# Retention & Virality Engine V1

Architecture éditoriale short-form : **STOP → HOLD → PROGRESS → REWARD → RETURN**.
Code : `engine/retention.py` (déterministe, aucun appel IA/réseau). Contrat web :
`growthos-web/src/lib/retention-contract.ts`. Benchmark : `content/scripts/retention/BENCHMARK.md`
(regénéré par `python scripts/retention_benchmark.py`).

**Ce que ce module ne fait pas** : prédire la viralité. Aucun score de viralité, aucune probabilité.
Il décrit des caractéristiques contrôlables (hook, rythme, boucle ouverte, payoff, répétitions,
progression visuelle, CTA) et signale des défauts factuels.

## Données (dans `content_items.script`, jsonb — aucune migration)

Tout est **optionnel** ; un script sans ces champs se comporte exactement comme avant.

| Champ | Où | Écrit par |
|---|---|---|
| `contentStrategy` {audiencePromise, coreQuestion, viewerProblem, payoff, hookType, hookText, curiosityMechanism, emotionalDriver, targetDurationSec, ctaIntent} | script | l'appel LLM de génération existant (0 appel en plus) |
| `openLoops` [{question, openedAtBlock, resolvedAtBlock?}] (indices base 0, hook = 0) ; la forme `openLoop` (objet) est aussi acceptée | script | idem |
| `retentionRole` (hook, setup, escalation, evidence, pattern_interrupt, reveal, payoff, cta) | bloc | idem |
| `informationGain` (new_fact, new_example, new_consequence, new_visual_evidence, new_question, answer, cta) | bloc | idem |
| `series` {name, episode, continuityCTA} | script | la fonctionnalité de séries (jamais imposé, pas généré par le LLM) |
| `retentionDiagnostics` | script | le moteur, à chaque génération (**dérivé**) |
| `generationMetadata` | script | le moteur, à chaque génération (**dérivé**) |

Valeurs invalides : `validate_script` les **rejette** (comme `shotType`). Le web doit donc ne stocker
que des valeurs valides (`retention-contract.ts` écarte silencieusement le reste). Les champs dérivés
sont exclus de l'empreinte de cache (`generation_cache._DERIVED_SCRIPT_KEYS`) : les stocker n'invalide jamais images/voix déjà payées.

## Hooks, rôles, CTA

- 10 familles de hook : `contradiction curiosity_gap specific_number warning scenario comparison unexpected_fact mistake challenge transformation`.
- `visualPurpose` -> rôle de rétention : hook→hook, establish→setup, action→escalation, evidence→evidence,
  reaction→pattern_interrupt, reveal→reveal, payoff→payoff, cta→cta. `explain` n'est **pas** mappé
  (c'est l'étiquette « explication générique »).
- 7 intentions de CTA : `none follow_for_series question next_episode save share subscribe`. Le moteur
  n'ajoute jamais de CTA ; le « like et abonne-toi » plaqué est signalé (`boilerplate_cta`).

## Rapport `retentionDiagnostics`

