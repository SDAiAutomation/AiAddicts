# Story Intelligence Pilot v0.2 — experimental

## Scope

This draft PR adds a **standalone, opt-in** offline timing helper and focused tests. It does not wire anything into the existing Faceloop generation pipeline, call ElevenLabs, modify storage, or introduce subscriptions.

The creative reference is a 45-second French educational conversation between Néo the young fox and Orion the elderly owl about saying no. Character and storyboard contracts will be integrated in a subsequent reviewable PR.

## Timing contract

Input: a storyboard with `target_duration_s` and `shots` containing unique `id` and positive `duration_s`; caller-supplied mapping of shot IDs to **measured** audio durations. Output: a deep-copied retimed storyboard and report. Each scene duration is at least the original duration and the audio duration plus pause. **Speech is never cut to fit the target.** Overruns prevent render readiness.

The helper **does not independently authenticate** that supplied audio durations were actually measured. Do not label this a real TTS test until ElevenLabs audio and a duration probe are integrated.

## Tests

Run `python -m unittest growthos.engine.story_intelligence.test_timing -v`. The six tests cover target fit, overrun, input immutability, missing audio, nonfinite duration and duplicate IDs. CI status must be checked before merging.

## Next steps

1. Review the existing narration/ElevenLabs interfaces before wiring the adapter.
2. Add the full storyboard schema and validators with versioning and tenant-safe character IDs.
3. Test real generated audio durations without logging or storing sensitive voice credentials.
4. Add regression coverage for existing video formats; merge only after review.
