# Story Studio animé — options explorées et feuille de route (note du chef de projet)

Date : 2026-10-24. Document de décision, **aucun code, aucune activation**. Légende : **[VÉRIFIÉ]** mesuré ou lu ; **[SOURCE TIERCE]** non confirmé à la source ; **[ESTIMATION]** jugement, jamais une mesure.

## 0. Ce que nous savons vraiment (base de toutes les décisions)
| Fait | Valeur | Statut |
| --- | --- | --- |
| Rendu 21,6 s en 1080×1920 sur `ubuntu-latest` (xvfb + OpenGL logiciel, pack synthétique) | 51,5 s rendu + 19 s encodage, 4 Mio | **VÉRIFIÉ** (run 40115329358), un seul échantillon |
| Voix : 393 caractères ElevenLabs pour l'histoire de démonstration | ≈ 0,07 USD au tarif du workflow (0,18 USD / 1 000 caractères) | calcul d'après la configuration, **ESTIMATION** |
| Images du prototype complet (personnages, expressions, 4 décors, accessoire) | ≈ 0,24 USD | table de coûts du dépôt, **ESTIMATION** |
| Coût d'une régénération Standard citée par la migration des crédits | ≈ 0,34 USD | commentaire de migration, **non vérifié** |
| Quota ElevenLabs du compte (Creator) | 121 032 caractères/mois, 30 043 utilisés à l'audit | **VÉRIFIÉ** par l'API d'abonnement |
| Production | l'animation **ne peut pas** tourner (flag non transmis, pas de Godot, pas de pack sur le runner) | **VÉRIFIÉ**, voulu |
Lecture économique **[ESTIMATION]** : une vidéo animée d'environ 22 s coûte surtout la voix (de l'ordre de 0,07 à 0,10 USD) ; le rendu est gratuit tant que le dépôt est public (minutes illimitées, note du workflow) et coûterait de l'ordre de 0,02 à 0,03 USD s'il devenait privé (tarif Linux 2 cœurs 0,006 USD/min, arrondi à la minute, **SOURCE TIERCE : documentation GitHub**). Le coût marginal est donc très inférieur à un Standard à images IA ; le vrai coût est la production des packs.

## 1. Distribution des packs de personnages vers le runner (bloquant)
| Option | Pour | Contre | Avis |
| --- | --- | --- | --- |
| **A. Bucket privé Supabase `story-packs` + manifeste SHA-256, téléchargé au début du job** | pas de binaire dans Git, droits contrôlés, même fournisseur que le reste | nouveau bucket à créer et à protéger (RLS, clé de service dans le job) | **Recommandée** |
| B. Git LFS dans un dépôt privé | historique, versions | quotas LFS payants, second dépôt à gérer | repli |
| C. Fichier de release d'un dépôt privé | simple | gestion de jetons, peu auditable | non |
| D. Image conteneur privée contenant Godot + pack | démarrage rapide, reproductible | registre, build, taille | à étudier si un runner dédié est choisi |
| E. Committer les sprites dans le dépôt public | zéro infrastructure | expose des actifs dont les droits ne sont pas vérifiés | **refusée** |

## 2. Où rendre
| Option | Pour | Contre | Avis |
| --- | --- | --- | --- |
| **A. Dans le job existant du worker** | zéro infrastructure, mesuré | la file est **en série** : une animation retarde Standard/Quiz ; le job porte les secrets de production | acceptable pour la bêta fermée |
| **B. Workflow dédié à l'animation (même runner, autre file)** | isole les retards et les secrets (on ne donne que ce qui est nécessaire), temps de job propre | un workflow de plus, file à détecter | **Recommandée dès la 2ᵉ étape** |
| C. Runner auto-hébergé (PC ou petit serveur) | pas de minutes facturées | maintenance, disponibilité, sécurité | non pour l'instant |
| D. Conteneur serverless (type Cloud Run / Modal) | montée en charge | nouveau fournisseur, nouveau coût **non mesuré**, gestion de secrets | à reconsidérer si la bêta dépasse quelques dizaines de vidéos/jour |
| E. GPU | — | **inutile** : le rendu logiciel suffit pour de la 2D | refusée |

## 3. Généraliser la scène (aujourd'hui limitée aux six répliques du prototype)
| Option | Pour | Contre | Avis |
| --- | --- | --- | --- |
| **A. Modèles d'épisode** (3 à 4 trames écrites à la main : accusation, dispute, révélation, poursuite) où le créateur change dialogues, décors et ambiance | qualité maîtrisée, livrable vite, cohérent avec « pas de fabrique de contenus interchangeables » si les trames sont variées | liberté limitée | **Recommandée en premier** |
| B. Scène pilotée par le contrat (gestes, humeurs, plans décrits dans le JSON) | liberté, extensible | gros chantier Godot, risque de plans maladroits non relus | **en second**, après retours de la bêta |
| C. Rester sur le prototype | rien à faire | aucune valeur produit | non |
| D. Nouveau rig pour d'autres personnages | variété | coût d'illustration élevé | après validation de la demande |

