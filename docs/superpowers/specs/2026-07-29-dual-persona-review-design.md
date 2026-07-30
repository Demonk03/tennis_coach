# Двухголосый разбор: тренер + психолог в prep и post-match review — дизайн

Дата: 2026-07-29
Статус: одобрен для реализации

## Идея

После первого реального использования MVP пользователь предложил два расширения, которые объединяются в одну фичу:

1. Пост-матчевый опросник: собирать самочувствие и свободный комментарий по игре (отдельно техника, отдельно психология), анализировать через ИИ что пошло не так и фиксировать вывод для будущих матчей.
2. Разделить советы на два «персонажа» — тренер (техника/физика/тактика) и психолог (ментальная часть) — вместо единого голоса.

Дуальность голосов нужна в двух точках жизненного цикла: **prep-брифе** перед матчем и **post-match review** после матча. Советы во время матча (переход между геймами, новый сет) остаются одним коротким голосом, как в MVP — момент игры не даёт времени читать два отдельных мнения.

## Сценарии

### 1. Подготовка к матчу (изменение существующего)

Вход не меняется. Меняется выход: вместо одного брифа — два отдельных коротких комментария, каждый от своего голоса:

- **Тренер** — тактика, физическая дозировка.
- **Психолог** — ментальный фокус.

Тренер дополнительно видит выводы из последних review (см. ниже), психолог — тоже.

### 2. Пост-матчевый разбор (новый сценарий)

Доступен только для матчей в терминальном статусе (`completed` или `cancelled`), один раз на матч.

Вход:

- `physical_rating` (1–5) — физическое состояние по ходу матча;
- `mental_rating` (1–5) — психологическая устойчивость/фокус по ходу матча;
- `technical_comment` — свободный текст, что пошло не так/хорошо по технике, физике, тактике;
- `mental_comment` — свободный текст, что происходило с головой, эмоциями, концентрацией.

Выход: два отдельных summary — от тренера (по `technical_comment` + `physical_rating`) и от психолога (по `mental_comment` + `mental_rating`). Каждое summary — по сути вывод на будущее, а не просто пересказ.

Результат сохраняется и переиспользуется: последние N review подтягиваются в контекст следующего prep-брифа, чтобы тренер и психолог видели, что отмечали в прошлый раз.

## Контекст AI

`gpt.py` получает два системных промпта вместо одного:

- `COACH_PROMPT` — тон и приоритеты тренера (техника, физика, тактика).
- `PSYCHOLOGIST_PROMPT` — тон и приоритеты психолога (ментальное состояние, эмоции, фокус).

Оба используются в двух функциях:

- `generate_prep_brief(match, survey, oura, past_reviews)` → `{"technical": str, "mental": str}` — два вызова OpenAI.
- `generate_post_match_review(match, prep, review_input)` → `{"technical": str, "mental": str}` — два вызова OpenAI.

Советы во время матча (`generate_changeover_advice`, `generate_new_set_advice`) не меняются — один голос, один системный промпт, как в MVP.

Если один из двух вызовов в паре падает — падает вся операция (`503 ai_unavailable`), партиальный результат (только одна половина) не сохраняется: оба голоса — часть одной консистентной записи.

## Архитектура

```text
gpt.py
 ├─ COACH_PROMPT / PSYCHOLOGIST_PROMPT
 ├─ generate_prep_brief()          → {"technical": str, "mental": str}
 └─ generate_post_match_review()   → {"technical": str, "mental": str}

db.py
 ├─ save_prep()                    — generated_brief_technical / generated_brief_mental
 ├─ save_review() / get_review_for_match()
 └─ get_recent_reviews(limit=3)    — контекст для следующего prep

app.py
 ├─ POST /api/matches/prep         — brief теперь {technical, mental}
 └─ POST /api/matches/:id/review   — новый эндпоинт
```

## Данные (Supabase)

`match_prep`: одна колонка `generated_brief` заменяется на две.

```sql
alter table match_prep drop column generated_brief;
alter table match_prep add column generated_brief_technical text not null default '';
alter table match_prep add column generated_brief_mental text not null default '';
alter table match_prep alter column generated_brief_technical drop default;
alter table match_prep alter column generated_brief_mental drop default;
```

Новая таблица `match_reviews` — один review на матч:

```sql
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

alter table match_reviews enable row level security;
create index if not exists match_reviews_created_at_idx on match_reviews(created_at desc);
```

`db.get_recent_reviews(limit=3)` — последние N записей `match_reviews` (summary-поля и исходные комментарии), передаются в `generate_prep_brief` как `past_reviews`.

## API-контракт

### `POST /api/matches/prep` (изменение)

Ответ:

```json
{
  "match": {...},
  "prep": {...},
  "brief": {
    "technical": "От тренера: ...",
    "mental": "От психолога: ..."
  },
  "oura": {...}
}
```

### `POST /api/matches/:id/review` (новое)

Запрос:

```json
{
  "physical_rating": 4,
  "mental_rating": 2,
  "technical_comment": "Подача не шла весь матч, много двойных на важных геймах",
  "mental_comment": "Плыл после проигранного первого сета, не мог перезагрузиться"
}
```

Валидация — по аналогии с существующими `_integer`/`_text` в `app.py`:

- `physical_rating`, `mental_rating` — целое 1–5;
- `technical_comment`, `mental_comment` — обязательные, max_length 500.

Правила состояния:

- 404 `not_found`, если матч не найден;
- 409 `invalid_match_state`, если статус матча не `completed`/`cancelled`;
- 409 `review_already_exists`, если review для этого `match_id` уже есть.

Ответ (201):

```json
{
  "review": {...},
  "summary": {
    "technical": "От тренера: ...",
    "mental": "От психолога: ..."
  }
}
```

## Frontend (PWA)

**Экран подготовки** — `#prep-result` вместо одного `<p id="prep-brief">` показывает два блока `.voice-card` (тренер / психолог). Этот же визуальный паттерн переиспользуется в review — единый язык «двух голосов» во всём приложении.

**Пост-матчевый review** — доступен в двух местах:

1. Сразу после `finish-form` — вместо немедленного перехода в историю показывается инлайн-форма review (слайдеры `physical_rating`/`mental_rating` по аналогии с `energy_level`, два `textarea`). После отправки — два `.voice-card` с summary, кнопка «В историю».
2. В `#screen-history` → `match-detail` — если у `completed`/`cancelled` матча ещё нет review, кнопка «Разобрать матч» открывает ту же форму (на случай, если приложение было закрыто сразу после игры). Если review уже есть — summary показываются как read-only.

## Тестирование

- Unit-тесты `gpt.generate_prep_brief` / `generate_post_match_review`: мокать `_complete`, проверять вызов обоих голосов и что падение одного даёт общую ошибку.
- API-тесты `POST /api/matches/:id/review`: 404/409 на неверный статус, 409 на повторный review, валидация рейтингов и длины комментариев.
- `node --check docs/app.js` — как сейчас; ручная проверка на устройстве, т.к. PWA не покрыта юнит-тестами.

## Ограничения

- Дуальность голосов не затрагивает советы во время матча (changeover/new_set) — там остаётся один голос.
- Редактирование или повторная генерация review не предусмотрены — один review на матч, вне зависимости от исхода.
- Применение SQL-миграций выполняется вручную, как и весь Supabase-деплой в проекте.
