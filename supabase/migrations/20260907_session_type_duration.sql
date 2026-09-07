-- Split session_format into two orthogonal axes: event type and time on court.
-- session_format stays as a derived legacy column so older rows and clients keep working.

alter table matches
  add column if not exists session_type text not null default 'friendly',
  add column if not exists session_duration text not null default 'unlimited';

update matches
set
  session_type = case
    when session_format = 'tournament' then 'tournament'
    else 'friendly'
  end,
  session_duration = case
    when session_format = '1h_session' then '1h'
    when session_format = '2h_session' then '2h'
    else 'unlimited'
  end;

alter table matches
  drop constraint if exists matches_session_type_check,
  drop constraint if exists matches_session_duration_check;

alter table matches
  add constraint matches_session_type_check
    check (session_type in ('friendly', 'tournament', 'practice')),
  add constraint matches_session_duration_check
    check (session_duration in ('1h', '1_5h', '2h', 'unlimited'));
