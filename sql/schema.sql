-- Human Purpose HR AI Gateway MVP schema
-- PostgreSQL / Supabase compatible

create extension if not exists pgcrypto;

create table if not exists companies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  domain text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists employees (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  slack_user_id text,
  whatsapp_phone text,
  telegram_chat_id text,
  teams_user_id text,
  email text,
  name text not null,
  manager_uuid uuid references employees(id) on delete set null,
  current_state text not null default 'idle'
    check (current_state in ('idle', 'prompted', 'awaiting', 'scored')),
  quiet_hours_start smallint not null default 22 check (quiet_hours_start between 0 and 23),
  quiet_hours_end smallint not null default 7 check (quiet_hours_end between 0 and 23),
  channel_preference text default 'slack'
    check (channel_preference in ('slack', 'whatsapp', 'telegram', 'none')),
  consent_given boolean not null default false,
  consented_at timestamptz,
  calendar_source text default 'google'
    check (calendar_source in ('google', 'outlook', 'none')),
  calendar_shared boolean not null default false,
  last_response_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create unique index if not exists ux_employees_company_slack_user_id
  on employees(company_id, slack_user_id)
  where slack_user_id is not null;

create unique index if not exists ux_employees_company_whatsapp_phone
  on employees(company_id, whatsapp_phone)
  where whatsapp_phone is not null;

create unique index if not exists ux_employees_company_telegram_chat_id
  on employees(company_id, telegram_chat_id)
  where telegram_chat_id is not null;

create unique index if not exists ux_employees_company_teams_user_id
  on employees(company_id, teams_user_id)
  where teams_user_id is not null;

create unique index if not exists ux_employees_company_email
  on employees(company_id, email)
  where email is not null;

create index if not exists ix_employees_company_state on employees(company_id, current_state);
create index if not exists ix_employees_manager on employees(manager_uuid);

create table if not exists trigger_events (
  id uuid primary key default gen_random_uuid(),
  employee_uuid uuid not null references employees(id) on delete cascade,
  company_id uuid not null references companies(id) on delete cascade,
  source_event_id text,
  channel text not null check (channel in ('slack', 'whatsapp', 'telegram', 'calendar', 'internal')),
  event_type text not null,
  content_hash text not null,
  metadata jsonb not null default '{}'::jsonb,
  delivery_status text not null default 'pending'
    check (delivery_status in ('pending', 'delivered', 'failed')),
  provider_message_id text,
  delivery_error text,
  delivery_updated_at timestamptz,
  created_at timestamptz not null default now(),
  processed_at timestamptz
);

create unique index if not exists ux_trigger_events_channel_source_event_id
  on trigger_events(channel, source_event_id)
  where source_event_id is not null;

create index if not exists ix_trigger_events_company_created_at
  on trigger_events(company_id, created_at desc);

create index if not exists ix_trigger_events_employee_created_at
  on trigger_events(employee_uuid, created_at desc);

create index if not exists ix_trigger_events_delivery_status
  on trigger_events(delivery_status, created_at desc);

create table if not exists processed_events (
  id uuid primary key default gen_random_uuid(),
  trigger_event_uuid uuid references trigger_events(id) on delete set null,
  employee_uuid uuid not null references employees(id) on delete cascade,
  sentiment_score double precision check (sentiment_score between -1 and 1),
  emotion_label text,
  engagement_level text check (engagement_level in ('low', 'med', 'high')),
  flag boolean not null default false,
  flag_reason text,
  reply_text text,
  triggered_rule_id text,
  processed_at timestamptz not null default now(),
  check ((flag = false) or (flag_reason is not null))
);

create index if not exists ix_processed_events_employee_processed_at
  on processed_events(employee_uuid, processed_at desc);

create index if not exists ix_processed_events_trigger_event_uuid
  on processed_events(trigger_event_uuid);

create table if not exists scores (
  id uuid primary key default gen_random_uuid(),
  employee_uuid uuid not null references employees(id) on delete cascade,
  mood_score double precision check (mood_score between 0 and 100),
  meeting_load_score double precision check (meeting_load_score between 0 and 1),
  alignment_score double precision,
  alignment_gap double precision,
  flag_raised boolean not null default false,
  period_start date,
  period_end date,
  computed_at timestamptz not null default now()
);

create index if not exists ix_scores_employee_computed_at
  on scores(employee_uuid, computed_at desc);

create table if not exists flags (
  id uuid primary key default gen_random_uuid(),
  employee_uuid uuid not null references employees(id) on delete cascade,
  score_uuid uuid references scores(id) on delete set null,
  severity text not null check (severity in ('low', 'medium', 'high', 'critical')),
  reason text not null,
  resolution_status text not null default 'open'
    check (resolution_status in ('open', 'in_progress', 'resolved', 'dismissed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  resolved_at timestamptz
);

create index if not exists ix_flags_employee_resolution_status
  on flags(employee_uuid, resolution_status, created_at desc);

create table if not exists consent_logs (
  id uuid primary key default gen_random_uuid(),
  employee_uuid uuid not null references employees(id) on delete cascade,
  consent_given boolean not null,
  source_channel text not null check (source_channel in ('slack', 'whatsapp', 'telegram', 'dashboard', 'web', 'internal')),
  recorded_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists ix_consent_logs_employee_recorded_at
  on consent_logs(employee_uuid, recorded_at desc);

create table if not exists dead_letter_queue (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  source_event_id text,
  payload jsonb not null default '{}'::jsonb,
  error_message text not null,
  retry_count integer not null default 0,
  resolved boolean not null default false,
  resolved_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists ix_dead_letter_queue_resolved_created_at
  on dead_letter_queue(resolved, created_at desc);

create table if not exists system_logs (
  id uuid primary key default gen_random_uuid(),
  level text not null check (level in ('debug', 'info', 'warning', 'error', 'critical')),
  component text not null,
  message text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists ix_system_logs_created_at on system_logs(created_at desc);
create index if not exists ix_system_logs_component_created_at on system_logs(component, created_at desc);

create table if not exists system_health (
  id uuid primary key default gen_random_uuid(),
  component text not null,
  status text not null check (status in ('ok', 'degraded', 'failed', 'unknown')),
  details jsonb not null default '{}'::jsonb,
  checked_at timestamptz not null default now()
);

create index if not exists ix_system_health_component_checked_at
  on system_health(component, checked_at desc);

create or replace function set_updated_at_timestamp()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_employees_set_updated_at on employees;
create trigger trg_employees_set_updated_at
before update on employees
for each row
execute procedure set_updated_at_timestamp();

drop trigger if exists trg_flags_set_updated_at on flags;
create trigger trg_flags_set_updated_at
before update on flags
for each row
execute procedure set_updated_at_timestamp();

alter table companies enable row level security;
alter table employees enable row level security;
alter table trigger_events enable row level security;
alter table processed_events enable row level security;
alter table scores enable row level security;
alter table flags enable row level security;
alter table consent_logs enable row level security;
alter table dead_letter_queue enable row level security;
alter table system_logs enable row level security;
alter table system_health enable row level security;
