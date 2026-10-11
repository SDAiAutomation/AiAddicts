# Faceloop — Creative Director & Quality Gate: implementation audit

Date: 2026-10-11. Status: design/audit only; no production behavior changes.

## Existing functionality (do not rebuild)
- `growthos/engine/retention.py`: deterministic STOP/HOLD/PROGRESS/REWARD/RETURN diagnostics, structured issue codes, `BLOCKING_CODES`, optional content strategy, language-aware narration rate. It explicitly does **not** predict virality.
- `growthos/engine/editorial_quality.py`: language-aware editorial heuristics, hook and CTA diagnostics; heuristics are not proof of quality.
- `growthos/engine/integrity.py`: narrow deterministic checks for arithmetic, claims, and CTA integrity; it is not general fact checking.
- `growthos/engine/quality.py`: post-render `score_generation(metrics, final_path)`, threshold 70, and `quality_check` manual-review path. Already considers editorial score, blocking retention issues, shot planning, motion, style integrity, math preflight, caption density and final file size.
- `growthos/README.md`: image style/character bible and optional image quality control already exist.

## Important gaps
1. Quality is spread across multiple reports; no single explainable **preflight** contract with evidence and precise edit targets for the user.
2. A score threshold alone can be misleading: distinguish hard failures, human-review uncertainty, and editorial suggestions.
3. Creative improvement should be **suggestion-only** by default. Do not auto-rewrite user scripts, modify facts, change visual identity, or incur API costs without approval.
4. Existing post-render QC cannot catch every subtitle overflow, audio silence, or misalignment. Add measurable media probes and visual checks only after benchmark and false-positive testing.
5. No claimed virality probability. A better hook is a hypothesis, not guaranteed growth.

## Proposed contract (future, additive)
```json
{
  "schema_version": "creative_quality:v1",
  "decision": "pass | review | block",
  "stage": "script | storyboard | render",
  "issues": [
    {
      "code": "stable_machine_code",
      "severity": "info | warning | blocking",
      "source": "retention | editorial | integrity | render",
      "block_index": 0,
      "evidence": "quoted excerpt or measurable timestamp",
      "reason": "what is actually wrong",
      "suggested_action": "targeted edit, not wholesale rewrite",
      "confidence": "deterministic | heuristic | unverified"
    }
  ],
  "automatic_edits_applied": false
}
```

## Rollout sequence
1. Create a read-only adapter of existing reports; preserve current blocking codes and publication statuses.
2. Add fixtures for FR/EN finance, mystery, quiz, animal stories and mathematical explainer; compare against existing benchmark videos.
3. Add tests for empty hook, broken payoff, CTA leakage, numerical contradictions, legitimate exceptions, old scripts without contentStrategy, and false positives.
4. Run shadow-mode against generated outputs; report disagreements without changing publishing.
5. Add one-scene/one-line suggestions with user approval; preserve narration facts and continuity.
6. Add post-render ffprobe checks (duration, stream presence, audio levels) and caption-safe-zone tests as a separate opt-in stage.
7. Only after measured false-positive rates and review, consider gating additional defects.

## Acceptance criteria
- No new paid model calls on existing generation path.
- No change to legacy score, threshold, `quality_check` status or publication without explicit approval.
- Stable codes and actionable evidence per issue.
- No automatic script rewrite.
- Full regression tests on legacy and new formats.
- Document false positives, review rate and runtime overhead.
