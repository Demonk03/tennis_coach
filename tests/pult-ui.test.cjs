const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { JSDOM } = require("jsdom");
function app() {
  const dom = new JSDOM(fs.readFileSync("docs/index.html", "utf8"), {
    url: "http://localhost/",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const w = dom.window;
  w.HTMLElement.prototype.scrollTo = function (o) {
    this.scrollTop = o.top;
  };
  w.confirm = () => false;
  w.localStorage.setItem("tennisCoachApiUrl", "http://api.test");
  w.localStorage.setItem("tennisCoachApiKey", "test");
  w.eval(
    fs.readFileSync("docs/app.js", "utf8").replace(/boot\(\);\s*$/, "") +
      "\nwindow.testApp={state,renderPrep,renderReview,renderObservation,renderFinish,renderMatch,renderDetails,renderHistory,renderProfile,formValues,saveDraft,draftKey,readDraft,performOperation,reconcileDrafts,scoreOutcome,handleAction};",
  );
  return { dom, w, a: w.testApp };
}
function bundle() {
  return {
    match: {
      id: "match1",
      status: "in_progress",
      opponent_name: "<script>alert(1)</script>",
    },
    prep: {
      generated_game_plan: {
        focus: "Фокус",
        tactics: ["раз", "два", "три"],
        body: "Тело",
        reset: "Reset",
        opponent_cue: "Slice",
      },
    },
    events: [],
  };
}
test("observation has explicit context and a pinned submit outside scrolling content", () => {
  const { dom, w, a } = app();
  try {
    a.state.activeBundle = bundle();
    a.renderObservation("changeover");
    assert.equal(
      w.document.querySelectorAll("#observation-form input:checked").length,
      0,
    );
    assert.equal(w.document.querySelectorAll("[name=own_issues]").length, 6);
    assert.equal(w.document.querySelector("[name=short_balls]"), null);
    assert.ok(
      w.document.querySelector("#actions button[form=observation-form]"),
    );
    assert.ok(
      !w.document
        .querySelector("#content")
        .contains(w.document.querySelector("#actions")),
    );
    a.renderObservation("new_set");
    assert.equal(
      w.document.querySelectorAll("[name=completed_set_result]").length,
      2,
    );
    assert.equal(
      w.document.querySelectorAll("#observation-form [name=score_state]")
        .length,
      0,
    );
    assert.equal(
      w.document.querySelectorAll("#observation-form [name=set_stage]").length,
      0,
    );
  } finally {
    dom.window.close();
  }
});
test("review collects multi styles and new benefit without default answers", () => {
  const { dom, w, a } = app();
  try {
    a.renderReview("match1");
    assert.equal(
      w.document.querySelectorAll("#review-form input:checked").length,
      0,
    );
    assert.equal(
      w.document.querySelectorAll("#review-form textarea[required]").length,
      0,
    );
    assert.equal(
      w.document.querySelectorAll("[name=opponent_styles][type=checkbox]")
        .length,
      6,
    );
    assert.equal(w.document.querySelectorAll("[name=app_helpful]").length, 2);
    assert.equal(
      w.document.querySelectorAll("[name=advice_changed_play]").length,
      0,
    );
    const f = w.document.querySelector("#review-form");
    f.elements.own_errors.value = "Коротко";
    a.saveDraft(f);
    a.renderReview("match1");
    assert.equal(
      w.document.querySelector("[name=own_errors]").value,
      "Коротко",
    );
    a.renderReview("match2");
    assert.equal(w.document.querySelector("[name=own_errors]").value, "");
  } finally {
    dom.window.close();
  }
});
test("latest advice dominates match and original plan stays available; text is escaped", () => {
  const { dom, w, a } = app();
  try {
    a.state.activeBundle = bundle();
    a.state.activeBundle.events = [
      {
        id: "e1",
        generated_advice: "<img src=x onerror=alert(1)>",
        event_type: "changeover",
      },
    ];
    a.renderMatch();
    assert.equal(
      w.document.querySelector(".advice-text").textContent,
      "<img src=x onerror=alert(1)>",
    );
    assert.equal(w.document.querySelector("#screen-match img"), null);
    assert.ok(w.document.querySelector("#screen-match details .plan-tactics"));
  } finally {
    dom.window.close();
  }
});
test("finish keeps accessible wheels and deferred-review action", () => {
  const { dom, w, a } = app();
  try {
    a.state.activeBundle = bundle();
    a.renderFinish();
    assert.equal(
      w.document.querySelectorAll(".score-wheel[role=listbox]").length,
      2,
    );
    assert.ok(w.document.querySelector("[name=finish_mode][value=later]"));
    assert.equal(a.scoreOutcome("6-0 6-4"), "win");
    assert.equal(a.scoreOutcome("6-4 abandoned"), null);
  } finally {
    dom.window.close();
  }
});
test("lost response reuses persisted operation ID and does not duplicate write", async () => {
  const { dom, w, a } = app();
  try {
    let writes = 0;
    const bodies = [];
    w.fetch = async (url, options) => {
      if (options.method === "POST") {
        writes++;
        bodies.push(JSON.parse(options.body));
        throw new Error("network");
      }
      return { ok: true, json: async () => ({ status: "failed" }) };
    };
    const key = a.draftKey("changeover", "m");
    await assert.rejects(
      a.performOperation(key, "/api/matches/m/events", "POST", {
        comment: "test",
      }),
    );
    await assert.rejects(
      a.performOperation(key, "/api/matches/m/events", "POST", {
        comment: "test",
      }),
    );
    assert.equal(writes, 2);
    assert.equal(bodies[0].idempotency_key, bodies[1].idempotency_key);
    w.fetch = async () => ({
      ok: true,
      json: async () => ({ status: "succeeded", result: { advice: "saved" } }),
    });
    const result = await a.performOperation(
      key,
      "/api/matches/m/events",
      "POST",
      { comment: "test" },
    );
    assert.equal(result.advice, "saved");
    assert.equal(a.readDraft(key), null);
  } finally {
    dom.window.close();
  }
});
test("permanent deletion requires explicit confirmation", async () => {
  const { dom, w, a } = app();
  try {
    a.state.detail = bundle();
    w.fetch = () => {
      throw new Error("must not send");
    };
    await a.handleAction("delete-match", {});
  } finally {
    dom.window.close();
  }
});
test("reopening reconciles a saved create and preserves newer edits under its match", async () => {
  const { dom, w, a } = app();
  try {
    const key = a.draftKey("prep");
    const saved = {
      values: { mindset: "Спокойно", energy_level: "3" },
      operation: {
        input: { mindset: "Спокойно", energy_level: 3 },
        body: { idempotency_key: "request1" },
      },
    };
    w.fetch = async () => ({
      ok: true,
      json: async () => ({
        status: "succeeded",
        result: { match: { id: "created1" } },
      }),
    });
    w.localStorage.setItem(key, JSON.stringify(saved));
    await a.reconcileDrafts();
    assert.equal(a.readDraft(key), null);
    saved.values.mindset = "Новый настрой";
    w.localStorage.setItem(key, JSON.stringify(saved));
    await a.reconcileDrafts();
    assert.equal(a.readDraft(key), null);
    const next = a.readDraft(a.draftKey("prep", "created1"));
    assert.equal(next.values.mindset, "Новый настрой");
    assert.equal(next.operation, undefined);
  } finally {
    dom.window.close();
  }
});
test("a replay cannot apply a previous server result after connection changes", async () => {
  const { dom, w, a } = app();
  try {
    const key = a.draftKey("changeover", "m");
    w.localStorage.setItem(
      key,
      JSON.stringify({
        operation: {
          input: { comment: "text", contract_version: 2 },
          body: { idempotency_key: "request1" },
        },
      }),
    );
    w.fetch = async () => {
      w.localStorage.setItem("tennisCoachApiUrl", "http://other.test");
      return {
        ok: true,
        json: async () => ({
          status: "succeeded",
          result: { advice: "old server" },
        }),
      };
    };
    await assert.rejects(
      a.performOperation(key, "/api/matches/m/events", "POST", {
        comment: "text",
      }),
      /Подключение изменилось/,
    );
    assert.ok(a.readDraft(key));
  } finally {
    dom.window.close();
  }
});
test("maximum advice and legacy plan text remain available in full", () => {
  const { dom, w, a } = app();
  try {
    const b = bundle();
    b.prep = {
      generated_brief_technical: "Старый технический план",
      generated_brief_mental: "Старый настрой",
    };
    b.events = [
      {
        id: "long",
        event_type: "new_set",
        generated_advice: "Длинный совет. ".repeat(50).slice(0, 700),
      },
    ];
    a.state.activeBundle = b;
    a.renderMatch();
    assert.equal(
      w.document.querySelector(".advice-text").textContent.length,
      700,
    );
    assert.ok(
      w.document
        .querySelector("#screen-match")
        .textContent.includes("Старый технический план"),
    );
    assert.ok(
      w.document
        .querySelector("#screen-match")
        .textContent.includes("Старый настрой"),
    );
  } finally {
    dom.window.close();
  }
});

test("form section titles sit inside rounded cards instead of cutting their borders", () => {
  const { dom, w, a } = app();
  try {
    a.renderPrep();
    assert.equal(w.document.querySelectorAll("#prep-form fieldset").length, 0);
    assert.equal(
      w.document.querySelectorAll("#prep-form .form-section").length,
      2,
    );
    assert.deepEqual(
      [...w.document.querySelectorAll("#prep-form .form-section-title")].map(
        (node) => node.textContent,
      ),
      ["Матч", "Состояние"],
    );
  } finally {
    dom.window.close();
  }
});

test("journal period is an explicit compact switch with a separate month picker", () => {
  const { dom, w, a } = app();
  try {
    a.state.history.loaded = true;
    a.state.history.items = [];
    a.state.history.next = null;
    a.state.history.stats = {
      completed: 13,
      wins: 8,
      losses: 5,
      unknown: 0,
      helpful_total: 0,
    };
    a.renderHistory();
    assert.equal(
      w.document.querySelectorAll(".period-switch button").length,
      2,
    );
    assert.equal(
      w.document.querySelector(".period-switch [aria-pressed=true]")
        .textContent,
      "Месяц",
    );
    assert.match(
      w.document.querySelector(".month-picker").textContent,
      /Выбрать месяц/i,
    );
    assert.equal(
      w.document.querySelector(".history-summary").children.length,
      2,
    );
    a.state.history.month = "";
    a.state.history.loaded = true;
    a.renderHistory();
    assert.equal(w.document.querySelector(".month-picker"), null);
    assert.equal(
      w.document.querySelector(".period-switch [aria-pressed=true]")
        .textContent,
      "Всё время",
    );
  } finally {
    dom.window.close();
  }
});

test("profile uses growing multiline fields for descriptive answers", async () => {
  const { dom, w, a } = app();
  try {
    w.fetch = async () => ({
      ok: true,
      json: async () => ({
        profile: {
          experience: "Длинное описание опыта",
          playing_style: "Длинное описание стиля",
        },
      }),
    });
    await a.renderProfile();
    assert.equal(
      w.document.querySelector("[name=experience]").tagName,
      "TEXTAREA",
    );
    assert.equal(
      w.document.querySelectorAll("#profile-form fieldset").length,
      0,
    );
    assert.equal(
      w.document.querySelectorAll("#profile-form textarea.auto-grow").length,
      5,
    );
  } finally {
    dom.window.close();
  }
});
