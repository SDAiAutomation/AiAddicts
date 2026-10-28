@growthos/CLAUDE.md

# Claude Code — sous-agents et vérifications automatiques

Lance Claude Code depuis la racine de ce repo (là où se trouve `.claude/`) pour que les agents, permissions et hooks ci-dessous soient chargés. Ces règles complètent `growthos/AGENTS.md` et `growthos/PRODUCT_DOCTRINE.md` sans les remplacer.

## Sous-agents du projet (`.claude/agents/`)

| Agent | Quand le lancer (automatiquement, sans attendre qu'on le demande) |
|---|---|
| `engine-reviewer` | Avant d'ouvrir ou de mettre à jour une PR. Verdict « Bloquant » = on corrige avant la PR. |
| `render-checker` | Après toute modification du rendu Story Studio (Godot, rigs, renderer, shotplan, timeline, lipsync) ou pour juger un MP4. |
| `contract-parity` | Quand `contract.py`, `story_adapter.py`, `shotplan.py` ou `story_animation/fixtures/*.json` change. Le miroir TypeScript est dans growthos-web. |

- Les vérificateurs n'ont pas participé à la construction : donne-leur la branche et l'objectif, pas tes conclusions.
- Lance en parallèle les vérifications indépendantes.

## Travail en parallèle

- Règle du propriétaire : **une PR par modification**. Plusieurs modifications indépendantes → sous-agents en worktree isolé (`isolation: worktree`), une branche et une PR chacun.
- Avant toute tâche longue ou multi-fichiers, passe par le mode plan et fais valider le découpage.

## Garde-fous (hook `.claude/hooks/guard_bash.py`)

Bloque : merge de PR, push sur `growthos/mvp`/master/main ou forcé, appels directs aux fournisseurs IA payants, activation des drapeaux de génération Story, lecture du `.env`, migrations Supabase distantes, clés Stripe live. Si un hook bloque : arrête-toi et explique à l'utilisateur, ne contourne pas. Le hook nécessite `python3` dans le PATH (WSL/Linux).

Le hook ne voit que les commandes shell : un script Python qui appelle un fournisseur payant n'est pas intercepté. Ne lance donc aucun worker, pipeline de génération ou script de production sans autorisation explicite ; préfère les fixtures, packs de remplacement et benchmarks hors ligne.

## Ce qui reste toujours humain

Merge, mise en production du worker, appels payants (OpenAI, ElevenLabs, modèles vidéo), migrations de production, et le jugement artistique d'un rendu.
