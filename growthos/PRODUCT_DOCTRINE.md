# La bible Faceloop — doctrine produit 2026–2028

## Mission et critère de décision

**The AI Content Engine for creators.** Faceless creation remains the first focus, but the platform will eventually support both generated stories and creator-owned footage.

Promesse : **Idea → Story → Video → Publish → Learn → Next Idea**.
Le passage visé est de « titre → génération » à « objectif créateur → boucle de contenu ». GrowthOS est le nom technique du moteur existant ; cette doctrine ne demande pas de renommer ses modules.

Chaque décision doit améliorer au moins une dimension : qualité, originalité, rétention, simplicité, vitesse, fiabilité ou économie unitaire. La qualité prime sur le volume. Le succès est une vidéo qui mérite d'être regardée et publiée, puis un apprentissage utile pour la suivante.

Les prescriptions ci-dessous décrivent la cible. Elles ne prouvent pas que les capacités sont implémentées.

## Deux moteurs complémentaires

### Faceloop Generate

`Idée → script → voix → images/vidéos → Short`

C'est le moteur actuellement construit. Il produit une histoire originale à partir d'une intention créative et applique les contrôles P0 de narration, originalité et cohérence visuelle.

### Faceloop AutoEdit

`Rushes utilisateur → compréhension IA → meilleurs moments → plan de montage → Short`

AutoEdit est un second moteur produit, pas une option ajoutée au générateur. Il transforme des vidéos apportées par l'utilisateur ou sous licence en contenus courts. Le même socle doit pouvoir servir au sport, gaming, podcasts, vlogs, fitness, interviews, éducation et automobile. Chaque catégorie devient un profil d'analyse et de règles de montage, plutôt qu'un éditeur séparé.

## P0 — qualité avant extension

### Story Engine 2.0 et hooks

Pipeline cible : idée → cinq hooks candidats → architecture narrative → vérification factuelle selon le mode → scènes → revue de rétention → contrôle d'originalité → script → direction visuelle.

Noter les hooks sur curiosité, précision, enjeux et clarté ; conserver les candidats et la justification de sélection. Éviter les accroches génériques telles que « You won't believe » et « What happened next shocked everyone ». La promesse du hook doit être tenue par la conclusion.

Bibliothèque d'archétypes : mystère/révélation, loyauté inattendue, découverte impossible, transformation, course contre la montre, animal incompris, mystère historique, relation humain–animal, identité cachée, intelligence inattendue, survie, réaction en chaîne, question non résolue. Varier selon l'historique ; ne pas transformer cette bibliothèque en scénarios interchangeables. Pour les animaux, explorer aussi comédie, aventure et amitié inter-espèces.

### Originalité et anti-répétition

Comparer le concept puis le script aux 20 dernières vidéos disponibles du même compte : concept, personnage, situation, environnement, hook, progression, twist, conclusion, vocabulaire et composition visuelle. Isoler strictement les historiques par compte et organisation.

Produire les ressemblances par dimension, les vidéos concernées et une proposition substantiellement différente. Un simple changement de noms ne suffit pas. Un personnage récurrent ou une intro commune ne constitue pas, à lui seul, un doublon.

Avec moins de 20 vidéos, utiliser l'historique disponible et afficher sa couverture. Sans historique, signaler que la comparaison historique est indisponible. Les seuils sont à calibrer sur des exemples annotés ; aucun score ne certifie la monétisation. Prévoir des réécritures plafonnées, puis une revue si le problème persiste.

### Visual Director et continuité

Passer de « paragraphe → image » à « script → scènes → plans ». Chaque plan décrit narration, durée, cadrage, sujet, action, environnement, lumière, émotion et personnages présents. Varier les compositions avec intention narrative.

Chaque personnage possède une identité stable : espèce, âge, silhouette, pelage/peau, yeux, vêtements, accessoires et traits distinctifs. Réinjecter cette identité uniquement dans les plans où il apparaît. Conserver également les états des lieux, objets, météo et heure ; justifier leurs changements dans le récit.

Réutiliser `engine/image_character_bible.py`, `engine/image_style_bible.py`, `engine/image_prompt_builder.py` et le contrôle qualité existant. L'injection textuelle réduit les dérives sans prouver la cohérence des images rendues : la validation doit aussi examiner les sorties.

### Prompts, fournisseurs, coûts et traçabilité

Centraliser les prompts dans un registre versionné (ex. `story-generator:v1`, `visual-director:v1`). Chaque génération référence exactement les versions utilisées.

