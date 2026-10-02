begin;
select plan(12);

select ok(not has_table_privilege('anon', 'public.credits_ledger', 'select,insert,update,delete,truncate'),
  'anon has no ledger access');
select ok(has_table_privilege('authenticated', 'public.credits_ledger', 'select'),
  'authenticated can read its RLS-filtered ledger');
select ok(not has_table_privilege('authenticated', 'public.credits_ledger', 'insert,update,delete,truncate'),
  'authenticated cannot forge ledger entries');
select ok(not has_function_privilege('anon', 'public.enforce_account_limit()', 'execute'),
  'anon cannot execute the account-limit trigger');
select ok(not has_function_privilege('authenticated', 'public.enforce_account_limit()', 'execute'),
  'authenticated cannot execute the account-limit trigger');
select ok(not has_function_privilege('authenticated', 'public.consume_ai_quota(uuid,text,integer)', 'execute'),
  'authenticated cannot choose quota arguments');
select ok(has_function_privilege('service_role', 'public.consume_ai_quota(uuid,text,integer)', 'execute'),
  'the server can consume AI quota');
select ok(not has_function_privilege('authenticated', 'public.consume_security_rate_limit(text,integer,integer)', 'execute'),
  'the rate limiter is server-only');
select ok(not has_function_privilege('authenticated', 'public.create_autoedit_job(uuid,uuid,text,text,numeric,text,text,text,integer)', 'execute'),
  'atomic AutoEdit admission is server-only');
select ok(not has_table_privilege('authenticated', 'public.autoedit_jobs', 'insert'),
  'AutoEdit rows cannot bypass atomic admission');
select ok(not has_function_privilege('authenticated', 'public.grant_plan_credits(uuid,integer,text,text)', 'execute'),
  'plan credit grants are server-only');
select ok(not exists (
  select 1
  from information_schema.role_table_grants
  where table_schema = 'public' and grantee = 'anon'
    and table_name in (
      'organizations','profiles','organization_members','accounts','strategies',
      'content_items','content_performance','insights','recommendations',
      'credits_ledger','niches','series','content_publication_jobs','ai_usage',
      'autoedit_jobs','security_rate_limits'
    )
), 'anon has no application-table grants');

select * from finish();
rollback;
