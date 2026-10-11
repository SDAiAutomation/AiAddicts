# YouTube Growth Intelligence — dashboard contract (design only)

## Goal
Expose understandable, trustworthy subscriber growth signals for YouTube channels without changing video generation or the existing retention score.

## MVP views
- Channel summary: tracked videos, total verified views, total gross subscribers gained, median subscribers gained / 1k views, coverage and latest observation timestamp.
- Video table: title, publish date, views, gross subscribers gained, gained/1k, observation date, data quality state.
- Exploratory feature comparisons: narrative archetype and hook with sample size and median rate, no claims of causal impact.

## Provenance contract
- `platform = youtube`, `source = youtube_auto`, `metric_semantics = gross_subscribers_gained`.
- `views` are lifetime cumulative video viewCount from YouTube Data API.
- `subscribers_gained` are YouTube Analytics subscribersGained for the video from published date to snapshot day.
- Persist collection timestamp, Analytics start/end dates, collector version and source when introducing a reviewed schema change.
- Never label generic historical `followers_delta` as net subscribers or automatically backfill provenance.

## Integrity
- Only one latest timestamped snapshot per video; latest missing data means unknown, not older snapshot fallback.
- Avoid sum of cumulative snapshots; sum only one snapshot per distinct video.
- Scope every query by authenticated organization's accounts and verify RLS.
- Distinguish videos without Analytics scope from actual zero subscriber gains.
- Hide exploratory rankings below 3 eligible videos and 50 views/video; add uncertainty warning for small cohorts.
- Avoid displaying J+1/J+7/J+30 comparisons unless normalized day-boundary data exists.
- The dashboard is read-only. No automatic prompt/CTA/series changes.

## Implementation gates
1. Validate offline unit tests in CI.
2. Review source metadata storage/migration, including RLS and backward compatibility.
3. Verify collector and UI access for tenant isolation.
4. Implement read-only API and UI in `growthos-web` behind a feature flag.
5. Compare dashboard output with YouTube Studio on sample videos.
6. Require separate approval for merge and production rollout.