Construire progressivement une interface interne par tâche : `generate_script`, `generate_hook`, `analyze_story`, `generate_image`, `generate_voice`, `analyze_video`. Les fournisseurs et modèles restent configurables derrière ces contrats ; un gateway interne n'impose aucun fournisseur particulier.

Tracer projet, génération, tâche, fournisseur/modèle, version de prompt, usage, coût estimé ou réel, latence, erreur, tentative et résultat qualité. Séparer coûts de script, images, voix, rendu, stockage et reprises. Une donnée tarifaire manquante reste inconnue. Distinguer crédits produit, revenu attribué et marge ; ne pas inventer de marge sans revenu et coût complets.

Étendre le rapport de coûts existant dans `engine/assembler.py` et ses tests. Fixer un budget d'appels, de coût et de latence pour les corrections automatiques ; conserver le coût des tentatives échouées lorsqu'il est connu.

## Vérité, rétention et qualité

Chaque projet choisit `Fiction`, `Inspired Story` ou `Fact / Documentary`. Pour Fact, rechercher et associer les sources aux affirmations avant validation du script ; une affirmation non vérifiée reste explicitement non vérifiée. Pour Inspired Story, distinguer base documentée et dramatisation. Une fiction ne se présente pas comme un événement réel attesté.

Le moteur de rétention raisonne en secondes : hook, contexte, question, montée des enjeux, révélation, résolution. Une structure 0–2 / 2–7 / 7–15 / 15–25 / 25–34 / 34–40 secondes est un exemple, pas un template obligatoire. Détecter exposition longue, phrases inutiles, manque d'information nouvelle, plans similaires, conclusion prévisible et promesse faible.

Le contrôle qualité couvre histoire, hook, cohérence visuelle, audio, originalité et risques de rétention. Chaque score doit indiquer méthode, version et dimensions réellement évaluées. Une dimension non mesurée reste inconnue. Corriger dans les budgets prévus ; sinon passer en revue explicite. Aucune prédiction de vues n'est déduite du score.

## P1 — intelligence par chaîne

Le Channel Brain mémorise niche, audience, langue, ton, voix, style, personnages, hooks, formats, historique et performances. Réutiliser la boucle de `engine/learning.py` et ses niveaux de confiance plutôt que construire une mémoire concurrente.

Les tendances servent à extraire des mécanismes, jamais à copier les histoires observées. Toute croissance ou comparaison affichée doit avoir une source, une fenêtre temporelle, un échantillon et une méthode. Pas de pourcentages fictifs.

Brancher progressivement les analytics YouTube et proposer des insights actionnables : point de chute observé, hypothèse, modification à tester. Ne pas inférer une chute à une seconde précise à partir de statistiques agrégées. Conserver une part d'exploration et distinguer corrélation et causalité.

Boucle : créer → publier → mesurer → comprendre → proposer une hypothèse → créer. Après chaque vidéo : qu'avons-nous appris, avec quelle confiance, et quel test vient ensuite ?

## P2 — automatisation après maîtrise de la qualité

Parcours : génération → revue → programmation → publication. Préparer titre, description, hashtags, miniature/image de couverture, déclaration IA et horaire. Adapter chaque intégration à ses permissions et capacités réelles.

Évaluer les besoins de déclaration IA par plateforme et type de contenu ; conserver la décision et son motif, avec revue si incertain. Les recommandations de prochaine vidéo doivent être fondées sur les mesures disponibles. La roadmap n'autorise pas à publier sans instruction utilisateur.

## AutoEdit — architecture cible et ordre de livraison

Le modèle IA comprend et annote les rushes ; il ne monte pas directement la vidéo. Le pipeline cible est :

`upload → proxy/compression → détection de scènes et pics audio → extraction de frames → vision → événements → highlight scoring → Edit Decision List → moteur déterministe → musique/beat-sync → captions/overlays → auto-reframe 9:16 → export`

L'analyse coûteuse est exécutée une seule fois et les événements détectés sont conservés. Plusieurs montages (Hype, Best Skills, Goals & Assists, Player Highlight, Cinematic Recap) peuvent ensuite être planifiés à partir du même index.

L'`Edit Decision List` (EDL) est le contrat entre IA et rendu. Il contient au minimum la source, les timecodes de début et de fin, la vitesse, le type d'événement, la cible de recadrage, les effets et la confiance. Il doit être validé avant exécution, versionné, rejouable et testable sans appel IA. FFmpeg applique l'EDL ; le modèle reste un réalisateur qui propose des décisions.

