# Quiz production render benchmark (2026-10-19)

The first measurements below were captured on Motion v3. After merging the target branch's Motion v6 renderer, the same script and previously narrated audio were rendered again; current measurements follow the historical table.

## Method

`content/scripts/quiz-benchmark-history.json` is a fixed five-question English history quiz. Its text exactly matches 12 previously generated narration blocks and word-timing files. `scripts/benchmark_quiz_pipeline.py` reuses those voice assets, disables provider credentials and fails if TTS is requested, then invokes the production `assembler._generate` and FFmpeg. It creates full MP4s, rather than browser previews or synthetic timing renders. No illustration is requested. Run with `python scripts/benchmark_quiz_pipeline.py --voice-cache <directory-containing-block-01.mp3-through-block-12.words.json>`.

The original voice cache was a local, pre-existing artifact; its historical provider charge is unknown. These runs made zero new provider calls. `renderCostUsd: null` means unmeasured compute cost, not free rendering. Rendering time is wall-clock on one Windows development machine and will vary with hardware/load. Re-running a case uses the final-video cache, and the harness reports `reusedFinalVideo: true` and `renderSeconds: null` for that rerun.

| Presentation | Frame | Duration | MP4 size | Fresh render | Elapsed | Failure |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Classic | 9:16 | 127.72 s | 3,587,451 B | 139.516 s | 142.281 s | none |
| Motion v3 | 9:16 | 127.72 s | 4,339,255 B | 265.406 s | 267.344 s | none |
| Classic | 16:9 | 127.72 s | 3,202,421 B | 137.984 s | 140.688 s | none |
| Motion v3 | 16:9 | 127.72 s | 3,641,265 B | 274.500 s | 278.485 s | none |

### Current renderer after merge: Motion v6

| Presentation | Frame | Duration | MP4 size | Fresh render | Elapsed | Failure |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Classic | 9:16 | 127.72 s | 3,673,133 B | 117.531 s | 119.062 s | none |
| Motion v6 | 9:16 | 130.272 s | 4,370,335 B | 106.328 s | 108.703 s | none |
| Classic | 16:9 | 127.72 s | 3,211,529 B | 132.829 s | 134.954 s | none |
| Motion v6 | 16:9 | 130.272 s | 3,760,549 B | 139.610 s | 143.047 s | none |

The v6 four-case run also had **0/4 observed failures** and zero new provider calls. Motion v6 includes a 0.5-second reveal beat per question, so its five-question output is 2.552 seconds longer than Classic. On this machine and script, Motion v6 rendered faster than Classic in portrait and 6.781 seconds slower in landscape. These are single-run measurements, not a general speed guarantee. Fresh v6 frames were extracted from each finished MP4; sampled question and countdown frames kept choices neutral, and reveal frames showed the answer. No sampled text was clipped. The Vault title and lock motifs sit near the top of the portrait frame; platform UI occlusion has not been tested on a device.

The initial v3 four-case run completed with **0/4 observed failures**, a small sample that is not a production failure-rate estimate. Motion v3 took about 1.9–2.0 times Classic render time for this script. Every case reused 12 voice blocks and used measured audio timing. FFprobe duration was 127.72 s; the quiz timing report totaled 127.7715 s. The 0.052 s difference is within the final media framing/rounding boundary; phase timing comes from measured narration blocks.

## Frame inspection

`scripts/inspect_quiz_benchmark.py` extracts question, countdown, and reveal frames from all four finished MP4s, using `quiz-presentation.json` scene times. The 12 current v6 frames are under ignored `output/quiz-production-benchmark/frames/`. The first question and reveal frames in both aspect ratios showed no clipped question, answer choice, or caption and no answer highlight before reveal. Contrast was legible in this Vault-theme reference. The answer highlight appeared in the reveal frames. The sampled countdown frames were also inspected; this is a representative frame review, not a pixel-by-pixel audit of all 130.272 seconds. The visible captions align with their respective phases in the sampled frames; listening and frame-level audio sync testing remain outstanding.

## Scope and repeatability

- The benchmark script uses the existing local voice cache and records `sourceVoiceCostUsd: null` explicitly. Another developer needs matching narration files to reproduce the measured-audio run; absent files cause an error before rendering.
- No external API usage or YouTube retention data was measured. Neither visual quality nor rendering speed is evidence of greater retention.
- The JSON results and MP4s remain under ignored `output/quiz-production-benchmark/`; no binary assets are committed.
- Rollback: remove the two benchmark scripts and reference JSON. They do not alter runtime rendering or persisted user data.
