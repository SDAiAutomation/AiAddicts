# Story Studio — existing voice catalog integration contract

**Product name:** Story Studio (module of Faceloop). **Internal engine:** Story Intelligence.

## Integration boundaries

Story Studio must reuse Faceloop's **existing voice selector and authorized catalog**, rather than introducing a new ElevenLabs catalog, provider configuration or hardcoded IDs. The frontend should send selected catalog voice IDs per character to the authenticated backend. Never trust a catalog snapshot sent by the browser as proof of authorization.

1. Identify the existing voice dropdown component, voice catalog query/API, and tenant authorization checks in the application frontend/backend.
2. Add a character-to-voice selection control using that existing component, one selection per character. Voice labels such as Corentin and Paul are presentation-only; **never infer provider IDs from names**.
3. On the server, load the catalog scoped to the authenticated tenant/user and permitted voice IDs. Pass this trusted catalog and the character selections to `resolve_character_voices(story, catalog, selections)`.
4. Pass the resolved IDs into the existing Story Intelligence audio generation path. Preserve explicit paid generation opt-in and the default maximum of two paid TTS shots in the pilot.
5. Save the selections with the draft storyboard using the application's existing project persistence and authorization patterns. Avoid new database tables until the current schema has been inspected.
6. Return validation errors for missing, disabled, or unauthorized voices; do not fall back silently to another user's voice.
7. Ensure Story Studio UI labels use **Story Studio**; do not rename internal `story_intelligence` imports or other Faceloop formats.

## Acceptance criteria

- A creator can choose different existing voices for Néo and Orion without entering provider IDs.
- Switching the selected voice updates the storyboard configuration but **does not trigger TTS** until the user explicitly starts generation.
- A forged voice ID from another tenant or a disabled voice is rejected by the backend.
- Preview remains offline and free; real audio is not claimed until generated and measured.
- Existing Quiz, Motion Graphics and other creation modes remain unaffected.

## Current status

The engine-side resolver and pilot CLI accept catalog-backed selections; offline tests pass. **Frontend dropdown wiring, authenticated catalog fetch, persistence, end-to-end browser tests and real TTS remain TODO.** The voice catalog's actual component/API paths have not yet been verified. This document is an implementation contract, not a claim of completed UI integration.
