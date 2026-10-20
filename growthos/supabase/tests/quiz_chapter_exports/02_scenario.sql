\set ON_ERROR_STOP off
\set I d0000000-0000-0000-0000-000000000001
set test.role='authenticated'; set test.uid='11111111-1111-1111-1111-111111111111'; set role authenticated;
\echo == editor requests 1,2 (expect 2 pending rows)
select chapter,status from request_quiz_chapter_export(:'I',array[1,2]);
\echo == repeat is idempotent
select chapter,status,attempts from request_quiz_chapter_export(:'I',array[1,2]);
\echo == invalid chapter / empty / 6 chapters (expect 3 errors)
select * from request_quiz_chapter_export(:'I',array[0]);
select * from request_quiz_chapter_export(:'I',array[]::int[]);
select * from request_quiz_chapter_export(:'I',array[1,2,3,4,5,1]);
\echo == legacy quiz and unrendered video refused (2 errors)
select * from request_quiz_chapter_export('d0000000-0000-0000-0000-000000000002',array[1]);
select * from request_quiz_chapter_export('d0000000-0000-0000-0000-000000000003',array[1]);
\echo == direct writes blocked (3 errors)
insert into quiz_chapter_exports(content_item_id,chapter) values (:'I',3);
update quiz_chapter_exports set status='ready';
select storage_paths from quiz_chapter_exports;
\echo == safe columns readable (2 rows)
select chapter,status,outputs from quiz_chapter_exports order by chapter;
\echo == viewer cannot request
set test.uid='22222222-2222-2222-2222-222222222222';
select * from request_quiz_chapter_export(:'I',array[3]);
\echo == viewer in org A can read (2 rows); org B owner sees 0 rows, and cannot request
select count(*) from quiz_chapter_exports;
set test.uid='33333333-3333-3333-3333-333333333333';
select count(*) as other_org_rows from quiz_chapter_exports;
select * from request_quiz_chapter_export(:'I',array[3]);
reset role;
\echo == worker claim, finish, retry
set test.role='service_role'; set role service_role;
select chapter,status,attempts from claim_quiz_chapter_export();
update quiz_chapter_exports set status='failed', error='x' where chapter=1;
update quiz_chapter_exports set status='ready', outputs='[{"file":"quiz_medium.mp4"}]', storage_paths='{"quiz_medium.mp4":"p"}' where chapter=2;
reset role;
set test.role='authenticated'; set test.uid='11111111-1111-1111-1111-111111111111'; set role authenticated;
select chapter,status,attempts from request_quiz_chapter_export(:'I',array[1,2]);
\echo == claim by authenticated is forbidden (1 error)
select * from claim_quiz_chapter_export();
reset role;
\echo == ready on a NEW version re-queues with attempts reset
update content_items set current_version_id='c0000000-0000-0000-0000-000000000002' where id=:'I';
update quiz_chapter_exports set status='ready', attempts=5, source_version_id='c0000000-0000-0000-0000-000000000001' where chapter=2;
set test.role='authenticated'; set role authenticated;
select chapter,status,attempts from request_quiz_chapter_export(:'I',array[2]);
reset role;
\echo == 5 failed attempts block retry
update quiz_chapter_exports set status='failed', attempts=5 where chapter=1;
set test.role='authenticated'; set role authenticated;
select chapter,status,attempts from request_quiz_chapter_export(:'I',array[1]);
reset role;
\echo == stale processing job reclaimed
update quiz_chapter_exports set status='processing', attempts=4, updated_at=now()-interval '2 hours' where chapter=2;
set test.role='service_role'; set role service_role;
select chapter,status,attempts,error from claim_quiz_chapter_export();
reset role;
select chapter,status,attempts from quiz_chapter_exports order by chapter;
\echo == series constraint
insert into series(content_format,quiz_config) values ('quiz','{"topic":"t","recipe":"long","question_count":50,"difficulty":"progressive","chapter_mode":"five_levels"}');
insert into series(content_format,quiz_config) values ('quiz','{"topic":"t","recipe":"long","question_count":40,"difficulty":"progressive","chapter_mode":"five_levels"}');
insert into series(content_format,quiz_config) values ('quiz','{"topic":"t","recipe":"long","question_count":25,"difficulty":"progressive"}');
