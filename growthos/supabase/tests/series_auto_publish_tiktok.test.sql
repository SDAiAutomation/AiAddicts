-- Test pgTAP de 20261107120000_series_auto_publish_tiktok.sql. NON EXÉCUTÉ (pas de Postgres local dans la session).
-- Les contraintes sont exercées sur des copies temporaires (LIKE ... INCLUDING CONSTRAINTS) pour ne pas dépendre
-- des clés étrangères accounts/content_items ; rien n'est écrit dans les tables réelles (rollback final).
begin;
select plan(13);

create temp table series_probe (like public.series including defaults including constraints);
create temp table jobs_probe (like public.content_publication_jobs including defaults including constraints);

-- series.auto_publish_platforms
select lives_ok($$insert into series_probe (account_id, name, auto_publish_platforms)
  values (gen_random_uuid(), 'probe', array['youtube'])$$, 'series: youtube still accepted');
select lives_ok($$insert into series_probe (account_id, name, auto_publish_platforms)
  values (gen_random_uuid(), 'probe', array['tiktok'])$$, 'series: tiktok accepted');
select lives_ok($$insert into series_probe (account_id, name, auto_publish_platforms)
  values (gen_random_uuid(), 'probe', array['youtube', 'tiktok'])$$, 'series: youtube + tiktok accepted');
select throws_ok($$insert into series_probe (account_id, name, auto_publish_platforms)
  values (gen_random_uuid(), 'probe', array['instagram'])$$, '23514', null, 'series: unknown platform refused');
insert into series_probe (account_id, name) values (gen_random_uuid(), 'default');
select is((select auto_publish_platforms from series_probe where name = 'default'), '{}'::text[],
  'series: default unchanged (empty array)');

-- content_publication_jobs.platform
select lives_ok($$insert into jobs_probe (content_item_id, platform) values (gen_random_uuid(), 'youtube')$$,
  'jobs: youtube still accepted');
select lives_ok($$insert into jobs_probe (content_item_id, platform) values (gen_random_uuid(), 'tiktok')$$,
  'jobs: tiktok accepted');
select throws_ok($$insert into jobs_probe (content_item_id, platform) values (gen_random_uuid(), 'instagram')$$,
  '23514', null, 'jobs: unknown platform refused');

-- The old youtube-only constraints are replaced, not stacked.
select is((select count(*)::int from pg_constraint c join pg_attribute a
             on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
           where c.conrelid = 'public.series'::regclass and c.contype = 'c' and a.attname = 'auto_publish_platforms'),
  1, 'series: exactly one check on auto_publish_platforms');
select is((select count(*)::int from pg_constraint c join pg_attribute a
             on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
           where c.conrelid = 'public.content_publication_jobs'::regclass and c.contype = 'c' and a.attname = 'platform'),
  1, 'jobs: exactly one check on platform');

-- RLS and privileges unchanged.
select ok((select relrowsecurity from pg_class where oid = 'public.content_publication_jobs'::regclass),
  'jobs: RLS still enabled');
select policies_are('public', 'content_publication_jobs', array['publication_jobs_member_select'],
  'jobs: only the member SELECT policy exists');
select ok(not has_table_privilege('authenticated', 'public.content_publication_jobs', 'insert')
          and not has_table_privilege('authenticated', 'public.content_publication_jobs', 'update')
          and not has_table_privilege('authenticated', 'public.content_publication_jobs', 'delete'),
  'jobs: clients still cannot write publication jobs');

select * from finish();
rollback;
