# YouTube-only subscriber growth rollout gates

Scope confirmed: user currently publishes only on YouTube. TikTok and Instagram are excluded.

## Experimental implementation

`engine/subscriber_growth.py` calculates **gross video-attributed subscribers gained per 1,000 cumulative views**. The YouTube collector uses `videos.list.statistics.viewCount` and `reports.metrics=subscribersGained` with a video filter from publication date to collection date. Values can have processing lag. This is neither net growth nor causal lift.

Latest timestamped snapshot per video is used, with no fallback to an older complete snapshot when the latest has missing metrics. Only explicitly tagged `platform=youtube` and `metric_source=youtube_auto` inputs are accepted; these tags are NOT present in the current production `content_performance` schema. **Do not tag historical rows as verified automatically.**

Exploratory grouped medians need >=3 eligible videos, >=50 views each. No scoring changes or production wiring.

## Review gates

1. Run `cd growthos && python -m unittest discover -s tests -p 'test_subscriber_growth.py'` and existing learning tests.
2. Audit whether YouTube analytics gross gains and cumulative Data API views diverge due to latency/day boundaries.
3. Add source/window provenance to new collection records with a reviewed migration or validated read-only adapter; avoid rewriting historical snapshots.
4. Verify multi-tenant isolation and RLS before exposing analytics in the UI.
5. Evaluate uncertainty and sample-size effects; no automatic prompt optimization from tiny cohorts.
6. Only after explicit review, consider a separate YouTube subscriber objective in strategy settings.

No database modifications, merge or deployment in this PR.
