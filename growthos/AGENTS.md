# Faceloop — permanent product instructions

Read [PRODUCT_DOCTRINE.md](PRODUCT_DOCTRINE.md) before making product or architecture decisions. It defines the target product; the README describes the existing implementation. GrowthOS remains the technical repository name.

For the AutoEdit integration boundary, use [AUTOEDIT_CONTRACT.md](AUTOEDIT_CONTRACT.md). Do not invent a second request or job-state shape in either codebase.

## Team ownership

- Claude Code owns the backend: database, workers, AI orchestration, media analysis, EDL generation, rendering and backend contracts.
- Codex owns the frontend: product flows, screens, states, form design, feedback, accessibility and integration with the backend contracts.
- Keep the boundary explicit. Frontend work may propose or document a contract, but must not silently duplicate backend business logic. Backend changes should expose stable, UI-oriented states and errors.

Faceloop is an AI content engine for faceless creators, designed to help them produce original, engaging short-form content that respects platform requirements.

- Every engineering decision must improve quality, originality, retention, simplicity, speed, reliability or unit economics. Explain material tradeoffs.
- Never sacrifice content quality to maximize generation volume. Avoid interchangeable stories and repetitive distress/rescue formulas.
- Preserve narrative and visual continuity. Reuse character identity across relevant shots without forcing characters into shots where they do not belong.
- Prefer intelligent defaults over extra UI controls. Technical model settings belong in internal configuration or advanced customization.
- Make AI operations observable, prompt-versioned, measurable and replaceable. Distinguish estimated costs from actual charges and missing measurements from zero.
- Use performance data to propose new hypotheses with evidence and confidence, without blindly duplicating successful videos.
- Distinguish fiction, inspired stories and verified facts. Never invent sources or present invented events as documented facts.
- Treat quality and originality scores as internal diagnostics, never guarantees of views or monetization.
- Prioritize Story Engine 2.0, anti-repetition and visual consistency before sports, autopublishing or additional niches. Extend existing components before adding parallel systems.
- Bound automated retries by attempts and cost; unresolved quality issues require an explicit review state.
- Build reusable systems, not scattered one-off prompts. The goal is content worth publishing.

This doctrine guides incremental work; it does not imply that roadmap features already exist or authorize publishing content externally.
