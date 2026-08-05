create extension if not exists pgcrypto;

create table if not exists player_profile (
  id boolean primary key default true check (id),
  level text not null default '',
  experience text not null default '',
  playing_style text not null default '',
  strengths text not null default '',
  medical_context text not null default '',
  mental_pattern text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists matches (
  id uuid primary key default gen_random_uuid(),
  match_date date not null default current_date,
  match_type text not null check (match_type in ('singles', 'doubles')),
  opponent_name text,
  opponent_level text not null,
  opponent_style text,
  surface text not null check (surface in ('hard', 'clay', 'grass', 'carpet', 'other')),
  weather text,
  session_format text not null check (
    session_format in ('tournament', '1h_session', '2h_session', 'friendly')
  ),
  current_score jsonb not null default '{"sets":"","game":"0-0","serving":"unknown"}'::jsonb,
  final_score text,
  status text not null default 'preparing' check (
    status in ('preparing', 'in_progress', 'completed', 'cancelled')
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz
);

create unique index if not exists matches_one_active_idx
  on matches ((true))
  where status in ('preparing', 'in_progress');

create table if not exists match_prep (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null unique references matches(id) on delete cascade,
  oura_health_log_id uuid references health_logs(id) on delete set null,
  oura_data_date date,
  oura_is_stale boolean not null default false,
  oura_readiness integer,
  oura_sleep_score integer,
  oura_hrv numeric,
  player_profile_snapshot jsonb not null default '{}'::jsonb,
  energy_level integer not null check (energy_level between 1 and 5),
  last_meal text,
  physical_state text not null,
  mindset text not null,
  generated_brief_technical text not null,
  generated_brief_mental text not null,
  generated_game_plan jsonb,
  created_at timestamptz not null default now()
);

create table if not exists match_events (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references matches(id) on delete cascade,
  idempotency_key uuid not null unique,
  event_type text not null check (event_type in ('changeover', 'new_set')),
  working_well text[] not null default '{}',
  not_working text[] not null default '{}',
  how_feeling text not null,
  energy_level integer check (energy_level between 1 and 5),
  score_at_event jsonb not null,
  generated_advice text not null,
  created_at timestamptz not null default now()
);

create table if not exists match_reviews (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null unique references matches(id) on delete cascade,
  physical_rating integer not null check (physical_rating between 1 and 5),
  mental_rating integer not null check (mental_rating between 1 and 5),
  technical_comment text not null,
  mental_comment text not null,
  generated_technical_summary text not null,
  generated_mental_summary text not null,
  created_at timestamptz not null default now()
);

create index if not exists matches_created_at_idx on matches(created_at desc);
create index if not exists match_events_match_id_created_at_idx
  on match_events(match_id, created_at);
create index if not exists match_reviews_created_at_idx
  on match_reviews(created_at desc);

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists matches_set_updated_at on matches;
create trigger matches_set_updated_at
before update on matches
for each row execute function set_updated_at();

drop trigger if exists player_profile_set_updated_at on player_profile;
create trigger player_profile_set_updated_at
before update on player_profile
for each row execute function set_updated_at();

alter table player_profile enable row level security;
alter table matches enable row level security;
alter table match_prep enable row level security;
alter table match_events enable row level security;
alter table match_reviews enable row level security;

-- Frontend никогда не обращается к Supabase напрямую. Backend использует service-role key,
-- поэтому отдельные RLS policies для anon/authenticated намеренно не создаются.
