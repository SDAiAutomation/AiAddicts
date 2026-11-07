# Story Visual — workflow du pilote (TEST, manuel) : mise en place unique

> Fichier : `.github/workflows/story-visual-pilot-worker.yml`. **Rien n'est lancé par cette PR** : le workflow ne s'exécute que sur déclenchement manuel,
> après approbation, depuis `growthos/mvp`, dans un environnement GitHub dédié. Le worker de production (`growthos-worker.yml`) n'est pas modifié et continue
> de refuser les récits illustrés (il ne reçoit jamais `STORY_VISUAL_ENABLED`).

## Pourquoi un workflow dédié
Le worker de production tourne toutes les 10 minutes avec les secrets **du dépôt** (base de production). Le réutiliser pour un pilote reviendrait à exécuter un
pipeline payant contre la production. Ce workflow est isolé par construction (vérifié par `tests/test_story_visual_pilot_workflow.py`) :
déclenchement manuel seul, branche `growthos/mvp` seule, environnement `story-visual-pilot` seul, **uniquement des secrets `PILOT_*`** (un environnement peut aussi lire
les secrets du dépôt de même nom : sans préfixe, un secret de test manquant retomberait silencieusement sur la production), refus de l'URL de la base de production,
confirmation textuelle **et** variable d'armement avant tout appel payant, **un seul job** (`worker.py --once`), le drapeau moteur posé à un seul endroit.

## Mise en place (une fois, par le propriétaire, dans GitHub)
1. **Base de test** prête et isolée (jamais la production) : migrations appliquées, administrateur de test créé, 3 requêtes SQL de contrôle exécutées (voir le dossier du pilote §5).
2. *Settings → Environments → New environment* : **`story-visual-pilot`**.
   - **Required reviewers : vous.** Le job attend alors votre approbation avant de démarrer (clés fournisseurs jamais exposées sans accord).
   - *Deployment branches* : « Selected branches » → `growthos/mvp` seulement.
3. **Secrets de l'environnement** (pas du dépôt) :
   `PILOT_SUPABASE_URL`, `PILOT_SUPABASE_ANON_KEY`, `PILOT_SUPABASE_SERVICE_ROLE_KEY` (base de TEST), `PILOT_ADMIN_USER_IDS` (UUID de l'administrateur de test),
   `PILOT_OPENAI_API_KEY`, `PILOT_ELEVENLABS_API_KEY` (poser ces deux clés en dernier).
4. **Variables de l'environnement** (non secrètes) :
   `PILOT_IMAGE_USD_EACH` (recommandé `0.012`), `PILOT_ELEVENLABS_USD_PER_1K_CHARS` (**votre tarif confirmé**, aucune valeur par défaut), `PILOT_VOICE_ID` (identifiant du catalogue),
   `PILOT_WORKER_ARMED` = `false` (ne le passer à `true` qu'au moment du pilote).
5. Aucun secret `PILOT_*` au niveau du dépôt.

Valeurs fixées dans le fichier (non modifiables par variable) : plafond `STORY_BUDGET_USD=1.00`, cible `0.50`, quota `1`, modèle `gpt-image-2.5-flare`, qualité `low`,
planificateur déclaré à 0 (aucun appel), rendu 0 $, stockage 0,01 $.

## Utilisation
1. **Pré-vérification (gratuite, hors ligne)** : *Actions → Story Visual pilot worker → Run workflow* sur `growthos/mvp`, mode `preflight`. Approuvez l'environnement. Le job refuse la
   base de production, vérifie la présence des secrets de test et affiche le verdict PRÊT / NON PRÊT (aucune valeur de secret n'est affichée). Aucun fournisseur, aucun worker.
2. Dans le site de test (flags du site posés par vous) : créer le projet, valider le script, **Simuler le lancement** (« Prêt »), puis, après votre autorisation, le lancement réel place UN item en file.
3. **Armer** : `PILOT_WORKER_ARMED=true`. *Run workflow*, mode `run`, confirmation `RUN-PAID-PILOT`. Après approbation, le job traite **au plus un** job
   (`worker.py --once`) ; la dépense est bornée par le plafond cumulé et le registre durable du moteur.
4. **Désarmer** immédiatement : `PILOT_WORKER_ARMED=false`.

## Arrêt d'urgence
- Remettre `PILOT_WORKER_ARMED=false` ou refuser l'approbation de l'environnement : aucun worker ne démarre.
- Annuler le run dans *Actions*. Le plafond cumulé empêche de toute façon de dépasser 1,00 $.

## Limites
- Le dépôt est **public** : les journaux d'Actions le sont aussi. Les secrets sont masqués et le pilote n'utilise que la fable d'exemple.
- L'approbation et la restriction de branche sont des réglages GitHub (§ mise en place) : le fichier ne peut pas les imposer ; sans elles, le garde-fou restant est la variable d'armement et la confirmation textuelle.
- Le worker traite la file de la **base de test** : elle ne doit contenir que l'épisode du pilote.

## Narration et durée cible
- Ordre d'exécution : **voix d'abord, images ensuite**. La durée de voix mesurée doit tenir dans la cible ±10 % ; sinon le job s'arrête (`NarrationOutOfTarget`) avant toute image payée et le **crédit est rendu** (exception à la règle « pas de remboursement après dépense »). Corriger la narration, puis relancer.
- La voix déjà payée est dans le cache disque (`voice_cache`) ; si le cache du worker est éphémère, une relance la repaie.
- `STORY_TTS_SPEED = 0.7` est calibré pour le pilote de 60 s ; une cible plus courte ou une langue plus lente peut sortir de ±10 %. La pause inter-scènes passe à 0,45 s.
- La clé de cache de la voix a changé : la première reprise après cette version repaie la voix.
