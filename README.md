# AI Tennis Coach

Личный мобильный AI-тренер по теннису: готовит структурированный план перед матчем, даёт короткие советы на переходах и помогает перестроиться между сетами. Показатели восстановления берутся из существующей таблицы `Oura-v2.health_logs`, а матчи и советы сохраняются в Supabase.

Frontend — устанавливаемый PWA из `docs/`, backend — Flask API, генерация советов — OpenAI API.

## Локальный запуск

1. Скопировать `.env.example` в `.env` и заполнить значения.
2. Установить зависимости: `python3 -m pip install -r requirements.txt`.
3. Применить `supabase/schema.sql` в Supabase-проекте Oura-v2.
4. Запустить API: `python3 app.py`.
5. Запустить PWA: `python3 -m http.server 8000 --directory docs`.

Откройте `http://localhost:8000`, затем в «Настройках» сохраните адрес API и личный API-ключ.

## Проверка

```bash
python3 -m pytest -q
```
