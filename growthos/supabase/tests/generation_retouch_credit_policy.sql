-- Test de la politique « 1 retouche gratuite » (migration 20261003120000).
-- À exécuter APRÈS la migration, sur une base jetable ou de test. Le bloc se
-- termine TOUJOURS par une exception : tout ce qu'il crée est annulé, et le
-- rapport PASS/FAIL est lu dans le message d'erreur.
do $test$
declare
  v_org uuid; v_acc uuid; v_item uuid;
  v_res text[] := '{}';
  v_ok boolean; v_bal integer; v_pack integer; v_held integer;
begin
  insert into organizations (name) values ('l0-test') returning id into v_org;
  update organizations set credits_balance = 5, pack_credits = 0 where id = v_org;
  insert into accounts (organization_id, platform, handle) values (v_org, 'tiktok', 'l0-test') returning id into v_acc;
  insert into content_items (account_id, title) values (v_acc, 'l0-test') returning id into v_item;

  -- S1/S2 : run 1 débite une fois, le rejeu ne redébite pas
  v_ok := reserve_generation_credit(v_item);
  select credits_balance into v_bal from organizations where id = v_org;
  v_res := v_res || ((case when v_ok and v_bal = 4 then 'PASS' else 'FAIL' end) || ' S1 run1 débite 1');
  v_ok := reserve_generation_credit(v_item);
  select credits_balance into v_bal from organizations where id = v_org;
  v_res := v_res || ((case when v_ok and v_bal = 4 then 'PASS' else 'FAIL' end) || ' S2 rejeu/double clic sans second débit');

  -- S3 : échec du run 1 -> remboursement, une seule fois
  v_ok := refund_generation_credit(v_item);
  select credits_balance into v_bal from organizations where id = v_org;
  v_res := v_res || ((case when v_ok and v_bal = 5 then 'PASS' else 'FAIL' end) || ' S3 échec run1 rembourse');
  v_ok := refund_generation_credit(v_item);
  select credits_balance into v_bal from organizations where id = v_org;
  v_res := v_res || ((case when not v_ok and v_bal = 5 then 'PASS' else 'FAIL' end) || ' S3b second remboursement refusé');

  -- S4 : run 1 réussi, puis retouche gratuite
  perform reserve_generation_credit(v_item);
  perform mark_generation_completed(v_item);
  v_ok := reserve_generation_credit(v_item);
  select credits_balance into v_bal from organizations where id = v_org;
  v_res := v_res || ((case when v_ok and v_bal = 4 then 'PASS' else 'FAIL' end) || ' S4 retouche gratuite (solde inchangé)');

  -- S4b : échec de la retouche -> rien à rembourser
  v_ok := refund_generation_credit(v_item);
  select credits_balance into v_bal from organizations where id = v_org;
  v_res := v_res || ((case when not v_ok and v_bal = 4 then 'PASS' else 'FAIL' end) || ' S4b échec retouche : pas de remboursement du run 1');

  -- S5 : retouche réussie, run 3 payant, rejeu sans second débit
  perform mark_generation_completed(v_item);
  v_ok := reserve_generation_credit(v_item);
  select credits_balance into v_bal from organizations where id = v_org;
  v_res := v_res || ((case when v_ok and v_bal = 3 then 'PASS' else 'FAIL' end) || ' S5 run3 payant');
  v_ok := reserve_generation_credit(v_item);
  select credits_balance into v_bal from organizations where id = v_org;
  v_res := v_res || ((case when v_ok and v_bal = 3 then 'PASS' else 'FAIL' end) || ' S5b rejeu run3 sans second débit');

  -- S6 : échec du run 3 -> rembourse uniquement le run 3
  v_ok := refund_generation_credit(v_item);
  select credits_balance into v_bal from organizations where id = v_org;
  select coalesce(-sum(delta), 0) into v_held from credits_ledger where related_content_item_id = v_item;
  v_res := v_res || ((case when v_ok and v_bal = 4 and v_held = 1 then 'PASS' else 'FAIL' end) || ' S6 échec run3 rembourse seulement run3');
  v_ok := refund_generation_credit(v_item);
  v_res := v_res || ((case when not v_ok then 'PASS' else 'FAIL' end) || ' S6b second remboursement refusé');

  -- S7 : solde nul -> retouche gratuite possible, run payant refusé
  update content_items set completed_generations = 1 where id = v_item;
  update organizations set credits_balance = 0 where id = v_org;
  v_ok := reserve_generation_credit(v_item);
  v_res := v_res || ((case when v_ok then 'PASS' else 'FAIL' end) || ' S7 retouche gratuite possible à solde 0');
  update content_items set completed_generations = 3 where id = v_item;
  v_ok := reserve_generation_credit(v_item);
  v_res := v_res || ((case when not v_ok then 'PASS' else 'FAIL' end) || ' S7b run payant refusé à solde 0');

  -- S8 : pack consommé en dernier, remboursé vers le pack
  update organizations set credits_balance = 1, pack_credits = 1 where id = v_org;
  delete from credits_ledger where related_content_item_id = v_item;
  update content_items set completed_generations = 0 where id = v_item;
  v_ok := reserve_generation_credit(v_item);
  select credits_balance, pack_credits into v_bal, v_pack from organizations where id = v_org;
  v_res := v_res || ((case when v_ok and v_bal = 0 and v_pack = 0 then 'PASS' else 'FAIL' end) || ' S8 débit sur le pack');
  v_ok := refund_generation_credit(v_item);
  select credits_balance, pack_credits into v_bal, v_pack from organizations where id = v_org;
  v_res := v_res || ((case when v_ok and v_bal = 1 and v_pack = 1 then 'PASS' else 'FAIL' end) || ' S8b remboursement vers le pack');

  -- S9 : plan business illimité
  update organizations set plan = 'business', credits_balance = 0 where id = v_org;
  v_ok := reserve_generation_credit(v_item);
  v_res := v_res || ((case when v_ok then 'PASS' else 'FAIL' end) || ' S9 business illimité');

  raise exception 'L0_RESULT: %', array_to_string(v_res, ' | ');
end
$test$;
