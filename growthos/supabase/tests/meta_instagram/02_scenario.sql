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

-- Membre des deux organisations et membre en lecture seule de A.
insert into auth.users (id, email) values
  ('cccccccc-0000-4000-8000-000000000001', 'c@test.invalid'),
  ('dddddddd-0000-4000-8000-000000000001', 'd@test.invalid')
on conflict do nothing;
delete from public.organization_members where user_id in ('cccccccc-0000-4000-8000-000000000001', 'dddddddd-0000-4000-8000-000000000001');
insert into public.organization_members (organization_id, user_id, role) values
  ('aaaaaaaa-0000-4000-8000-000000000002', 'cccccccc-0000-4000-8000-000000000001', 'editor'),
  ('bbbbbbbb-0000-4000-8000-000000000002', 'cccccccc-0000-4000-8000-000000000001', 'editor');

do $$
begin
  -- Idempotence : un echec libere la cible et garde l'historique ; une autre cible reste possible.
  update public.social_publications set status = 'failed', error_code = 'meta_rejected' where target_external_id = '178';
  insert into public.social_publications (organization_id, account_id, content_item_id, platform, target_external_id, status)
  values ('aaaaaaaa-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000003', 'aaaaaaaa-0000-4000-8000-000000000004', 'instagram', '178', 'published');
  if (select count(*) from public.social_publications) <> 2 then raise exception 'historique des tentatives perdu'; end if;
  begin
    insert into public.social_publications (organization_id, account_id, content_item_id, platform, target_external_id)
    values ('aaaaaaaa-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000003', 'aaaaaaaa-0000-4000-8000-000000000004', 'instagram', '178');
    raise exception 'republication acceptee';
  exception when unique_violation then null; end;
  insert into public.social_publications (organization_id, account_id, content_item_id, platform, target_external_id)
  values ('aaaaaaaa-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000003', 'aaaaaaaa-0000-4000-8000-000000000004', 'instagram', '999');
  delete from public.social_publications where target_external_id = '999';

  -- Contraintes de valeur.
  begin update public.account_oauth_tokens set status = 'bogus'; raise exception 'statut accepte'; exception when check_violation then null; end;
  begin update public.account_oauth_tokens set auth_flow = 'bogus'; raise exception 'flux accepte'; exception when check_violation then null; end;
  begin update public.social_publications set permalink = 'http://x'; raise exception 'lien non https accepte'; exception when check_violation then null; end;
  begin update public.social_publications set status = 'bogus'; raise exception 'statut publication accepte'; exception when check_violation then null; end;

  -- TikTok et YouTube restent valides sans les nouvelles colonnes.
  insert into public.account_oauth_tokens (account_id, platform, encrypted_access_token) values ('aaaaaaaa-0000-4000-8000-000000000003', 'tiktok', '\x00');

  -- Horodatage automatique, y compris sur une ecriture service.
  update public.account_oauth_tokens set last_checked_at = clock_timestamp() where platform = 'instagram';
  -- now() est fige dans la transaction : on verifie que le declencheur existe et s'execute sans erreur.
  if not exists (select 1 from pg_trigger where tgname = 'account_oauth_tokens_touch') then raise exception 'declencheur absent'; end if;

  -- Droits exacts de chaque role.
  if has_table_privilege('anon', 'public.social_publications', 'select') then raise exception 'anon lit les publications'; end if;
  if has_column_privilege('authenticated', 'public.account_oauth_tokens', 'encrypted_access_token', 'select') then raise exception 'jeton accessible'; end if;
  if has_column_privilege('authenticated', 'public.account_oauth_tokens', 'encrypted_refresh_token', 'select') then raise exception 'refresh accessible'; end if;
  if has_column_privilege('authenticated', 'public.account_oauth_tokens', 'external_business_id', 'select') then raise exception 'portefeuille accessible'; end if;
  if has_column_privilege('authenticated', 'public.social_publications', 'container_id', 'select') then raise exception 'conteneur accessible'; end if;
  if has_table_privilege('authenticated', 'public.social_publications', 'insert,update,delete') then raise exception 'ecriture client possible'; end if;
  if not has_table_privilege('service_role', 'public.social_publications', 'select,insert,update,delete') then raise exception 'serveur sans droit'; end if;
  if not has_table_privilege('service_role', 'public.account_oauth_tokens', 'select,insert,update,delete') then raise exception 'serveur sans droit sur les jetons'; end if;
end $$;

set local role service_role;
do $$ begin
  update public.social_publications set poll_count = poll_count + 1 where target_external_id = '178';
  if not found then raise exception 'service_role ne peut pas ecrire'; end if;
end $$;
reset role;

set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"bbbbbbbb-0000-4000-8000-000000000001","role":"authenticated"}', true);
do $$ begin
  if exists (select 1 from public.social_publications) then raise exception 'fuite inter-organisation'; end if;
  if exists (select 1 from public.account_oauth_tokens where platform = 'instagram') then raise exception 'connexion visible par une autre organisation'; end if;
  begin
    perform encrypted_access_token from public.account_oauth_tokens;
    raise exception 'jeton chiffre lisible';
  exception when insufficient_privilege then null; end;
  begin
    update public.social_publications set status = 'published';
    raise exception 'ecriture client acceptee';
  exception when insufficient_privilege then null; end;
  begin
    insert into public.social_publications (organization_id, account_id, content_item_id, platform, target_external_id)
    values ('aaaaaaaa-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000003', 'aaaaaaaa-0000-4000-8000-000000000004', 'instagram', 'x');
    raise exception 'insertion client acceptee';
  exception when insufficient_privilege then null; end;
end $$;

select set_config('request.jwt.claims', '{"sub":"cccccccc-0000-4000-8000-000000000001","role":"authenticated"}', true);
do $$ begin
  if (select count(*) from public.social_publications) <> 2 then raise exception 'membre multi-organisation sans acces a A'; end if;
end $$;

select set_config('request.jwt.claims', '{"sub":"dddddddd-0000-4000-8000-000000000001","role":"authenticated"}', true);
do $$ begin
  if exists (select 1 from public.social_publications) then raise exception 'non-membre voit des publications'; end if;
end $$;

select set_config('request.jwt.claims', '{"sub":"aaaaaaaa-0000-4000-8000-000000000001","role":"authenticated"}', true);
do $$ begin
  if (select count(*) from public.social_publications) <> 2 then raise exception 'membre sans acces a sa publication'; end if;
  -- Colonnes exactes lues par les pages sous le role authenticated.
  perform status, error_code, permalink, created_at, content_item_id, platform from public.social_publications;
  perform account_id, status, expires_at, external_username, granted_scopes, platform from public.account_oauth_tokens;
end $$;

reset role;
do $$ begin
  -- Suppression du contenu : pas de ligne orpheline.
  delete from public.content_items where id = 'aaaaaaaa-0000-4000-8000-000000000004';
  if exists (select 1 from public.social_publications) then raise exception 'publications orphelines'; end if;
end $$;
rollback;
