# Continuité du narrateur — revue du 12 octobre 2026

## Correction implémentée après réattribution explicite à Codex

Le créateur a demandé « fais tout, toi même » après la revue ci-dessous. Le correctif est maintenant appliqué dans le checkout `growthos-web`, sans déploiement ni modification des épisodes existants.

- `src/lib/narrative-perspective.ts` centralise les règles versionnées et la relecture sémantique. Les dialogues attribués, autres personnages et CTA sont explicitement distingués d'une bascule du narrateur. Aucune regex de comptage des pronoms.
- `ai-actions.ts` applique les règles aux générations manuelles, séries, transformations et suggestions de hook. Après les contrôles déterministes, une relecture indépendante alimente la boucle existante : deux générations maximum, une relecture par tentative, pas de nouvelle boucle. Une incohérence persistante ou une relecture indisponible ne renvoie pas de blocs acceptés. Le mode préserver sort toujours avant tout appel IA.
- Les variantes de hook et corrections de bloc sont vérifiées chacune insérée dans le récit entier, avec le récit initial comme référence. Les alternatives incohérentes sont retirées sans attribuer leurs défauts au script original.
- Une relecture coûte un appel supplémentaire : plafond de 20 secondes, 2 048 tokens de sortie, huit variantes et 64 000 caractères d'entrée sérialisée. Les tokens mesurés sont comptés ; les mesures incomplètes sont signalées. Pour les scripts, ils rejoignent `script_usage` ; pour la revue de hook, l'usage du générateur et celui du vérificateur sont retournés séparément car leurs modèles diffèrent. Cette réponse n'ajoute pas de persistance de coût au flux de revue de hook existant.
- La version est conservée dans l'usage et les reçus de recommandation manuels, transformations et séries. Aucun second contrat de script/job, aucune migration ni nouveau réglage utilisateur.

Validation : tests de parsing strict, panne/troncature du fournisseur, usage incomplet, plafond d'entrée, réécriture bornée, refus après deux tentatives, filtrage des suggestions et comptabilisation par modèle ; tests d'intégration de génération et recommandations ; TypeScript et lint ciblé.

Calibration réelle du 12 octobre, sur huit exemples fictifs courts (pas des scripts de SD-Faceloop), couvrant fr/en/de/es/it/pt :

| Cas | Attendu | gpt-5-mini |
| --- | --- | --- |
| Léa passe de je à elle, français | Signaler | Signalé |
| Dialogue cité de Léa puis elle, français | Accepter | Accepté |
| I puis he désignant le frère, anglais | Accepter | Accepté |
| Récit au je puis CTA au tu, français | Accepter | Accepté |
| Anna passe de ich à sie, allemand | Signaler | Signalé |
| Récit cohérent à la première personne, espagnol | Accepter | Accepté |
| Dialogue attribué à Luca, italien | Accepter | Accepté |
| Ana passe de eu à ela, portugais | Signaler | Signalé |

`gpt-5-mini` : 8/8 attendus, 8,827 s, 767 tokens d'entrée et 901 de sortie mesurés. Ce petit échantillon n'est pas une garantie de détection générale.

Le même essai avec `gpt-5-nano` a signalé à tort les cinq cas cohérents (parfois avec une justification disant elle-même « aucun changement »), en 18,856 s, 767 tokens d'entrée et 2 002 de sortie. Il n'est donc pas utilisé comme vérificateur : la revue des variantes emploie le modèle de script (`OPENAI_SCRIPT_MODEL`, défaut `gpt-5-mini`) et conserve son usage séparé. Le modèle de proposition des variantes reste inchangé. Un changement de modèle configuré mérite une nouvelle calibration.

## Revue initiale (historique)

Signalement : certaines histoires du compte SD-Faceloop alternent première et troisième personne. Aucun script de ce compte ni trace de génération n'a été consulté : la cause propre aux épisodes reste à confirmer. Cette revue porte sur le checkout local `growthos-web` et le moteur Python, pas sur la version déployée.

## Constats vérifiés

