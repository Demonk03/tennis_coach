# AI Tennis Coach — Project Context

GitHub: https://github.com/Demonk03/tennis_coach

## Назначение

Личный мобильный PWA-тренер по теннису. Генерирует структурированный план на матч, одну короткую установку на переходе и план на новый сет. Матчи, наблюдения и советы сохраняются в Supabase.

## Архитектура

```text
docs/ PWA (GitHub Pages)
        ↓ Bearer API key
app.py Flask API (Railway)
        ├─ db.py → Supabase
        │          ├─ users + health_logs (существующие таблицы Oura-v2)
        │          └─ player_profile + matches + match_prep + match_events + match_reviews
        └─ gpt.py → OpenAI API (тренер + психолог)
```

Tennis-coach никогда не вызывает Oura API. Он только читает последнюю строку `health_logs` по `OURA_USER_ID`. Значения копируются в `match_prep`, чтобы история была неизменной.

## Компоненты

| Файл | Назначение |
|---|---|
| `app.py` | Flask routes, auth, CORS, validation, lifecycle |
| `db.py` | Все обращения к Supabase |
| `gpt.py` | Промпты и вызовы OpenAI |
| `supabase/schema.sql` | Tennis-таблицы, ограничения, индексы, RLS |
| `supabase/migrations/` | Инкрементальные миграции для уже созданного Supabase-проекта |
| `render.yaml` | Конфигурация Render — не используется, реальный хостинг backend — Railway |
| `docs/` | Статический mobile-first PWA |
| `tests/` | Unit/API tests без внешних сервисов |

## Жизненный цикл

- В БД допускается один матч `preparing` или `in_progress`.
- `POST /api/matches/prep` сначала получает ответ OpenAI и только затем создаёт матч.
- После брифа `POST /api/matches/:id/start` переводит матч в `in_progress`.
- PWA восстанавливает состояние через `GET /api/matches/active`.
- События имеют UUID `idempotency_key`.
- Завершение переводит матч в `completed`; отмена — в `cancelled`.
- `POST /api/matches/:id/review` доступен только для `completed`/`cancelled` матчей, один разбор на матч (unique constraint на `match_id`, повтор → 409 `review_already_exists`).

## Supabase

Схему следует применять в том же Supabase-проекте, где уже есть `users` и `health_logs`. Backend использует service-role key. RLS включён, но policies для браузера отсутствуют: frontend не ходит в Supabase напрямую.

### Новые таблицы

- `matches`: контекст, структурированный текущий счёт, итог, статус.
- `player_profile`: единственный постоянный профиль игрока — уровень, опыт, стиль, сильные стороны и медицинский контекст.
- `match_prep`: опрос, снимки Oura и профиля игрока, структурированный `generated_game_plan` и legacy-тексты `generated_brief_technical`/`generated_brief_mental` для старых клиентов.
- `match_events`: тип, чипы, состояние, счёт, совет, idempotency key.
- `match_reviews`: post-match анкета (`physical_rating`, `mental_rating`, `technical_comment`, `mental_comment`) и сгенерированные выводы тренера/психолога, один разбор на матч.

## Персоны в gpt.py

Каждый AI-текст генерируется от лица одной из двух персон через отдельный system prompt:

- `COACH_PROMPT` — техника, тактика, физическое состояние, дозировка нагрузки.
- `PSYCHOLOGIST_PROMPT` — эмоции, концентрация, устойчивость.

В prep используется объединённый `MATCH_PLAN_PROMPT`, который возвращает проверяемую JSON-карточку: соперник, три ориентира, тело, reset и фокус. В post-match review сохраняются два отдельных голоса. На переходах и перед новым сетом используется короткий тренерский совет. Таск-промпты внутри каждого вызова явно указывают, на каких полях DATA строить совет.

Постоянный профиль передаётся как пользовательские данные, а не как system prompt. При создании плана его снимок сохраняется в `match_prep.player_profile_snapshot`; этот снимок используется на протяжении матча и при разборе. Текущее состояние из предматчевой анкеты и наблюдений имеет приоритет. Медицинский контекст используется только для безопасной дозировки нагрузки, без диагнозов, интерпретации анализов и назначения препаратов или добавок.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `SUPABASE_URL` | URL существующего Supabase Oura-v2 |
| `SUPABASE_KEY` | service-role key |
| `OURA_USER_ID` | UUID нужной строки `users` |
| `OURA_MAX_AGE_DAYS` | После скольких дней запись считается устаревшей |
| `APP_TIMEZONE` | Часовой пояс проверки свежести |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | Модель, default `gpt-4o-mini` |
| `API_KEY` | Личный ключ frontend → backend |
| `DASHBOARD_ORIGIN` | Разрешённые origins через запятую |

## Проверка

```bash
python3 -m pytest -q
python3 -m py_compile app.py db.py gpt.py
node --check docs/app.js
```

## Ограничения MVP

- Нет multi-user, полного offline, голоса и автоматического скоринга по очкам.
- Экран статистических паттернов отложен до накопления 8–10 матчей.
- Деплой и применение SQL требуют реальных секретов и выполняются отдельно.
- Известная блокирующая проблема (на 2026-07-30): запросы из Safari к защищённым endpoint'ам на Railway (`tenniscoach-production.up.railway.app`) зависают без HTTP-ответа. `/api/health` (без auth и Supabase) отвечал нормально. Подробности и диагностика — в заметке Obsidian проекта.
