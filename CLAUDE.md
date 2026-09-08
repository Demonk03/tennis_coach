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
        │          └─ player_profile + matches + match_prep + match_events + match_reviews
        └─ gpt.py → OpenAI API (тренер + психолог)
```

## Компоненты

| Файл | Назначение |
|---|---|
| `app.py` | Flask routes, auth, CORS, validation, lifecycle |
| `pult.py` | Контракт v2, безопасные повторы, полная история, статистика и досье |
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

Backend использует service-role key. RLS включён, но policies для браузера отсутствуют: frontend не ходит в Supabase напрямую.

### Новые таблицы

- `matches`: контекст, структурированный текущий счёт, итог, статус. Формат сессии разделён на две независимые оси: `session_type` (`friendly`/`tournament`/`practice`) задаёт допустимый уровень риска в тактике, `session_duration` (`1h`/`1_5h`/`2h`/`unlimited`) задаёт дозировку нагрузки. Legacy-колонка `session_format` вычисляется из этой пары в `app.py` и сохраняется для старых строк и клиентов.
- `player_profile`: единственный постоянный профиль игрока — уровень, опыт, стиль, сильные стороны и медицинский контекст.
- `match_prep`: опрос, снимок профиля игрока, структурированный `generated_game_plan` и legacy-тексты `generated_brief_technical`/`generated_brief_mental` для старых клиентов.
- `match_events`: два мультивыбора (`own_issues`, `opponent_actions`), комментарий, относительный счёт, стадия сета, совет и idempotency key. Legacy-поля не удалены.
- `match_reviews`: три слоя post-match анкеты — свои ошибки, эмоциональное состояние и наблюдения о сопернике; также хранит `advice_changed_play` и два AI-вывода.

## Персоны в gpt.py

Каждый AI-текст генерируется от лица одной из двух персон через отдельный system prompt:

- `COACH_PROMPT` — техника, тактика, физическое состояние, дозировка нагрузки.
- `PSYCHOLOGIST_PROMPT` — эмоции, концентрация, устойчивость.

В prep используется объединённый `MATCH_PLAN_PROMPT`, который возвращает проверяемую JSON-карточку: соперник, три ориентира, тело, reset и фокус. Тактика калибруется по текущему состоянию; история с тем же `opponent_name` передаётся отдельным блоком. На переходе AI связывает свою проблему с действием соперника. В post-match review сохраняются два отдельных AI-голоса.

Постоянный профиль передаётся как пользовательские данные, а не как system prompt. При создании плана его снимок сохраняется в `match_prep.player_profile_snapshot`; этот снимок используется на протяжении матча и при разборе. Текущее состояние из предматчевой анкеты и наблюдений имеет приоритет. Медицинский контекст используется только для безопасной дозировки нагрузки, без диагнозов, интерпретации анализов и назначения препаратов или добавок.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `SUPABASE_URL` | URL Supabase-проекта |
| `SUPABASE_KEY` | service-role key |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | Модель, default `gpt-4o-mini` |
| `API_KEY` | Личный ключ frontend → backend |
| `DASHBOARD_ORIGIN` | Разрешённые origins через запятую |

## Проверка

```bash
python3 -m pytest -q
python3 -m py_compile app.py db.py gpt.py pult.py
node --check docs/app.js
npm test  # после установки devDependencies
```

## Пульт v2

- Новый PWA использует `contract_version=2`; старые маршруты сохранены.
- До старта подготовка меняется в том же матче с проверкой ревизии; после старта исходные анкета и план неизменны.
- Операции подготовки, событий, завершения и разбора фиксируются транзакционно через `pult_operations`, с сохранённым результатом и защитой от устаревших запросов.
- Снимок начального контекста хранится в `match_prep`; legacy-уточнения стиля — отдельными записями `match_context_updates`.
- `app_helpful` (польза в целом) не объединять с прежним `advice_changed_play`.
- Досье использует точный логин, все исходные наблюдения и ссылки на матчи; кэш — `opponent_dossiers`. Не объединять имена и логины автоматически.
- Выпуск требует добавочной миграции `20260908_pult_v2.sql` до backend и frontend. Порядок резервирования, проверки истории и отката: [docs/deployment/pult-v2.md](docs/deployment/pult-v2.md). Не применять `20260907_remove_oura.sql` в рамках редизайна.

## Ограничения MVP

- Нет multi-user, полного offline, голоса и автоматического скоринга по очкам.
- Экран статистических паттернов отложен до накопления 8–10 матчей.
- Деплой и применение SQL требуют реальных секретов и выполняются отдельно.
- Перед деплоем P1–P3 обязательно применить `20260907_changeover_observations.sql`, `20260907_match_review_opponent.sql` и `20260907_session_type_duration.sql`.
- Известная блокирующая проблема (на 2026-07-30): запросы из Safari к защищённым endpoint'ам на Railway (`tenniscoach-production.up.railway.app`) зависают без HTTP-ответа. `/api/health` (без auth и Supabase) отвечал нормально. Подробности и диагностика — в заметке Obsidian проекта.