`hook` · `structure` · `pacing` · `openLoops` + `promises` · `payoff` · `repetition` ·
`visualProgression` (+ `plan`, `patternInterrupts`) · `cta` · `issues` · `summary`.
Chaque problème : `{section, code, severity: "high"|"info", message, blocks?}` (messages en français,
`code` stable pour l'i18n). **Seuils configurables** (`RetentionConfig`) ; par défaut seuls le hook
(4 s, constante existante de `quality.py`), le CTA (12 mots) et des longueurs de lisibilité signalent
quelque chose — aucun seuil de « succès » universel (`max_block_sec`, `max_seconds_before_payoff`,
`max_seconds_before_first_example` sont `None` = mesure descriptive).

Durées : mesurées (voix off réelle, `durations`) sinon estimées depuis le nombre de mots
(fr 213, en 172 mots/min — miroir de `script-length.ts`).

### Impact sur la qualité (`quality.score_generation`)

Uniquement si le script déclare un `contentStrategy` **et** seulement pour les problèmes `high`
(payoff/boucle/répétition/promesse) : -4 chacun, plafonné à -12. Les scripts sans `contentStrategy`
sont notés comme avant.

## Analytique future (rien n'est collecté ici)

`generationMetadata` = face « génération » de la jointure :
`content_item_id` → contentStrategy → hookType → structure narrative → types de scène → durée → métriques observées.
`OBSERVED_METRIC_FIELDS` : `shownInFeed choseToView swipedAway views engagedViews averageViewDuration
averagePercentageViewed likes comments shares subscribersGained`. **`views` et `engagedViews` restent
distincts** (YouTube a changé le comptage des vues Shorts en 2025). `join_observation()` rejette tout
champ inconnu. Pas d'API YouTube, pas de ML.

## Coût

0 appel LLM supplémentaire (le `contentStrategy` sort du même appel de script), 0 appel image,
0 fournisseur. L'analyse tourne localement (millisecondes). Seul surcoût : quelques centaines de
tokens de prompt/sortie sur l'appel de script existant.

## Phase 5.2 — calibration (2026-10-01)

Real-model validation (Phase 5.1) showed the model treating roles as mandatory slots. Changes, all deterministic or prompt-level:

- **Prompt (web `ai-actions.ts`)**: roles, open loops and CTA are optional tools ("hook → evidence → payoff" is valid); answer early, payoff must be a specific answer; never speak internal role names; no invented first-person experience; no placeholders. Explainers (Motion Graphics, not TikTok) use a *short* profile (25–45 s, `lib/script-length.ts`, `content_goal: reach`); TikTok keeps its 60 s monetization target.
- **Guards**: `role_label_leak` (high) + a scrub before storage (`stripRoleLabels`, mirror of `ROLE_LABEL_RE`); `unsupported_first_person` (info for 1 block, high for 2+, exempt for `source_type: pasted_text`).
- **Motion Graphics** (`engine/motion_graphics/semantic.py`): scenes whose data mean nothing (placeholders, charts without values, empty comparisons, progress bar without a quantity) fall back to `icon_text` and the fallback is recorded in `motion_preflight` (`fallback_semantic` / `fallback_schema`). `targetRatio` is never drawn as a percentage any more.
- **Diagnostics**: number words normalized (`five dollars` = `$5`, `ten thousand` = `10000`, `$25k`); removed `weak_hook_visual`, `hook_type_signal_missing`, `cta_carries_value`, `loop_resolved_after_payoff`, `no_tension`, `no_open_loop`, `no_reveal_or_payoff`, `no_escalation_or_evidence`, `late_setup`, CTA intent mismatches; `promised_number_missing` and lexical-overlap payoff checks are info only (rounding-tolerant). Rule: a diagnostic is "high" only if a viewer would see the defect or the signal is structural/numeric; metadata mismatches and taste are silent.

## Phase 5.3 — final calibration & content integrity

- **Profile ≠ visual style.** The length profile ("short" ≈ 25–45 s as an order of magnitude, never a floor) comes from an explicit per-script choice or from the account strategy (`strategies.priority_formats` containing a short format), is stored as `script.length_profile`, and drives `content_goal` (short → `reach`). Motion Graphics no longer implies any duration.
- **`engine/integrity.py`** (deterministic, no LLM/network, silent outside narrow recognized forms): arithmetic (rate conversions day/week/month/year, time-to-goal at one fixed rate, subtraction chains, listed-amount sums, percent-of, formula scenes, accumulated contributions), investment projections without an explicit/hedged assumption, "guaranteed" language, unsourced empirical generalities, CTAs that promise a resource/reply/DM, visible placeholders. Blocking codes (`retention.BLOCKING_CODES`) put the video in `quality_check` (score −35) — a false number or a fake promise never goes out on autopilot. The web drops a CTA that promises a resource (the CTA is optional) and sets `ctaIntent: none`.
- **Motion Graphics fallbacks** (`semantic.fallback_scene`): existing scene types only — one readable number → `big_number`; several readable facts → `checklist`; progress bar with a visible amount → `big_number`; last resort → `icon_text` with a title or a *complete* short clause of the narration (`display_phrase`), never a truncated fragment. Recorded in `motion_preflight` (`fallback_semantic` / `fallback_schema`) and surfaced as an info diagnostic.
- **Prompt**: no enumeration of forbidden label phrases (raw leakage measured, see report), no role-sequence examples; density and block count come from the idea.
