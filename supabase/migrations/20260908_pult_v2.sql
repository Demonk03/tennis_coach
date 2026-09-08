-- Additive rollout. Apply only after a verified backup. No historical values are backfilled.
begin;
alter table match_prep add column if not exists revision integer not null default 1;
alter table match_prep add column if not exists match_context_snapshot jsonb;
alter table match_events add column if not exists contract_version integer not null default 1;
alter table match_events add column if not exists completed_set_result text check (completed_set_result in ('won','lost'));
alter table match_reviews add column if not exists contract_version integer not null default 1;
alter table match_reviews add column if not exists opponent_styles text[] not null default '{}';
alter table match_reviews add column if not exists opponent_style_note text not null default '';
alter table match_reviews add column if not exists app_helpful boolean;

create table if not exists pult_operations (
  id uuid primary key, kind text not null, match_id uuid, body_hash text not null,
  status text not null check (status in ('pending','succeeded','failed')),
  token uuid not null, lease_until timestamptz not null,
  result jsonb, error jsonb, created_at timestamptz not null default now()
);
create table if not exists opponent_dossiers (
  opponent_name text primary key, source_hash text not null, summary jsonb not null,
  updated_at timestamptz not null default now()
);
create table if not exists match_context_updates (
  id uuid primary key default gen_random_uuid(), match_id uuid not null references matches(id) on delete cascade,
  opponent_style text not null, created_at timestamptz not null default now()
);
alter table pult_operations enable row level security;
alter table opponent_dossiers enable row level security;
alter table match_context_updates enable row level security;
create index if not exists match_context_updates_match_idx on match_context_updates(match_id, created_at);
create index if not exists matches_opponent_date_idx on matches(opponent_name, match_date desc, id);