## 4. Produire les personnages et les décors
| Option | Coût | Qualité | Avis |
| --- | --- | --- | --- |
| **A. Génération par l'API déjà utilisée + relecture humaine** | ≈ 0,24 USD le prototype **[ESTIMATION]** | correcte, dérive possible entre variantes (observée) | **bêta** |
| B. Illustrateur humain | **inconnu** (devis à demander) | la plus haute, droits clairs | **dès que la demande est prouvée** et pour les personnages vedettes |
| C. Image→vidéo par un fournisseur externe | non mesuré | mouvement riche, cohérence faible | **écartée par l'utilisateur** (pas de service dépendant supplémentaire) |
| D. Banque d'assets achetée | variable | variable | à étudier pour les décors |

## 5. Musique et bruitages
| Option | Droits | Avis |
| --- | --- | --- |
| **Synthèse locale originale** (actuelle) | aucune licence à vérifier | **garder** pour la bêta |
| Bibliothèque sous licence | à lire licence par licence | plus tard |
| Eleven Music | page de conditions du produit introuvable (404) ; **SOURCE TIERCE** : restrictions possibles pour pub/TV/jeux | non tant que non lu |
| Aucune musique | — | repli |

## 6. Synchronisation labiale
| Option | Avis |
| --- | --- |
| **Alignement par caractère du fournisseur de voix + enveloppe audio** (actuel) | **garder** : mesuré, gratuit, multilingue |
| Rhubarb Lip Sync | reconnaissance anglaise par défaut, licence **non vérifiée** (« other » selon un agrégateur) : **non** |
| Modèle de visèmes entraîné | surdimensionné pour 2D simple : non |

## 7. Qualité et revue humaine
Aujourd'hui un échec qualité rembourse et échoue. Options : (A) échec simple [actuel], (B) état « à revoir » avec aperçu et décision du créateur [**recommandé avant la bêta ouverte**, doctrine : « les problèmes de qualité non résolus exigent un état de revue »], (C) revue interne systématique avant livraison (coûteux en temps).

## 8. Produit et prix
- Positionnement : **séries avec personnages récurrents** (la valeur que les chaînes à images fixes n'ont pas), pas « une vidéo de plus ».
- Prix en crédits : **1 crédit** en bêta (décision prise, réversible) ; réévaluer avec des coûts réels ; si le coût marginal reste bas, l'animé peut être un argument d'acquisition plutôt qu'un produit premium.
- Mesure : « coût par vidéo satisfaisante » (événements `generation_*` + `video_declared_satisfied`, **[VÉRIFIÉ]** schéma).

## 9. Droits et conformité (bloquant avant diffusion)
OpenAI : page officielle inaccessible, sources tierces : l'utilisateur est propriétaire de la sortie, usage commercial permis sous conditions, **pas de garantie de droit d'auteur** sur une image IA ⇒ protéger la **marque et le système** (continuité, séries), pas le dessin seul. ElevenLabs : usage commercial sur plans payants (conditions lues) ; conditions « OEM/revente » **non lues**. Divulgation de contenu IA sur les plateformes à respecter. **Décision requise : relecture par un juriste avant toute diffusion.**

## 10. Critères d'arrêt (pour ne pas s'enliser)
Arrêter ou redimensionner si : (1) les droits ne sont pas clarifiés d'ici la fin de la bêta fermée ; (2) moins de la moitié des vidéos de la bêta sont déclarées satisfaisantes par leurs auteurs ; (3) le coût mesuré par vidéo dépasse un seuil à fixer avec le prix du crédit ; (4) la file d'animation dégrade les délais Standard/Quiz.

## 11. Feuille de route recommandée
| Étape | Contenu | Dépend de |
| --- | --- | --- |
| R1 | Décision et construction de la distribution des packs (option 1A) + workflow dédié (2B) | revue humaine du diff (secrets) |
| R2 | Modèles d'épisode (3A) avec variété de trames | R1 |
| R3 | État « à revoir » (7B) | R2 |
| R4 | Relecture juridique (9) | indépendant, **à lancer maintenant** |
| R5 | Bêta fermée (5 administrateurs, 20 vidéos) avec les requêtes du runbook | R1–R4 |
| R6 | Bilan chiffré contre les critères d'arrêt ; décision d'illustrateur / généralisation (3B) | R5 |

## 12. Décisions prises par le chef de projet dans ce document (réversibles)
Packs : bucket privé (1A). Hébergement : job existant pour la bêta, workflow dédié ensuite (2A→2B). Scène : modèles d'épisode d'abord (3A). Musique : synthèse locale (5). Lip-sync : alignement fournisseur (6). Prix : 1 crédit en bêta (8). **Non décidé, revient à l'utilisateur** : la relecture juridique (9) et l'engagement d'un illustrateur (4B).
