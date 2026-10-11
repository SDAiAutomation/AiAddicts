# YouTube metrics provenance — code audit (2026-10-11)

Source: `growthos-web/src/lib/youtube/metrics.ts` and `src/app/api/cron/youtube-metrics/route.ts` on the default branch.

## Verified

- `views` = YouTube Data API `videos.list(part=statistics)` `viewCount`: cumulative video views.
- `followers_delta` = YouTube Analytics API `reports` metric **`subscribersGained`**, filtered by `video==<youtube_video_id>`, with `startDate` = the video's `published_at` calendar date (fallback `2020-01-01`) and `endDate` = current UTC date.
- `watch_time_pct` = `averageViewPercentage` from the same Analytics request, and `shares` = `shares`.
- The two APIs are called in the same collection pass and values inserted together into `content_performance`.
- The cron skips videos with a snapshot within the previous 20 hours and tracks videos published within the last 45 days.

## Critical semantic correction

`subscribersGained` is **gross gained subscribers**, not net subscribers. It does **not** subtract `subscribersLost`. The database column `followers_delta` is a generic name and must not be described as verified net growth for these YouTube rows.

A suitable descriptive metric for this specific source is **attributed subscribers gained per 1,000 cumulative video views**. It is not necessarily a causal attribution of subscribing behavior and not a net growth metric.

## Caveats

- Data API view totals and Analytics reports can have different processing delays and day boundaries.
- Analytics start date defaults to 2020-01-01 if `published_at` is null.
- Missing Analytics scope or unavailable rows result in null, not zero.
- The collector does not persist metric provenance, window bounds, or API extraction lag in the row.
- Historic rows may have been inserted by other paths and cannot be automatically relabeled based solely on this collector.

## Next gate

Trace TikTok writers and any manual entry paths before normalizing production rows. Add explicit source/window semantics and distinguish gross gained vs lost vs net, preferably without changing the current learning score. Do not merge this experimental PR yet.
