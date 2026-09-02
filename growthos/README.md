# GrowthOS — MVP dogfooding

Cycle minimal : `script.json` → voix off → vidéo texte-carte sous-titrée → package prêt à publier manuellement.

Portée volontaire de ce cycle 1 (semaines 1-2 du plan "Résultats d'abord") :

- Pas de génération vidéo IA payante. Fond uni + sous-titres brûlés : suffisant pour valider la boucle sur un vrai compte, à coût quasi nul.
- Pas de publication automatique (OAuth TikTok/Meta). La demande d'app développeur prendrait des semaines à elle seule. Le script produit une caption prête + une checklist, la publication reste manuelle.
- Un seul provider voix (ElevenLabs), pas de fallback : ce n'est pas un besoin réel à ce stade.

## Installation

```bash
pip install -r requirements.txt
# ffmpeg doit être installé sur la machine (apt install ffmpeg / brew install ffmpeg)
cp .env.example .env   # puis renseigner ELEVENLABS_API_KEY
```

## Lancer une génération

```bash
python main.py content/scripts/exemple-01.json
```

Produit, dans `output/<compte>-<titre>/` :

1. `audio/` — un mp3 par bloc + la voix off complète assemblée
2. `captions.srt` — sous-titres synchronisés sur la durée réelle de chaque bloc
3. `final/*.mp4` — vidéo finale (fond uni + sous-titres brûlés)
4. `publish/caption.txt` — caption + hashtags prêts à copier-coller
5. `publish/checklist.md` — checklist avant publication manuelle

## Écrire une nouvelle histoire

Un script est un fichier JSON dans `content/scripts/` avec `title`, `niche`, `account`, `voice_id`, `hashtags`, et une liste `blocks` (`role`: `hook` / `point` / `cta`, `text`: le texte narré). Voir `exemple-01.json`.

## Suivi hebdomadaire

Après chaque publication réelle, ajouter une ligne dans `metrics/suivi-hebdo.csv` (6 métriques du plan "Résultats d'abord" : publications/semaine, vues moyennes, watch time, abonnés nets, engagement, leads). Pas de dashboard à ce stade, c'est la V0 volontairement plate — le Dashboard produit viendra une fois la boucle validée.

## Tests

```bash
python -m unittest discover -s tests
```

Aucun appel réseau ni ffmpeg dans les tests (logique pure : validation de script, timestamps SRT, CSV de métriques).

## Prochaines étapes

Voir le plan sur 6-8 semaines : Quality Gate simple + analytics de base (semaines 3-4), corrections de friction + début de mémoire de compte (semaines 5-6), stabilisation pour la mise en public des résultats (semaines 7-8).
