# Story Studio — Gate 5 : revue de sécurité, de confidentialité et de droits (2026-10-25)

Revue **en lecture seule** : aucun code modifié, aucun appel payant, aucun déploiement, aucun drapeau changé (l'animation reste éteinte, décision D1). Chaque constat dit ce qui a été lu et ce qui ne l'a pas été. Ce n'est pas un avis juridique. Sources externes : synthèses secondaires, à recouper sur les conditions officielles.

## 1. Workflow dédié `story-animation-worker.yml` (porte les secrets de production)
| # | Constat | Gravité | Proposition |
| --- | --- | --- | --- |
| S1 | **Bon** : déclenchement manuel seul, aucun `pull_request`, `permissions: contents: read`, `concurrency` sans annulation, ignoré sans la variable de dépôt `STORY_ANIMATION_ENABLED`, secrets limités à ce qu'un rendu animé utilise (service role Supabase, ElevenLabs, OpenAI et Anthropic pour la modération, `ADMIN_USER_IDS`) | — | garder |
| S2 | Les actions tierces sont référencées par **étiquette**, pas par empreinte de commit (`actions/checkout@v4`, `actions/setup-python@v5`) alors que le job porte des secrets de production | moyenne | épingler par SHA de commit (étiquettes lues le 2026-10-25 : `checkout` v4 → `11d5960a…`, `setup-python` v5 → `a26af69b…` ; à vérifier qu'il s'agit bien du commit, pas d'un objet d'étiquette annotée) |
| S3 | **Godot** : la somme SHA-512 vient du même dépôt de versions que l'archive ; elle protège d'un téléchargement corrompu, pas d'une version piégée | moyenne | épingler dans le dépôt la somme attendue de l'archive 4.7.2 (une valeur constante revue) |
| S4 | Dépendances Python **épinglées en version** (`requests`, `supabase`, `Pillow`…) mais sans empreintes ; paquets `apt` non épinglés | faible | acceptable ; empreintes (`--require-hashes`) si exigé plus tard |
| S5 | **Aucune isolation réseau** du sous-processus Godot (déjà documentée dans `rig_v1.py`) ; son environnement est filtré (les variables contenant KEY, SECRET, TOKEN, PASSWORD, CREDENTIAL sont retirées) mais le sous-processus pourrait appeler Internet | moyenne | lancer Godot dans un espace de noms réseau vide sur le runner (`unshare -n`), avec un test qui vérifie qu'il ne peut pas joindre un hôte |
| S6 | Tout détenteur du droit d'écriture peut déclencher le workflow (donc l'utiliser avec les secrets) | moyenne | rattacher le job à un **environnement GitHub protégé** avec relecteur requis, et y déplacer les secrets |
| S7 | Entrées du rendu : dialogue, noms et décors sont validés par un contrat fermé ; un texte n'est jamais interprété, seulement dessiné ; les chemins de packs viennent d'une table fermée ; le pack est vérifié par SHA-256 avant usage | — | garder (tests présents) |

## 2. Données, crédits, accès
- **Positif** : modération avant toute dépense et avant la réservation du crédit ; réservation et remboursement idempotents, testés ; réclamation par mise à jour conditionnée (deux workers ne prennent jamais le même contenu) ; accès réservé aux administrateurs de la plateforme ; bucket `story-packs` privé sans politique ; vidéos dans `content-videos` (privé, limite de 200 Mio).
- **À noter** : aucun test de bout en bout du chemin Standard et Quiz n'a été relancé pour ce chantier ; seuls les tests unitaires (identiques à ceux d'avant, mêmes 3 erreurs antérieures) l'ont été.

