# AI Tennis Coach — Project Context

GitHub: https://github.com/Demonk03/tennis_coach

## Назначение

Личный мобильный PWA-тренер по теннису. Генерирует подготовительный бриф, одну короткую установку на переходе и план на новый сет. Матчи, наблюдения и советы сохраняются в Supabase.

## Архитектура

```text
docs/ PWA (GitHub Pages)
        ↓ Bearer API key
app.py Flask API (Render)
        ├─ db.py → Supabase
        │          ├─ users + health_logs (существующие таблицы Oura-v2)
        │          └─ matches + match_prep + match_events
        └─ gpt.py → OpenAI API
```

Tennis-coach никогда не вызывает Oura API. Он только читает последнюю строку `health_logs` по `OURA_USER_ID`. Значения копируются в `match_prep`, чтобы история была неизменной.

## Компоненты

| Файл | Назначение |
|---|---|
| `app.py` | Flask routes, auth, CORS, validation, lifecycle |
| `db.py` | Все обращения к Supabase |
| `gpt.py` | Промпты и вызовы OpenAI |
| `supabase/schema.sql` | Tennis-таблицы, ограничения, индексы, RLS |
| `docs/` | Статический mobile-first PWA |
| `tests/` | Unit/API tests без внешних сервисов |
| `render.yaml` | Конфигурация Render |

## Жизненный цикл

- В БД допускается один матч `preparing` или `in_progress`.
- `POST /api/matches/prep` сначала получает ответ OpenAI и только затем создаёт матч.
- После брифа `POST /api/matches/:id/start` переводит матч в `in_progress`.
- PWA восстанавливает состояние через `GET /api/matches/active`.
- События имеют UUID `idempotency_key`.
- Завершение переводит матч в `completed`; отмена — в `cancelled`.

## Supabase

Схему следует применять в том же Supabase-проекте, где уже есть `users` и `health_logs`. Backend использует service-role key. RLS включён, но policies для браузера отсутствуют: frontend не ходит в Supabase напрямую.

### Новые таблицы

- `matches`: контекст, структурированный текущий счёт, итог, статус.
- `match_prep`: опрос, снимок Oura и подготовительный бриф.
- `match_events`: тип, чипы, состояние, счёт, совет, idempotency key.

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
