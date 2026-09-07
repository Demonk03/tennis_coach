# AI Tennis Coach

Личный мобильный AI-тренер по теннису: учитывает постоянный профиль игрока, готовит структурированный план перед матчем, даёт короткие советы на переходах и помогает перестроиться между сетами. Профиль, матчи и советы сохраняются в Supabase.

Frontend — устанавливаемый PWA из `docs/`, backend — Flask API, генерация советов — OpenAI API.

## Локальный запуск

1. Скопировать `.env.example` в `.env` и заполнить значения.
2. Установить зависимости: `python3 -m pip install -r requirements.txt`.
3. Применить `supabase/schema.sql` в Supabase-проекте.
4. Запустить API: `python3 app.py`.
5. Запустить PWA: `python3 -m http.server 8000 --directory docs`.

Откройте `http://localhost:8000`, затем в «Настройках» сохраните адрес API и личный API-ключ.

Для существующей базы вместо полной схемы примените миграции из `supabase/migrations/`, включая `20260730_player_profile.sql` и `20260907_remove_oura.sql`.

## Проверка

```bash
python3 -m pytest -q
```
