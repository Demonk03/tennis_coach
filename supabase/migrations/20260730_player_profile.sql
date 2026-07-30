create table if not exists player_profile (
  id boolean primary key default true check (id),
  level text not null default '',
  experience text not null default '',
  playing_style text not null default '',
  strengths text not null default '',
  medical_context text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table match_prep
  add column if not exists player_profile_snapshot jsonb not null default '{}'::jsonb;

drop trigger if exists player_profile_set_updated_at on player_profile;
create trigger player_profile_set_updated_at
before update on player_profile
for each row execute function set_updated_at();

alter table player_profile enable row level security;

comment on table player_profile is
  'Singleton durable player context used to personalize tennis advice';
comment on column match_prep.player_profile_snapshot is
  'Immutable player profile used when this match plan was generated';