## 3. Confidentialité (RGPD)
- La page de confidentialité liste déjà **ElevenLabs** (synthèse vocale du texte des scripts), **OpenAI**, Supabase, Vercel, GitHub (worker), Stripe, Google/YouTube, Pexels et les plateformes sociales.
- **Écart** : **Anthropic n'y figure pas**, alors que la seconde couche de modération (`engine/moderation.py`, Claude Haiku) reçoit le texte des scripts, y compris celui des histoires animées. À ajouter à la liste des sous-traitants. Écart préexistant pour Standard, que Story Studio hérite.
- Les dialogues des histoires partent chez ElevenLabs et les services de modération : à dire clairement à l'utilisateur au moment de la génération (la mention payante existe, la mention de transmission non).

## 4. Droits d'usage (non vérifiés à la source)
| Sujet | Ce qui a été lu | Risque / à faire |
| --- | --- | --- |
| Voix ElevenLabs | synthèses secondaires : les forfaits payants incluent une licence commerciale ; l'audio produit **pendant** l'abonnement est utilisable commercialement ; celui produit hors abonnement ne l'est pas ; pas d'attribution exigée en payant (inférence) | confirmer sur les conditions officielles et le forfait Creator ; **l'arrêt de l'abonnement pourrait priver de droits les audios existants** : décision commerciale à prendre |
| Images OpenAI (sprites, décors) | les conditions disent que l'utilisateur possède les sorties, réserve légale « dans la mesure permise par la loi » ; sortie non exclusive ; protection par le droit d'auteur incertaine ; garanties d'indemnisation à confirmer | confirmer sur les conditions officielles ; garder la preuve d'origine (journal de coût, prompts) ; ne pas prétendre à l'exclusivité |
| Ressemblance des personnages | Pip et Rosette sont originaux mais dans un style « rubber hose » à gants blancs très répandu | revue par un juriste pour la ressemblance avec des personnages existants avant diffusion publique |
| Voix locale libre (Piper `mls`, Kokoro) | rapport séparé (`STORY_STUDIO_LOCAL_TTS_LICENSES_2026-10-25.md`) | seule piste à 0 € ; non retenue pour l'instant |

## 5. Divulgation « contenu IA » à la publication
- **TikTok** : `is_aigc: true` est toujours envoyé (`lib/tiktok/publish-rules.ts`). OK.
- **YouTube** : la charge utile d'envoi (`lib/youtube/publish.ts`) fixe `privacyStatus` et `selfDeclaredMadeForKids` mais **n'envoie pas** le champ `status.containsSyntheticMedia`, disponible depuis l'API de fin octobre 2024. Les règles de YouTube portent sur le contenu réaliste ; un dessin animé manifestement irréel n'est en principe pas concerné, mais **la règle actuelle n'a pas été relue** et d'autres vidéos Faceloop (images réalistes) pourraient l'être. Écart préexistant, à instruire séparément.

## 6. Critères GO / NO-GO avant toute réactivation
| Critère | État |
| --- | --- |
| Contrat, pipeline, qualité, crédits : tests verts | **OK** |
| Rendu Linux d'une histoire complète avec les deux packs | **non fait** (l'outil de mesure rend un clip court) |
| S2, S3, S6 corrigés (actions épinglées, Godot épinglé, environnement protégé) | **non fait** |
| S5 (isolation réseau de Godot) | **non fait** |
| Anthropic ajouté à la confidentialité | **non fait** |
| Droits ElevenLabs et OpenAI confirmés sur les conditions officielles | **non fait** |
| Revue juridique de la ressemblance des personnages | **non fait** |
| Validation humaine de l'art et de l'audio | **en attente de l'utilisateur** |
**Décision : NO-GO pour toute ouverture au public.** GO possible pour des essais internes du propriétaire seul, après S2, S3 et S6, avec l'animation allumée uniquement le temps de l'essai.

## 7. Correctifs que je peux préparer (zéro coût)
1. PR workflow : actions épinglées par SHA, somme Godot épinglée, `environment:` protégé (le relecteur se règle dans GitHub, par vous), test statique de non-régression.
2. PR web : ajouter Anthropic aux sous-traitants (FR/EN) et une phrase de transmission lors de la génération.
3. PR moteur : isolation réseau de Godot (`unshare -n`) avec un test, à valider sur le runner.
