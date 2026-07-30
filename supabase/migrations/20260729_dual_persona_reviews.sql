alter table match_prep
  add column if not exists generated_brief_technical text not null default '';
alter table match_prep
  add column if not exists generated_brief_mental text not null default '';

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'match_prep'
      and column_name = 'generated_brief'
  ) then
    update match_prep
    set generated_brief_technical = generated_brief
    where generated_brief_technical = '';
  end if;
end
$$;

alter table match_prep alter column generated_brief_technical drop default;
alter table match_prep alter column generated_brief_mental drop default;
alter table match_prep drop column if exists generated_brief;

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

create index if not exists match_reviews_created_at_idx
  on match_reviews(created_at desc);

alter table match_reviews enable row level security;
