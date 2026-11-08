-- A executer sur une base locale ou de branche, jamais en production :
--   psql "$LOCAL_DB_URL" -v ON_ERROR_STOP=1 -f <ce fichier>
-- Tout est annule par le rollback final.
begin;

insert into auth.users (id, email) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'a@test.invalid'),
  ('bbbbbbbb-0000-4000-8000-000000000001', 'b@test.invalid')
on conflict do nothing;

insert into public.organizations (id, name) values
  ('aaaaaaaa-0000-4000-8000-000000000002', 'A'),
  ('bbbbbbbb-0000-4000-8000-000000000002', 'B');
-- Le declencheur handle_new_user a pu creer d'autres appartenances : seules celles-ci comptent ici.
delete from public.organization_members where user_id in ('aaaaaaaa-0000-4000-8000-000000000001', 'bbbbbbbb-0000-4000-8000-000000000001');
insert into public.organization_members (organization_id, user_id, role) values
  ('aaaaaaaa-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000001', 'owner'),
  ('bbbbbbbb-0000-4000-8000-000000000002', 'bbbbbbbb-0000-4000-8000-000000000001', 'owner');
insert into public.accounts (id, organization_id, handle, platform) values
  ('aaaaaaaa-0000-4000-8000-000000000003', 'aaaaaaaa-0000-4000-8000-000000000002', 'a', 'instagram');
insert into public.content_items (id, account_id, title) values
  ('aaaaaaaa-0000-4000-8000-000000000004', 'aaaaaaaa-0000-4000-8000-000000000003', 'T');
insert into public.account_oauth_tokens (account_id, platform, encrypted_access_token, status, external_account_id)
values ('aaaaaaaa-0000-4000-8000-000000000003', 'instagram', '\x00', 'insufficient_scope', '178');
insert into public.social_publications (organization_id, account_id, content_item_id, platform, target_external_id, status)
values ('aaaaaaaa-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000003', 'aaaaaaaa-0000-4000-8000-000000000004', 'instagram', '178', 'processing');

do $$ begin
  begin
    insert into public.social_publications (organization_id, account_id, content_item_id, platform, target_external_id)
    values ('aaaaaaaa-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000003', 'aaaaaaaa-0000-4000-8000-000000000004', 'instagram', '178');
    raise exception 'double publication acceptee';
  exception when unique_violation then null; end;
end $$;

set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"bbbbbbbb-0000-4000-8000-000000000001","role":"authenticated"}', true);
do $$ begin
  if exists (select 1 from public.social_publications) then raise exception 'fuite inter-organisation'; end if;
  begin
    perform encrypted_access_token from public.account_oauth_tokens;
    raise exception 'jeton chiffre lisible';
  exception when insufficient_privilege then null; end;
  begin
    update public.social_publications set status = 'published';
    raise exception 'ecriture client acceptee';
  exception when insufficient_privilege then null; end;
end $$;

select set_config('request.jwt.claims', '{"sub":"aaaaaaaa-0000-4000-8000-000000000001","role":"authenticated"}', true);
do $$ begin
  if (select count(*) from public.social_publications) <> 1 then raise exception 'membre sans acces a sa publication'; end if;
  -- Colonnes exactes lues par les pages sous le role authenticated.
  perform status, error_code, permalink, created_at, content_item_id, platform from public.social_publications;
  perform account_id, status, expires_at, external_username, granted_scopes, platform from public.account_oauth_tokens;
end $$;
reset role;
rollback;