Le MVP AutoEdit accepte des clips courts et commence par Sports. L'expérience demande uniquement le focus (meilleurs moments, buts, skills, joueur ou célébrations), le style (Hype, Cinematic, Clean, Emotional) et la durée (15, 30 ou 60 secondes). Le mode `Player Focus` suit un joueur identifié, par exemple `#17`, et peut produire plusieurs durées depuis la même analyse.

L'ordre est strict : terminer et solidifier Generate ; sortir AutoEdit MVP avec clips courts ; tester Sports auprès de vrais utilisateurs ; généraliser ensuite aux autres catégories. Ne pas maintenir deux pipelines incomplets en parallèle.

## P3 — expansion

Après validation du MVP, AutoEdit s'étend aux profils Gaming, Podcast, Vlog, Fitness, Interview, Education et Auto. Sports AutoEdit couvre les médias apportés par l'utilisateur ou sous licence, la détection de scènes/actions, la sélection de moments, le focus joueur, le rythme musical, le recadrage, les ralentis, les sous-titres et l'export. Puis viennent analytics TikTok/Reels, équipes, API et usages agences.

Ne pas mener simultanément toutes les catégories AutoEdit, avatars, long format, éditeur d'images, marketplace et application mobile. La priorité reste de rendre Generate puis le premier AutoEdit assez bons pour être regardés jusqu'au bout.

## Expérience utilisateur

La complexité appartient à Faceloop. Écran Create cible : sujet, plateforme, style, ton, durée et bouton de génération. Les réglages avancés vivent dans Customize ; température, seed et paramètres fournisseurs ne deviennent pas des décisions obligatoires.

À terme, le directeur créatif propose un concept, un archétype, une durée, une direction visuelle et une conclusion, avec une explication fondée sur l'historique. L'utilisateur conserve la direction créative. Ne pas promettre la viralité.

## Mesures produit

Suivre activation, délai jusqu'à la première vidéo, complétion, régénération, export, publication, vidéos/utilisateur/semaine, rétention D7/D30, conversion payante, coût et marge par vidéo. Le volume est une mesure d'usage, pas l'objectif à maximiser.

Quand les intégrations les fournissent : viewed/swiped away, pourcentage moyen regardé, relecture, likes, commentaires et abonnements pour 1 000 vues. Distinguer métrique indisponible et valeur nulle ; documenter définitions, fenêtres et dénominateurs.

## Livraison P0 et critères d'acceptation

1. Contrats narratifs et registre de prompts : résultat validable, cinq hooks traçables, mode de vérité et version persistés ; compatibilité des scripts existants conservée.
2. Anti-répétition : historique borné et isolé, détection des paraphrases sur un corpus annoté, justification des alertes, personnages récurrents acceptés lorsque l'histoire diffère, reprise plafonnée.
3. Plans et continuité : identité conservée dans chaque plan pertinent, plans sans personnage possibles, temporalité explicite, dérives non résolues envoyées en revue.
4. Observabilité et coûts : chaque tentative traçable, coûts incomplets signalés, budgets respectés, aucune opération facturée cachée derrière un score final.
5. Évaluation sur les chaînes internes : revue humaine de la narration et des visuels, comparaison des versions sur qualité, régénération, coût et latence avant généralisation.

## Sources et portée des règles de plateforme

Sources YouTube consultées le 23 septembre 2026 : [monétisation et contenu inauthentique](https://support.google.com/youtube/answer/1311392?hl=en), [droits nécessaires à la monétisation](https://support.google.com/youtube/answer/2490020?hl=en).

YouTube évalue notamment l'originalité et la variation substantielle du contenu. L'usage de l'IA n'est pas à lui seul le critère d'exclusion ; les séries peuvent conserver des personnages si les histoires diffèrent. Les formules répétitives d'animaux en détresse sont citées parmi les exemples problématiques. La fenêtre de 20 vidéos et les scores proposés ici sont des choix internes, sans garantie d'éligibilité.

Pour l'implémentation de la publication, revalider les règles en vigueur, notamment [la déclaration des contenus synthétiques sur YouTube](https://support.google.com/youtube/answer/14328491?hl=en), ainsi que les sources officielles TikTok et Meta. Leurs exigences détaillées ne sont pas validées par ce document.
