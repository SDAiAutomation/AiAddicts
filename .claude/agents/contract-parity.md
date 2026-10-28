---
name: contract-parity
description: À utiliser dès qu'on modifie le contrat Story Studio côté moteur (growthos/engine/story_animation/contract.py, story_adapter.py, shotplan.py, fixtures/*.json) ou côté web (growthos-web src/lib/story-studio/*.ts, scripts/fixtures/*.json). Vérifie que le moteur Python et son miroir TypeScript restent identiques. Lecture seule.
tools: Read, Grep, Glob, Bash
model: sonnet
---

Le moteur (ce repo, `growthos/engine/story_animation/`) est l'autorité. Le frontend growthos-web en garde un miroir TypeScript et des fixtures partagées. Ton travail : détecter tout écart.

## Trouver le frontend
Cherche le clone growthos-web dans cet ordre : `../growthos-web`, `../../growthos-web`. S'il est introuvable, dis-le et propose `git clone --depth 1 https://github.com/SDAiAutomation/growthos-web ../growthos-web` (branche `master`). Ne le modifie jamais.

## Vérifications
1. **Fixtures partagées** : pour chaque fichier présent des deux côtés (`growthos/engine/story_animation/fixtures/` ↔ `growthos-web/scripts/fixtures/`, par ex. `animation_contract.json`, `story_v21_*.json`, `rig_v1_story.json`), compare les SHA-256. Tout écart est bloquant.
2. **Constantes** : compare `contract.py` à `src/lib/story-studio/animation-contract.ts` — énumérations (moods, gestes, plans, caméra, transitions…), limites par schéma, cibles de durée, débits de parole ; `MAX_RENDER_SHOTS` côté moteur ↔ `src/lib/story-studio/render.ts`.
3. **Adaptateur** : `story_adapter.py` ↔ son miroir TypeScript (test de parité `story_adapter_parity.json` côté web).
4. **Tests des deux côtés** :
   - moteur : `python -m unittest discover -s growthos/engine/story_animation -p 'test_*.py'`
   - web (si `node_modules` présent) : `node --test scripts/story-*.test.mjs` dans growthos-web.

## Rapport
Tableau court : élément — moteur — web — identique ?. Puis les corrections à faire et de quel côté (le moteur fait foi, sauf décision contraire écrite). Verdict : **Parité OK** ou **Écart bloquant**.
