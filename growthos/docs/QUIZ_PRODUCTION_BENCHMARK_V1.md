# Quiz production render benchmark (2026-10-19)

## Method

`content/scripts/quiz-benchmark-history.json` is a fixed five-question English history quiz. Its text exactly matches 12 previously generated narration blocks and word-timing files. `scripts/benchmark_quiz_pipeline.py` reuses those voice assets, disables provider credentials and fails if TTS is requested, then invokes the production `assembler._generate` and FFmpeg. It creates full MP4s, rather than browser previews or synthetic timing renders. No illustration is requested. Run with `python scripts/benchmark_quiz_pipeline.py --voice-cache <directory-containing-block-01.mp3-through-block-12.words.json>`.

The original voice cache was a local, pre-existing artifact; its historical provider charge is unknown. These runs made zero new provider calls. `renderCostUsd: null` means unmeasured compute cost, not free rendering. Rendering time is wall-clock on one Windows development machine and will vary with hardware/load. Re-running a case uses the final-video cache, and the harness reports `reusedFinalVideo: true` and `renderSeconds: null` for that rerun.

| Presentation | Frame | Duration | MP4 size | Fresh render | Elapsed | Failure |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Classic | 9:16 | 127.72 s | 3,587,451 B | 139.516 s | 142.281 s | none |
| Motion v3 | 9:16 | 127.72 s | 4,339,255 B | 265.406 s | 267.344 s | none |
| Classic | 16:9 | 127.72 s | 3,202,421 B | 137.984 s | 140.688 s | none |
| Motion v3 | 16:9 | 127.72 s | 3,641,265 B | 274.500 s | 278.485 s | none |

All four completed: observed failure rate **0/4**, which is a small sample and not a production failure-rate estimate. Motion took about 1.9–2.0 times Classic render time for this script. Every case reused 12 voice blocks and used measured audio timing. FFprobe duration was 127.72 s; the quiz timing report totals 127.7715 s. The 0.052 s difference is within the final media framing/rounding boundary; phase timing comes from measured narration blocks.

## Frame inspection

`scripts/inspect_quiz_benchmark.py` extracts question, countdown, and reveal frames from all four finished MP4s, using `quiz-presentation.json` scene times. The 12 resulting frames are under ignored `output/quiz-production-benchmark/frames/`. The first question and reveal frames in both aspect ratios showed no clipped question, answer choice, or caption and no answer highlight before reveal. Contrast was legible in this Vault-theme reference. The answer highlight appeared in the reveal frames. The sampled countdown frames were also inspected; this is a representative frame review, not a pixel-by-pixel audit of all 127.72 seconds. The visible captions align with their respective phases in the sampled frames; listening and frame-level audio sync testing remain outstanding.

## Scope and repeatability

- The benchmark script uses the existing local voice cache and records `sourceVoiceCostUsd: null` explicitly. Another developer needs matching narration files to reproduce the measured-audio run; absent files cause an error before rendering.
- No external API usage or YouTube retention data was measured. Neither visual quality nor Motion's slower rendering is evidence of greater retention.
- The JSON results and MP4s remain under ignored `output/quiz-production-benchmark/`; no binary assets are committed.
- Rollback: remove the two benchmark scripts and reference JSON. They do not alter runtime rendering or persisted user data.