-- A claim is durable across workers. Token fencing prevents an expired worker committing.
create or replace function pult_claim_operation(p_id uuid, p_kind text, p_match_id uuid, p_hash text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare op pult_operations; fresh uuid := gen_random_uuid();
begin
  insert into pult_operations(id,kind,match_id,body_hash,status,token,lease_until)
  values(p_id,p_kind,p_match_id,p_hash,'pending',fresh,now()+interval '4 minutes')
  on conflict(id) do nothing;
  select * into op from pult_operations where id=p_id for update;
  if op.kind<>p_kind or op.match_id is distinct from p_match_id or op.body_hash<>p_hash then
    return jsonb_build_object('status','conflict');
  end if;
  if op.status='succeeded' then return to_jsonb(op); end if;
  if op.token<>fresh and op.status='pending' and op.lease_until>now() then
    return jsonb_build_object('status','pending');
  end if;
  -- Serialize AI-producing operations for a given resource, including different request IDs.
  perform pg_advisory_xact_lock(hashtextextended(p_kind||coalesce(p_match_id::text,'new'),0));
  if exists(select 1 from pult_operations where id<>p_id and kind=p_kind
            and match_id is not distinct from p_match_id and status='pending' and lease_until>now()) then
    update pult_operations set status='failed',error='{"code":"resource_busy"}' where id=p_id;
    return jsonb_build_object('status','busy');
  end if;
  update pult_operations set status='pending',token=fresh,lease_until=now()+interval '4 minutes',error=null
  where id=p_id returning * into op;
  return jsonb_build_object('status','claimed','token',op.token);
end $$;

create or replace function pult_fail_operation(p_id uuid,p_token uuid,p_error jsonb)
returns void language sql security definer set search_path=public as $$
  update pult_operations set status='failed',error=p_error
  where id=p_id and token=p_token and status='pending';
$$;

create or replace function pult_renew_operation(p_id uuid,p_token uuid)
returns boolean language plpgsql security definer set search_path=public as $$
begin
  update pult_operations set lease_until=now()+interval '4 minutes'
  where id=p_id and token=p_token and status='pending' and lease_until>now();
  return found;
end $$;

-- All business writes and the replayable response commit in one database transaction.
create or replace function pult_commit_operation(p_id uuid,p_token uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path=public as $$
declare op pult_operations; m matches; pr match_prep; ev match_events; rv match_reviews;
  v_result jsonb; mid uuid; input_match jsonb;
begin
  select * into op from pult_operations where id=p_id for update;
  if not found or op.token<>p_token or op.status<>'pending' or op.lease_until<now() then
    raise exception 'operation_expired';
  end if;
  mid:=op.match_id;
  if mid is not null then
    select * into m from matches where id=mid for update;
    if not found then raise exception 'match_not_found'; end if;
  end if;
  if op.kind in ('prep_create','prep_update') then
    if op.kind='prep_update' then
      select * into pr from match_prep where match_id=mid for update;
      if m.status<>'preparing' or pr.revision<>(p_payload->>'revision')::integer then
        raise exception 'revision_conflict';
      end if;
    elsif exists(select 1 from matches where status in ('preparing','in_progress')) then
      raise exception 'active_match_exists';
    end if;
    input_match:=p_payload->'match';
    if op.kind='prep_create' then
      insert into matches(match_type,opponent_name,opponent_level,opponent_style,surface,weather,session_type,session_duration,session_format,status)
      values(input_match->>'match_type',input_match->>'opponent_name',input_match->>'opponent_level',input_match->>'opponent_style',
        input_match->>'surface',input_match->>'weather',input_match->>'session_type',input_match->>'session_duration',input_match->>'session_format','preparing')
      returning * into m;
      mid:=m.id;
    else
      update matches set match_type=input_match->>'match_type',opponent_name=input_match->>'opponent_name',
        opponent_level=input_match->>'opponent_level',opponent_style=input_match->>'opponent_style',surface=input_match->>'surface',
        weather=input_match->>'weather',session_type=input_match->>'session_type',session_duration=input_match->>'session_duration',
        session_format=input_match->>'session_format' where id=mid returning * into m;
    end if;
    insert into match_prep(match_id,energy_level,last_meal,physical_state,mindset,player_profile_snapshot,
      generated_game_plan,generated_brief_technical,generated_brief_mental,match_context_snapshot,revision)
    values(mid,(p_payload->'prep'->>'energy_level')::integer,p_payload->'prep'->>'last_meal',p_payload->'prep'->>'physical_state',
      p_payload->'prep'->>'mindset',p_payload->'prep'->'player_profile_snapshot',p_payload->'prep'->'generated_game_plan',
      p_payload->'prep'->>'generated_brief_technical',p_payload->'prep'->>'generated_brief_mental',input_match,1)
    on conflict(match_id) do update set energy_level=excluded.energy_level,last_meal=excluded.last_meal,
      physical_state=excluded.physical_state,mindset=excluded.mindset,player_profile_snapshot=excluded.player_profile_snapshot,
      generated_game_plan=excluded.generated_game_plan,generated_brief_technical=excluded.generated_brief_technical,
      generated_brief_mental=excluded.generated_brief_mental,match_context_snapshot=excluded.match_context_snapshot,
      revision=match_prep.revision+1 returning * into pr;
    v_result:=jsonb_build_object('match',to_jsonb(m),'prep',to_jsonb(pr),'events','[]'::jsonb,'review',null);
  elsif op.kind='event' then
    if m.status<>'in_progress' then raise exception 'invalid_match_state'; end if;
    ev:=jsonb_populate_record(null::match_events,p_payload);
    ev.id:=gen_random_uuid(); ev.match_id:=mid; ev.idempotency_key:=p_id; ev.created_at:=now();
    ev.working_well:='{}'; ev.not_working:='{}'; ev.how_feeling:=coalesce(ev.observation_comment,'');
    ev.score_at_event:='{}'; ev.contract_version:=2;
    insert into match_events select ev.*;
    v_result:=jsonb_build_object('event',to_jsonb(ev),'advice',ev.generated_advice);
  elsif op.kind='review' then
    if m.status not in ('completed','cancelled') then raise exception 'invalid_match_state'; end if;
    select * into rv from match_reviews where match_id=mid;
    if not found then
      rv:=jsonb_populate_record(null::match_reviews,p_payload);
      rv.id:=gen_random_uuid(); rv.match_id:=mid; rv.created_at:=now(); rv.contract_version:=2;
      insert into match_reviews select rv.*;
    end if;
    v_result:=jsonb_build_object('review',to_jsonb(rv),'summary',jsonb_build_object('technical',rv.generated_technical_summary,'mental',rv.generated_mental_summary));
  elsif op.kind='finish' then
    if m.status='completed' and m.final_score=p_payload->>'final_score' then null;
    elsif m.status<>'in_progress' then raise exception 'invalid_match_state';
    else
      update matches set status='completed',final_score=p_payload->>'final_score',completed_at=now()
      where id=mid returning * into m;
    end if;
    v_result:=jsonb_build_object('match',to_jsonb(m));
  elsif op.kind='dossier_refresh' then
    insert into opponent_dossiers(opponent_name,source_hash,summary)
    values(p_payload->>'opponent_name',p_payload->>'source_hash',p_payload->'summary')
    on conflict(opponent_name) do update set source_hash=excluded.source_hash,summary=excluded.summary,updated_at=now();
    v_result:=jsonb_build_object('summary',p_payload->'summary');
  else raise exception 'unknown_operation';
  end if;
  update pult_operations set status='succeeded',result=v_result where id=p_id;
  return v_result;
end $$;

create or replace function pult_start_match(p_match_id uuid,p_revision integer default null)
returns jsonb language plpgsql security definer set search_path=public as $$
declare m matches; rev integer;
begin
  select * into m from matches where id=p_match_id for update;
  if not found or m.status not in ('preparing','in_progress') then raise exception 'invalid_match_state'; end if;
  select revision into rev from match_prep where match_id=p_match_id;
  if p_revision is not null and p_revision is distinct from rev then raise exception 'revision_conflict'; end if;
  update matches set status='in_progress' where id=p_match_id returning * into m;
  return jsonb_build_object('match',to_jsonb(m));
end $$;

create or replace function pult_update_style(p_match_id uuid,p_style text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare m matches;
begin
  select * into m from matches where id=p_match_id for update;
  if not found or m.status<>'in_progress' then raise exception 'invalid_match_state'; end if;
  insert into match_context_updates(match_id,opponent_style) values(p_match_id,p_style);
  -- This is the legacy current-context projection; immutable initial values live in prep's snapshot.
  update matches set opponent_style=p_style where id=p_match_id returning * into m;
  return to_jsonb(m);
end $$;

-- Security-definer RPCs must never be callable by browser roles.
revoke all on function pult_claim_operation(uuid,text,uuid,text) from public,anon,authenticated;
revoke all on function pult_fail_operation(uuid,uuid,jsonb) from public,anon,authenticated;
revoke all on function pult_commit_operation(uuid,uuid,jsonb) from public,anon,authenticated;
revoke all on function pult_renew_operation(uuid,uuid) from public,anon,authenticated;
revoke all on function pult_start_match(uuid,integer) from public,anon,authenticated;
revoke all on function pult_update_style(uuid,text) from public,anon,authenticated;
grant execute on function pult_claim_operation(uuid,text,uuid,text),pult_fail_operation(uuid,uuid,jsonb),
  pult_commit_operation(uuid,uuid,jsonb),pult_renew_operation(uuid,uuid),pult_start_match(uuid,integer),pult_update_style(uuid,text) to service_role;
grant select, insert, update, delete on pult_operations, opponent_dossiers, match_context_updates to service_role;
commit;
