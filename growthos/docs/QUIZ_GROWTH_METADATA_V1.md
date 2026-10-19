# Quiz generation metadata for performance analysis

The existing `content_items.script.generationMetadata` JSON gains `quizProfile` for newly rendered quiz videos. The existing `quizPresentation` timing report and `generation_cost_report` remain in place. No new table, request shape, or YouTube metric is introduced.

`quizProfile` records recipe, theme, presentation, question count, duration in seconds, duration source, verification outcome counts, and renderer version. It also carries `estimatedGenerationCostUsd` and `generationCostMissingRates` when the worker has a cost report. A missing cost is `null`; the estimate is not an actual provider invoice or local compute charge. Questions from older scripts without verification state count as `unverified`, never as `verified`. Renderer version for Classic is `quiz-classic:legacy` because the legacy style had no separate version field; Motion uses its explicit `quiz-motion:v3` version.

The existing `content_item_id` and platform publication ID provide the join to real observations in `content_performance`. Analysis must retain observation source/window and cannot treat a small sample, theme, or animation as a proven retention or subscriber effect. Existing `generationMetadata` fields and arbitrary user-generated quiz fields are preserved.

## Migration and rollback

This is an additive JSONB field and requires no database migration or backfill. Old videos retain their prior metadata. Rolling back the code stops writing `quizProfile`; stored records remain readable by existing consumers. No published content is changed.
