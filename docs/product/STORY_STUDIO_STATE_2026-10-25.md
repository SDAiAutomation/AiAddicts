# Story Studio animé — état au 2026-10-25 (point d'arrêt de la session)

Document de reprise. Tout ce qui est écrit ici a été fait ou mesuré pendant la session ; ce qui n'a pas été vérifié est dit comme tel.

## 1. En production (fusionné)
| Élément | Où | État |
| --- | --- | --- |
| Éditeur animé (4 étapes : Projet, Personnages, Scènes en poste de travail, Aperçu), propositions IA contraintes | growthos-web `master` (PR #156, #157) | fusionné, Vercel redéployé |
| Choix du style : `noir_1930`, `sepia_1930`, `cyanotype_1930`, `couleur_1930` | web #158, #159 ; moteur #87, #88 | fusionné |
| Correction « main devant la bouche » (`point`) + couche de vie du rig | moteur #86 | fusionné |
| Le worker principal ne réclame plus les histoires animées | moteur #85 | fusionné |
| Pack `prototype_v1` et pack `couleur_v1` (23 PNG + manifeste SHA-256 chacun) | bucket privé Supabase `story-packs` | publiés, téléchargement vérifié |
| Variable de dépôt GitHub `STORY_ANIMATION_ENABLED=true` ; variable Vercel production `STORY_ANIMATION_ENABLED=1` | GitHub / Vercel | posées |
| Migration du bucket `story-packs` | projet Supabase partagé (`lclesqfokgetznhepgmj`) | appliquée (aucune politique : accès service role seulement) |

Une vidéo réelle a été générée avant les correctifs (« La pendule hypnotique », 33 s, 1080×1920, voix et sous-titres alignés). **Aucune vidéo n'a encore été générée avec les correctifs, ni avec le style couleur.**

## 2. Chantier en cours : qualité d'écriture des histoires
Constat : `Proposer les scènes avec l'IA` utilise `gpt-5-mini` (défaut de `OPENAI_SCRIPT_MODEL`) et produit des dialogues plats. La clé OpenAI donne accès à des modèles bien plus forts (`gpt-5.5` listé).

Banc d'essai : `experiments/story_writing/bench.py` (non commité, non fusionné). 12 idées × 3 systèmes (A = production actuelle, C = même prompt sur `gpt-5.5`, B = écriture en passes : 4 idées de départ → choix → écriture → relecture/réécriture selon une grille de 9 critères), jugés à l'aveugle deux fois (ordre inversé).
Résultats partiels au moment de l'arrêt (10 concepts sur 12) : B gagne contre A à chaque jugement, C gagne contre A à chaque jugement, B gagne contre C la grande majorité du temps. **Juge = modèle, pas public** : à confirmer en montrant des paires de textes à l'utilisateur.
Risques déjà vus : B peut s'éloigner de l'idée de départ ou être obscur ; deux critères (clarté et fidélité) ont été ajoutés avant le banc complet.

Reprise du banc : `python experiments/story_writing/bench.py <dossier> --only <numéros manquants>` (clé lue dans `~/story_studio_work/.openai_key`, plafond de 1,2 M de jetons). Résultats : `~/story_studio_work/bench1/bench.json`.

## 3. Prochaines étapes proposées
1. Finir le banc, présenter 3 paires de textes à l'utilisateur, décider.
2. Si B est retenu : le brancher dans `animated-ai-actions.ts` à la place de l'appel unique (mêmes catalogues, mêmes validations `sanitizeProposedShots`), choisir le modèle par variable d'environnement, chiffrer le coût par proposition.
3. Générer une vidéo de test réelle (style couleur) pour valider la chaîne complète : worker Linux, pack couleur, correctifs de pose.
4. Plus tard : nouveaux personnages (bibliothèque qui grandit, un par un), voir la discussion « personnages vs histoire » (l'histoire passe en premier).

## 4. Points qui restent à la charge du propriétaire
- Relecture juridique des conditions OpenAI et ElevenLabs avant toute diffusion publique (images et voix).
- Validation visuelle de Pip et Rosette et des styles.
- Mode sombre de l'éditeur, parcours connecté complet, rendu Linux du pack couleur : non vérifiés.
- Ancienne variable Vercel `STORY_GENERATION_ENABLED=1` (plus lue par le code) : à supprimer si souhaité.

## 5. Coûts engagés
Images OpenAI : environ 0,60 $ estimé au total depuis le début (journal `experiments/story_gate1/out/cost_ledger.json`, non commité). Voix ElevenLabs : une génération de test. Texte OpenAI du banc : de l'ordre de 150 000 à 200 000 jetons.
