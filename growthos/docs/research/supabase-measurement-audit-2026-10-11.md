# Supabase measurement audit — 2026-10-11

Read-only inspection of Supabase project `growthos` (`lclesqfokgetznhepgmj`). No schema changes, no data writes.

## Existing schema

`public.content_performance` has `content_item_id`, `captured_at`, nullable `views`, nullable `followers_delta`, `watch_time_pct`, `likes`, `comments`, `shares`, and `leads`. **No explicit observation-window start/end, metric provenance, or cumulative-vs-period indicator.**

## Snapshot availability

| Account platform | Videos | Snapshots | Non-null follower values | Paired views > 0 + followers |
|---|---:|---:|---:|---:|
| YouTube | 57 | 528 | 445 | 444 |
| TikTok | 34 | 330 | 312 | 312 |

These are database counts, not confirmed usable same-window conversion observations. Multiple snapshots per video are common.

## Observed snapshot behavior

| Platform | Repeated snapshots | Views lower than prior snapshot | Followers lower than prior snapshot | Negative follower values |
|---|---:|---:|---:|---:|
| YouTube | 478 | 2 | 0 | 0 |
| TikTok | 303 | 7 | 1 | 0 |

These patterns suggest mostly cumulative-looking values but **do not establish semantics**. Lower views may be corrections or mixed sources. Non-decreasing follower values do not establish whether the value is per-video, channel-wide, or window-based. Never infer that missing values mean zero.

## Decision

**NO-GO for live conversion rankings or recommendations.** The standalone experimental calculation can only accept explicitly normalized same-window measurements. Do not query current production rows into it without a verified adapter.

## Required next investigation

1. Trace every writer of `content_performance` (CLI, cron, platform analytics, manual form) and document the exact API fields and time window for `followers_delta` and `views`.
2. Confirm video attribution of subscribers gained, especially TikTok.
3. Add explicit provenance/window semantics through a reviewed migration only if necessary.
4. Create fixture-based tests for cumulative-to-period normalization, corrections, missing values and duplicate timestamps.
5. Run offline validation and compare metrics without touching existing `engine/learning.py`.

Do not merge the draft PR or deploy on the basis of these counts.
