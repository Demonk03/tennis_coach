alter table match_prep
  add column if not exists generated_game_plan jsonb;

comment on column match_prep.generated_game_plan is
  'Structured pre-match card: opponent_cue, three tactics, body, reset and focus';
