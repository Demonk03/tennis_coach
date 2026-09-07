-- Structured, tap-friendly observations for changeovers and new-set check-ins.
-- Legacy columns remain so historical events and older clients keep working.

alter table match_events
  add column if not exists own_issues text[] not null default '{}',
  add column if not exists opponent_actions text[] not null default '{}',
  add column if not exists observation_comment text not null default '',
  add column if not exists score_state text check (score_state in ('ahead', 'even', 'behind')),
  add column if not exists set_stage text check (set_stage in ('early', 'middle', 'late'));
