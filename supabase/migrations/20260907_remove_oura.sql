-- Удаление интеграции с Oura.
-- Столбцы больше не заполняются приложением. Миграция удаляет их вместе
-- с накопленными значениями — применять после того, как история не нужна.

alter table match_prep
  drop column if exists oura_health_log_id,
  drop column if exists oura_data_date,
  drop column if exists oura_is_stale,
  drop column if exists oura_readiness,
  drop column if exists oura_sleep_score,
  drop column if exists oura_hrv;
