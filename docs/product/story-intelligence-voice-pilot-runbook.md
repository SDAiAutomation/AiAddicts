# Néo & Orion voice pilot (experimental)

The pilot is **not connected to production**. No audio has been generated yet. The sample contains two shots targeting 12 seconds; actual duration must be verified from decoded audio.

## Free preview

```bash
python -m growthos.engine.story_intelligence.voice_pilot \\
  --story growthos/engine/story_intelligence/fixtures/neo_orion_voice_pilot.json \\
  --output /tmp/faceloop-voice-pilot
```

This makes **zero paid requests** and does not create audio files.

## Explicit paid generation (manual, only after choosing two valid voice IDs)

```bash
export ELEVENLABS_API_KEY='YOUR_SECRET_KEY'  # never commit secrets
python -m growthos.engine.story_intelligence.voice_pilot \\
  --story growthos/engine/story_intelligence/fixtures/neo_orion_voice_pilot.json \\
  --output /tmp/faceloop-voice-pilot \\
  --neo-voice-id YOUR_NEO_VOICE_ID \\
  --orion-voice-id YOUR_ORION_VOICE_ID \\
  --generate
```

This makes **one ElevenLabs request per shot** (two for this fixture), which may incur usage charges. Do not run repeatedly without checking quota. The existing TTS code can retry transient failures. The CLI stores MP3 files and timing reports locally and does not upload to Supabase.

## Verification

```bash
python -m unittest discover -s growthos/engine/story_intelligence -p 'test_*.py' -v
```

The adapter measures **decoded** audio duration using the existing FFmpeg helper and refuses render readiness if audio exceeds the target. This is not phoneme-level lip-sync. Confirm voice licensing and output quality before publishing. Do not merge until CI and compatibility checks pass.
