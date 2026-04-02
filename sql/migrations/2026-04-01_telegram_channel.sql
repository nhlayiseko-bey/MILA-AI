-- Incremental migration for Telegram channel support and safer idempotency.

alter table employees
  add column if not exists telegram_chat_id text;

create unique index if not exists ux_employees_company_telegram_chat_id
  on employees(company_id, telegram_chat_id)
  where telegram_chat_id is not null;

alter table employees
  drop constraint if exists employees_channel_preference_check;

alter table employees
  add constraint employees_channel_preference_check
  check (channel_preference in ('slack', 'whatsapp', 'telegram', 'none'));

alter table trigger_events
  drop constraint if exists trigger_events_channel_check;

alter table trigger_events
  add constraint trigger_events_channel_check
  check (channel in ('slack', 'whatsapp', 'telegram', 'calendar', 'internal'));

alter table consent_logs
  drop constraint if exists consent_logs_source_channel_check;

alter table consent_logs
  add constraint consent_logs_source_channel_check
  check (source_channel in ('slack', 'whatsapp', 'telegram', 'dashboard', 'web', 'internal'));
