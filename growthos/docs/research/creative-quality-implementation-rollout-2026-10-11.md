# Creative Quality Gate — implementation and staged validation

## Shipped in draft PR
- `engine/creative_quality.py`: read-only adapter over existing retention and editorial diagnostics. Structured issues, actionable suggestions, decision pass/review/block, no enforcement.
- `engine/render_preflight.py`: optional ffprobe media container/stream inspection, read-only. Second ffmpeg pass (~10 % of the video length): long silence (>= 2.5 s), frozen image (>= 4 s), very quiet audio (mean < -38 dB), all advisory warnings. Thresholds measured on 36 real renders with 0 false positives; black frames are deliberately not checked (dark Motion Graphics themes stay black up to 7 s). No caption OCR or overlap claim.
- `creative_quality_cli.py`: standalone preview from an existing script and optional video.
- Unit tests and GitHub Actions workflow for these modules.

## Run locally
```bash
cd growthos
python -m unittest discover -s tests -p 'test_creative_quality.py' -v
python -m unittest discover -s tests -p 'test_render_preflight.py' -v
python creative_quality_cli.py content/scripts/exemple-01.json --output /tmp/quality.json
python creative_quality_cli.py content/scripts/exemple-01.json --video /path/to/video.mp4
```

## User experience contract (next web integration)
Show three separate groups in Studio:
1. **Critical integrity**: code, offending script block, exact evidence, reason, one targeted action. Never silently edit facts.
2. **Editorial suggestions**: label heuristic, allow dismissal and comparison; no claim of predicted views.
3. **Rendered video**: stream/duration checks; show 'not checked' if no MP4 or ffprobe unavailable.

Render the existing report as read-only; no service-role token in browser; authorize each content item by organization and RLS. Add a feature flag default off, with no new paid calls. Store report only after security review, otherwise generate server-side on demand.

## Benchmark protocol
Use a consented, fixed sample spanning FR/EN finance, mysteries, quizzes, animal narratives, and math explainers. Include positive controls and deliberately broken scripts.
For each issue record: source code, human reviewer judgment (true/false/uncertain), whether it would block, proposed fix, and review time. Calculate precision by severity and false-block rate; avoid optimizing for a single aggregate score.
Include tests for missing hook, real arithmetic error, innocent numbers, unsupported CTA promise, old scripts lacking contentStrategy, intentionally silent clips, missing ffprobe, and legitimate video without narration.

## Release gates
- CI tests pass and code review approves.
- Existing `quality.score_generation` and publication statuses remain unchanged.
- No false blocking on benchmark samples (new gate remains advisory until separately approved).
- Shadow-mode runtime/cost impact measured.
- Auth/RLS tests across two organizations before UI release.
- Product owner separately approves any new enforcement, Supabase migration, or production deployment.

## Known limitations
The quality adapter does not verify facts, predict virality, or fix a script. Render checks catch silence, frozen image and quiet audio, not subtitle clipping, text legibility or desync. A silence under background music is not detected (music masks it). Sensitivity is only verified on a synthetic clip: no real defective render was available. An existing low editorial score is advisory in the new report and retains its separate legacy semantics. Tests are committed but their execution must be confirmed from CI or a local checkout.