- `growthos-web/src/app/(app)/content/ai-actions.ts`, `buildBasePrompt`, vers ligne 133 : le registre tu/vous doit rester constant, mais aucune règle équivalente ne fixe l'identité du narrateur et la personne du récit.
- Même fichier, `scriptIssues`, lignes 376–405 : vérifie notamment longueur, rôles, répétitions et diversité des plans ; ne contrôle pas la continuité du narrateur.
- Même fichier, demande de réécriture, ligne 449 : conserve sujet, progression et résolution, sans demander explicitement de conserver le narrateur.
- Même fichier, `HOOK_SYSTEM_PROMPT`, lignes 1099–1100 : les variantes de hook et corrections de blocs préservent la langue et le rôle, sans contrainte explicite de point de vue. C'est une voie possible de dérive, pas une origine démontrée.
- `engine/retention.py`, `_FIRST_PERSON_RE` et `find_first_person_anecdotes`, lignes 401–447 : détection de certaines expériences au passé en français/anglais ; ce n'est pas un contrôle de perspective. `unsupported_first_person`, lignes 1287–1296, est informatif pour un seul bloc et désactivé pour un texte importé. Ne pas détourner ce diagnostic pour bloquer toute fiction au « je ».

## Correction proposée au propriétaire de l'orchestration

Claude Code possède cette implémentation selon `AGENTS.md`. Aucun changement exécutable ni modification de compte effectué pendant cette revue.

Ajouter à la génération commune une instruction versionnée :

> Continuité du narrateur : détermine avant d'écrire qui raconte et à quelle personne. Respecte le point de vue explicitement demandé dans le brief, le texte source ou la mémoire validée de la série. Sinon, choisis un point de vue adapté au récit et conserve-le du hook à la résolution. Ne transforme jamais le même personnage de « je » en « il/elle » sans transition narrative explicitement demandée. Les paroles citées appartiennent à leur locuteur ; les mentions d'autres personnages et l'adresse au spectateur ne changent pas le narrateur. Le point de vue d'un plan visuel (POV) ne détermine pas la personne de la voix off. Relis tous les blocs pour vérifier cette continuité.

Ajouter à chaque réécriture complète et à la revue hook/blocs :

> Préserve l'identité du narrateur, la personne de narration et l'attribution des paroles du récit fourni. Une accroche alternative doit pouvoir remplacer l'accroche actuelle sans changer qui raconte. Si le récit mélange déjà les points de vue de façon incohérente, signale les blocs concernés et harmonise selon l'intention explicite ; ne décide pas à partir d'un simple comptage des pronoms.

Brancher le contrôle sémantique sur la revue qualité existante, avec les blocs concernés et une justification. Ne pas créer un second moteur ni un nouveau contrat parallèle. Réutiliser le budget de reprises et l'état de revue existants ; ne pas déclencher de boucle autonome supplémentaire. Ne pas modifier automatiquement un texte importé en mode préserver. Pas de réglage UI supplémentaire ni de préférence de compte inventée.

Une règle de prompt seule réduit le risque sans garantir la cohérence. Une regex « je + il » ne convient pas : elle confond dialogues, autres personnages et changement de narrateur. Tout contrôle sémantique supplémentaire doit tracer version, coût et tentative dans les mécanismes existants.

## Vérification attendue lors de l'implémentation

- Rejeter une bascule où le même protagoniste raconte « J'ai ouvert la porte » puis devient « Léa entre » sans transition, si Léa est bien le narrateur établi.
- Accepter « J'ai ouvert la porte. Il m'attendait » : deux personnages différents.
- Accepter « Léa murmure : “Je reviendrai.” Elle ferme la porte » : dialogue attribué dans un récit à la troisième personne.
- Accepter un CTA adressé au spectateur et un plan visuel POV sans les interpréter comme un changement du narrateur.
- Préserver une fiction cohérente à la première personne ; ne pas la convertir systématiquement à la troisième personne.
- Vérifier génération, réécriture de longueur, variante de hook et correction isolée de bloc, dans les langues prises en charge.
- Préserver strictement le texte importé en mode préserver ; signaler une incohérence sans réécriture silencieuse.
- Confirmer sur un épisode SD-Faceloop : script enregistré, brief/mémoire, versions de prompts et réécritures disponibles. Comparer avant/après pour identifier l'étape responsable. Ne pas présenter les exemples de cette revue comme des extraits du compte.
