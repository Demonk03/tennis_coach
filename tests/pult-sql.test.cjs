const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { PGlite } = require("@electric-sql/pglite");
const { randomUUID } = require("node:crypto");

test("additive migration preserves history and fences transactional operations", async () => {
  const db = new PGlite();
  try {
    await db.exec(
      "create role anon;create role authenticated;create role service_role;",
    );
    // PGlite has core gen_random_uuid; pgcrypto extension is unavailable in its WASM build.
    await db.exec(
      fs
        .readFileSync("supabase/schema.sql", "utf8")
        .replace("create extension if not exists pgcrypto;", ""),
    );
    const old = (
      await db.query(
        "insert into matches(match_type,opponent_level,surface,session_format,status,final_score) values('singles','equal','hard','friendly','completed','6-0 6-4') returning *",
      )
    ).rows[0];
    const oldPrep = (
      await db.query(
        "insert into match_prep(match_id,energy_level,physical_state,mindset,generated_brief_technical,generated_brief_mental) values($1,3,'old body','old mind','old plan','old focus') returning *",
        [old.id],
      )
    ).rows[0];
    await db.query(
      "insert into match_events(match_id,event_type,how_feeling,score_at_event,idempotency_key,generated_advice) values($1,'changeover','legacy','{}',$2,'old advice')",
      [old.id, randomUUID()],
    );
    await db.query(
      "insert into match_reviews(match_id,physical_rating,mental_rating,technical_comment,mental_comment,generated_technical_summary,generated_mental_summary,advice_changed_play) values($1,3,3,'old tech','old mental','old summary','old psych',true)",
      [old.id],
    );
    const before = {};
    for (const table of [
      "matches",
      "match_prep",
      "match_events",
      "match_reviews",
    ])
      before[table] = (await db.query(`select * from ${table}`)).rows;
    const migration = fs.readFileSync(
      "supabase/migrations/20260908_pult_v2.sql",
      "utf8",
    );
    await db.exec(migration);
    await db.exec(migration);
    for (const [table, rows] of Object.entries(before)) {
      const after = (await db.query(`select * from ${table} order by id`)).rows;
      assert.equal(rows.length, after.length);
      for (const row of rows) {
        const next = after.find((r) => r.id === row.id);
        for (const [k, v] of Object.entries(row))
          assert.deepEqual(next[k], v, `${table}.${k} preserved`);
      }
    }
    assert.equal(
      (await db.query("select app_helpful from match_reviews")).rows[0]
        .app_helpful,
      null,
    );
    const rpc = async (name, args) =>
      (
        await db.query(
          `select ${name}(${args.map((_, i) => "$" + (i + 1)).join(",")}) as value`,
          args,
        )
      ).rows[0].value;
    const claim = (key, kind, mid, hash = "body") =>
      rpc("pult_claim_operation", [key, kind, mid, hash]);
    const key = randomUUID();
    const claimed = await claim(key, "prep_create", null);
    assert.equal(claimed.status, "claimed");
    assert.equal((await claim(key, "prep_create", null)).status, "pending");
    assert.equal(
      (await claim(key, "prep_create", null, "different")).status,
      "conflict",
    );
    const payload = {
      match: {
        match_type: "singles",
        opponent_name: "andrey_k",
        opponent_level: "equal",
        opponent_style: "slice",
        surface: "hard",
        weather: "",
        session_type: "friendly",
        session_duration: "1h",
        session_format: "1h_session",
      },
      prep: {
        energy_level: 3,
        last_meal: "",
        physical_state: "fine",
        mindset: "ready",
        player_profile_snapshot: { level: "3.5" },
        generated_game_plan: { focus: "depth", tactics: ["a", "b", "c"] },
        generated_brief_technical: "new plan",
        generated_brief_mental: "new focus",
      },
    };
    const created = await rpc("pult_commit_operation", [
      key,
      claimed.token,
      payload,
    ]);
    assert.equal(created.match.status, "preparing");
    assert.equal(
      (await claim(key, "prep_create", null)).result.match.id,
      created.match.id,
    );
    const id = created.match.id,
      updateKey = randomUUID();
    const update = await claim(updateKey, "prep_update", id);
    const edited = await rpc("pult_commit_operation", [
      updateKey,
      update.token,
      { ...payload, revision: 1, prep: { ...payload.prep, mindset: "edited" } },
    ]);
    assert.equal(edited.match.id, id);
    assert.equal(edited.prep.revision, 2);
    assert.equal(edited.prep.id, created.prep.id);
    await assert.rejects(rpc("pult_start_match", [id, 1]), /revision_conflict/);
    await rpc("pult_start_match", [id, 2]);
    const lateKey = randomUUID(),
      late = await claim(lateKey, "prep_update", id);
    await assert.rejects(
      rpc("pult_commit_operation", [
        lateKey,
        late.token,
        { ...payload, revision: 2 },
      ]),
      /revision_conflict/,
    );
    await rpc("pult_update_style", [id, "new observation"]);
    assert.equal(
      (
        await db.query(
          "select match_context_snapshot from match_prep where match_id=$1",
          [id],
        )
      ).rows[0].match_context_snapshot.opponent_style,
      "slice",
    );
    assert.equal(
      (
        await db.query(
          "select count(*)::int as n from match_context_updates where match_id=$1",
          [id],
        )
      ).rows[0].n,
      1,
    );
    const ek = randomUUID(),
      eclaim = await claim(ek, "event", id);
    const event = await rpc("pult_commit_operation", [
      ek,
      eclaim.token,
      {
        event_type: "new_set",
        own_issues: ["short_balls"],
        opponent_actions: [],
        completed_set_result: "lost",
        energy_level: 2,
        observation_comment: "",
        generated_advice: "next set",
      },
    ]);
    assert.equal(event.event.completed_set_result, "lost");
    assert.deepEqual(event.event.score_at_event, {});
    const fk = randomUUID(),
      fc = await claim(fk, "finish", id);
    await rpc("pult_commit_operation", [
      fk,
      fc.token,
      { final_score: "6-0 6-4" },
    ]);
    const rk = randomUUID(),
      rc = await claim(rk, "review", id);
    const r = await rpc("pult_commit_operation", [
      rk,
      rc.token,
      {
        physical_rating: 4,
        mental_rating: 3,
        own_errors: "test",
        emotional_state: "",
        opponent_style: "",
        opponent_style_note: "",
        opponent_styles: [],
        opponent_what_worked: "",
        opponent_errors: "",
        technical_comment: "test",
        mental_comment: "",
        app_helpful: true,
        advice_changed_play: null,
        generated_technical_summary: "tech",
        generated_mental_summary: "mental",
      },
    ]);
    assert.equal(r.review.app_helpful, true);
    assert.equal(r.review.advice_changed_play, null);
    const exp = randomUUID(),
      first = await claim(exp, "prep_create", null);
    await db.query(
      "update pult_operations set lease_until=now()-interval '1 minute' where id=$1",
      [exp],
    );
    const second = await claim(exp, "prep_create", null);
    assert.notEqual(first.token, second.token);
    await assert.rejects(
      rpc("pult_commit_operation", [exp, first.token, payload]),
      /operation_expired/,
    );
    const forbidden = await db.query(
      "select has_function_privilege('anon','pult_commit_operation(uuid,uuid,jsonb)','EXECUTE') as allowed",
    );
    assert.equal(forbidden.rows[0].allowed, false);
  } finally {
    await db.close();
  }
});
