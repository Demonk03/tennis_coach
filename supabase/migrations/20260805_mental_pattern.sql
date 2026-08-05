alter table player_profile
  add column if not exists mental_pattern text not null default '';

comment on column player_profile.mental_pattern is
  'Durable psychological tendency (e.g. tightens up on break points) — distinct from the per-match mindset survey answer';
