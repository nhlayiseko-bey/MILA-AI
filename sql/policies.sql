-- Supabase RLS policies for Human Purpose HR AI Gateway
-- Expected JWT claims for authenticated users:
-- - company_id (uuid)
-- - employee_id (uuid)
-- - role (e.g. manager)

drop policy if exists service_role_companies_all on companies;
create policy service_role_companies_all on companies
  for all to service_role
  using (true)
  with check (true);

drop policy if exists service_role_employees_all on employees;
create policy service_role_employees_all on employees
  for all to service_role
  using (true)
  with check (true);

drop policy if exists service_role_trigger_events_all on trigger_events;
create policy service_role_trigger_events_all on trigger_events
  for all to service_role
  using (true)
  with check (true);

drop policy if exists service_role_processed_events_all on processed_events;
create policy service_role_processed_events_all on processed_events
  for all to service_role
  using (true)
  with check (true);

drop policy if exists service_role_scores_all on scores;
create policy service_role_scores_all on scores
  for all to service_role
  using (true)
  with check (true);

drop policy if exists service_role_flags_all on flags;
create policy service_role_flags_all on flags
  for all to service_role
  using (true)
  with check (true);

drop policy if exists service_role_consent_logs_all on consent_logs;
create policy service_role_consent_logs_all on consent_logs
  for all to service_role
  using (true)
  with check (true);

drop policy if exists service_role_dead_letter_queue_all on dead_letter_queue;
create policy service_role_dead_letter_queue_all on dead_letter_queue
  for all to service_role
  using (true)
  with check (true);

drop policy if exists service_role_system_logs_all on system_logs;
create policy service_role_system_logs_all on system_logs
  for all to service_role
  using (true)
  with check (true);

drop policy if exists service_role_system_health_all on system_health;
create policy service_role_system_health_all on system_health
  for all to service_role
  using (true)
  with check (true);

drop policy if exists authenticated_companies_select on companies;
create policy authenticated_companies_select on companies
  for select to authenticated
  using (id = (auth.jwt() ->> 'company_id')::uuid);

drop policy if exists authenticated_employees_select on employees;
create policy authenticated_employees_select on employees
  for select to authenticated
  using (
    company_id = (auth.jwt() ->> 'company_id')::uuid
    and deleted_at is null
  );

drop policy if exists authenticated_trigger_events_select on trigger_events;
create policy authenticated_trigger_events_select on trigger_events
  for select to authenticated
  using (company_id = (auth.jwt() ->> 'company_id')::uuid);

drop policy if exists authenticated_processed_events_select on processed_events;
create policy authenticated_processed_events_select on processed_events
  for select to authenticated
  using (
    exists (
      select 1
      from employees e
      where e.id = processed_events.employee_uuid
        and e.company_id = (auth.jwt() ->> 'company_id')::uuid
        and e.deleted_at is null
    )
  );

drop policy if exists authenticated_scores_select on scores;
create policy authenticated_scores_select on scores
  for select to authenticated
  using (
    exists (
      select 1
      from employees e
      where e.id = scores.employee_uuid
        and e.company_id = (auth.jwt() ->> 'company_id')::uuid
        and e.deleted_at is null
    )
  );

drop policy if exists authenticated_flags_select on flags;
create policy authenticated_flags_select on flags
  for select to authenticated
  using (
    exists (
      select 1
      from employees e
      where e.id = flags.employee_uuid
        and e.company_id = (auth.jwt() ->> 'company_id')::uuid
        and e.deleted_at is null
    )
  );

drop policy if exists authenticated_consent_logs_select on consent_logs;
create policy authenticated_consent_logs_select on consent_logs
  for select to authenticated
  using (
    exists (
      select 1
      from employees e
      where e.id = consent_logs.employee_uuid
        and e.company_id = (auth.jwt() ->> 'company_id')::uuid
        and e.deleted_at is null
    )
  );

drop policy if exists employee_self_select on employees;
create policy employee_self_select on employees
  for select to authenticated
  using (
    id = (auth.jwt() ->> 'employee_id')::uuid
    and deleted_at is null
  );

drop policy if exists employee_self_scores_select on scores;
create policy employee_self_scores_select on scores
  for select to authenticated
  using (employee_uuid = (auth.jwt() ->> 'employee_id')::uuid);

drop policy if exists employee_self_processed_events_select on processed_events;
create policy employee_self_processed_events_select on processed_events
  for select to authenticated
  using (employee_uuid = (auth.jwt() ->> 'employee_id')::uuid);

drop policy if exists employee_self_consent_logs_select on consent_logs;
create policy employee_self_consent_logs_select on consent_logs
  for select to authenticated
  using (employee_uuid = (auth.jwt() ->> 'employee_id')::uuid);

drop policy if exists manager_team_employees_select on employees;
create policy manager_team_employees_select on employees
  for select to authenticated
  using (
    (auth.jwt() ->> 'role') = 'manager'
    and manager_uuid = (auth.jwt() ->> 'employee_id')::uuid
    and company_id = (auth.jwt() ->> 'company_id')::uuid
    and deleted_at is null
  );
