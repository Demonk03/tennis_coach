-- Preserve three separate post-match entities: my game, my emotional state,
-- and observations about the opponent. Existing review columns remain intact.

alter table match_reviews
  add column if not exists own_errors text not null default '',
  add column if not exists emotional_state text not null default '',
  add column if not exists opponent_style text not null default '',
  add column if not exists opponent_what_worked text not null default '',
  add column if not exists opponent_errors text not null default '',
  add column if not exists advice_changed_play boolean;
