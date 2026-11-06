# Subscriber Growth Intelligence — isolated v0 (2026-10-11)

**Status:** experimental, not connected to the live recommendation engine.

## Verified baseline

- `growthos/engine/learning.py` already incorporates `followers_delta` in the composite score, capped at 10 points.
- `growthos/log_metrics.py` accepts `--followers-delta` and persists performance snapshots.
- The existing recommendation experiment uses a retention baseline. Do not silently reinterpret it as subscriber conversion.
- The script-generation prompt and retention CTA contract already support optional CTAs. This PR does not change them.

## Experimental metric

Net subscribers per 1,000 views = `followers_delta / views * 1000`.
Negative values are valid. Missing follower data is **unknown**, not zero.
Group-level descriptive medians require at least three distinct eligible videos and 50 views each. These thresholds are exploratory, not statistically validated.

**Critical data contract:** numerator and denominator must cover the same observation window. The current CLI accepts independent values and does not prove whether they are cumulative or period deltas. Until this is confirmed for each platform/import path, do **not** feed live rows into the new module or compare its output to account baselines.

## Scope and guardrails

- No migrations, writes, new LLM calls, API calls, prompt changes, UI, or automatic recommendations.
- No modification to `performance_score`, `build_insights`, or `build_recommendation`.
- `conversion_insights` expects already-normalized, one-row-per-video same-window snapshots.
- This is observational, not causal; a high conversion rate may reflect channel maturity, topic, exposure, or selection effects.
- Test offline with `python -m unittest tests.test_subscriber_growth` from `growthos/` (depending on test package layout, discovery: `python -m unittest discover -s tests -p 'test_subscriber_growth.py'`).

## Next gates (before any production integration)

1. Audit YouTube/TikTok/Meta ingestion and distinguish cumulative counters, period deltas, and signed net subscriber changes.
2. Normalize observation windows and retain explicit provenance; do not merge incompatible snapshots.
3. Confirm whether `followers_delta` includes unfollows and whether the value is video-attributable.
4. Evaluate account-level and format-level sample sizes, noise, confidence intervals, and age effects.
5. Compare proposed insights against existing recommendations offline, then decide whether to add a user-selectable growth objective.

No production rollout or merge is authorized by this experimental PR.
