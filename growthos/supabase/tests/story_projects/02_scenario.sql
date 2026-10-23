\set ON_ERROR_STOP off
\set A 00000000-0000-0000-0000-00000000000a
\set B 00000000-0000-0000-0000-00000000000b
set test.uid='11111111-1111-1111-1111-111111111111'; set role authenticated;
\echo == editor creates a draft in own org; created_by forced to caller even if spoofed (expect 1 row, created_by 1111)
insert into story_projects(organization_id,title,created_by) values (:'A','Mon histoire','33333333-3333-3333-3333-333333333333') returning title,status,created_by;
\echo == editor cannot create in another org (1 error)
insert into story_projects(organization_id,title) values (:'B','Intrus');
\echo == status other than draft refused (1 error)
update story_projects set status='rendered';
\echo == oversize / malformed payloads refused (3 errors)
update story_projects set characters='{"a":1}';
update story_projects set shots=(select jsonb_agg('{}'::jsonb) from generate_series(1,31));
update story_projects set title=repeat('x',121);
\echo == organization_id and created_by cannot be changed (expect A, 1111)
update story_projects set organization_id=:'B', created_by='33333333-3333-3333-3333-333333333333' returning organization_id,created_by;
\echo == save and resume: update then read back (expect 2 characters)
update story_projects set characters='[{"id":"neo","name":"Néo","voice_id":"v1"},{"id":"orion","name":"Orion","voice_id":"v2"}]', shots='[{"id":"shot_01","speaker_id":"neo","dialogue":"Salut","duration_s":4}]';
select title,jsonb_array_length(characters) as n_chars,jsonb_array_length(shots) as n_shots from story_projects;
reset role;
\echo == viewer reads (1 row) but cannot write (update affects 0 rows, insert errors)
set test.uid='22222222-2222-2222-2222-222222222222'; set role authenticated;
select count(*) from story_projects;
update story_projects set title='hack';
insert into story_projects(organization_id,title) values (:'A','viewer write');
delete from story_projects;
reset role;
\echo == other org owner sees 0 rows and cannot update/delete the other org project (0, 0 rows)
set test.uid='33333333-3333-3333-3333-333333333333'; set role authenticated;
select count(*) as other_org_rows from story_projects;
update story_projects set title='hack' returning id;
delete from story_projects returning id;
reset role;
\echo == anon has no access (1 error)
set role anon; select count(*) from story_projects;
reset role;
\echo == untouched title and updated_at advanced (expect Mon histoire, true)
select title, updated_at > created_at as touched from story_projects;
