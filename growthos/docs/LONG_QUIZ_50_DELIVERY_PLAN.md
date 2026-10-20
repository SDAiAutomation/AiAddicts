# Long Quiz 50 — delivery plan and acceptance gates

Status: incremental draft implementation, not production approved.

## Product target
One landscape YouTube long-form quiz with 50 fact-checked questions, divided into five clearly named difficulty chapters (Easy 1–10, Medium 11–20, Hard 21–30, Expert 31–40, Genius 41–50), plus five separately exportable Shorts.

## What this PR implements
- Backward-compatible four visual round metadata for 10+ question quizzes and a subtle Motion round entrance.
- Python validation/compiler supports up to 50 questions; an additive Supabase migration expands the long series configuration limit.
- Offline unit regression workflow and 50/51 boundary tests.

## Explicitly NOT complete
- The current Motion backgrounds and generated backdrops still use FOUR visual parts, not five named difficulty tiers.
- A progressive difficulty setting does NOT certify question difficulty or ensure a true five-tier progression.
- Frontend wizard and generator in the separate growthos-web repo may still enforce a 30-question cap.
- No automatic chapter title scenes, audio transitions, YouTube timestamp metadata, Shorts segmentation, or automated publication.
- No full 50-question render/voice-cost/performance benchmark has been run.

## Implementation phases
1. **Contract**: add opt-in `chapters` schema (five 10-question spans, verified difficulty labels and independent question provenance), preserve legacy four-part mode. Validate chapter boundaries and questions.
2. **Generator**: create ten questions per level; fact-check, deduplicate across all 50, balance correct-answer positions, require editorial approval of Expert/Genius claims.
3. **Motion**: explicit five-chapter visual identity and transitions; add fifth palette/backdrop only for the opt-in mode; maintain existing four-part appearance for legacy quizzes. Avoid answer leakage and unnecessary additional narration.
4. **Audio/video**: derive chapter timecodes from measured final scene durations, not estimated countdowns. Export 16:9 master plus five independently paced 9:16 Shorts with hooks, disclosures, and CTA. Never simply crop a 16:9 master without safe-zone checks.
5. **Web and persistence**: align frontend 50-question limits, validation and Supabase migrations; add progress and cost estimates and resumable long jobs.
6. **Quality gates**: CI, 25- and 50-question offline render tests, legibility across 16:9 and 9:16, timing/voice sync, cost/time ceiling, duplicate/accuracy checks, and a manual YouTube playback review.

## Release decision
Do not merge or deploy solely because Python unit tests pass. Validate schema in staging, frontend integration, end-to-end 50-question rendering and independent Shorts output first.
