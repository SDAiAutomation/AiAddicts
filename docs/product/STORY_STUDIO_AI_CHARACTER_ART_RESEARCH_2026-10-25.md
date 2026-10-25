# AI art for Story Studio's Godot rigs (25 October 2026)

Status: research, offline intake and a local API-backed **concept preview** implemented. No cutout character pack is approved or worker-wired. Keep the existing public rendering flag off.

## Findings checked against current sources

- OpenAI's current Images API supports `gpt-image-2.5-flare` for faster drafts and `gpt-image-2.5-sunburst` for precise edits, including image references and transparent PNG output. See [image generation](https://developers.openai.com/api/docs/guides/image-generation), [image prompting](https://developers.openai.com/api/docs/guides/image-prompting), and [edits reference](https://developers.openai.com/api/reference/resources/images/methods/edit).
- OpenAI explicitly warns that recurring-character consistency and structured composition can still fail. A reference-led workflow improves identity retention but does not remove the need for human review. See [API limitations](https://developers.openai.com/api/docs/guides/image-generation) and [Images 2.5 announcement](https://openai.com/index/introducing-chatgpt-images-2-5/).
- Godot supports reusable cutout pieces with independent pivots and selective frame replacement for faces and extremities. Its `AnimationTree` can blend actions; these are renderer capabilities, not automatic image-to-rig conversion. See [cutout animation](https://docs.godotengine.org/en/stable/tutorials/animation/cutout_animation.html) and [AnimationTree](https://docs.godotengine.org/en/stable/tutorials/animation/animation_tree.html).
- OpenAI currently prices both Image 2.5 models by input/output tokens; the published standard rates are $8 per million image-input, $30 per million image-output and $5 per million text-input tokens. Exact per-character cost depends on generated size, quality and retries; record returned usage rather than claiming a fixed image price. See [pricing](https://developers.openai.com/api/docs/pricing).

## Root cause in this repository

`demo_rig_v2.py` draws geometric developer placeholders. `rig_v2` currently accepts only six PNG roles (`torso`, `head`, two hands/wings, two feet), draws limbs as lines and paints eyes and mouth procedurally. Replacing those six PNGs with attractive artwork alone will improve silhouettes and textures but will **not** create polished acting or anatomy. The character system remains a technical proof.

The existing `engine/openai_images.py` serves Standard Video scene images as JPEG and already defaults to Image 2.5 Flare; its output is unsuitable as a transparent cutout pack. Reuse its accounting and retry ideas when production character authoring is designed, but do not route an opaque scene JPEG straight into Godot.

## Recommended production workflow

1. Write one immutable character bible: species/age, silhouette, proportions, palette, clothing, distinctive features and visual style. Approve a single full-body reference image per identity.
2. Use the approved reference with the Images **edits** endpoint to request transparent, neutral-pose pieces. Start with a small manual Tavi owl pilot. Keep a fixed camera angle and lighting; generate one part per request when needed. Request no scene, text, shadow or checkerboard. Store the model snapshot, prompt version, reference hash, output hash, usage and human decision.
3. Review each piece at actual video scale. Check identity, missing joints, style, outline thickness, occlusion, mirrored parts, alpha and seam behavior. Regenerate only the rejected part under a bounded budget.
4. Record manually approved anchors and face points, then run `rig_pack_author.author_pack(...)`. It rejects missing/opaque/edge-clipped PNG parts, preserves exact asset hashes and validates the existing rig manifest. The pack can then enter the private pack registry after approval.
5. Render a short scene beside the prior art and inspect frames plus motion. Only then decide whether to expand the rig schema with upper/lower limbs, alternate face plates, mouth shapes and authored pivots. Keep legacy projects version-aware.

The current six-piece contract can be used for a **visual pilot** but should not be advertised as unrestricted character generation. The production gate needs a richer rig and human-reviewed art. A full scene illustration or sprite sheet cannot be treated as six rig pieces without segmentation and anchor review.

## Immediate pilot prompt

Use case: `illustration-story`. Original character: Tavi, a small elderly owl with broad warm-brown wings, a compact ochre body, cream facial disk, gentle observant eyes, a short amber beak and a tiny satchel. Hand-painted children's storybook style with restrained texture, clean readable silhouette and consistent medium-dark contour. Neutral front three-quarter pose, limbs separated enough for cutout extraction, even soft light. Entire character visible with margin. Fully transparent background; no scenery, cast shadow, checkerboard, lettering or watermark. Maintain exactly this identity in follow-up edits.

This is a **reference image prompt**, not a final Godot sprite. The follow-up part prompts must inherit the approved reference and specify the exact role, rest pose, pivot overlap and transparent background. Character-facing story scenes should reuse the approved pack instead of generating a new character image every shot.

## Acceptance for a first API-backed pack

- Six RGBA PNGs pass the intake and manifest validators; hashes are persisted.
- The approved reference and all six parts visibly share identity, palette and line style.
- A Godot render shows the character in idle, walk, point, talk and a reaction beside another character; representative frames are manually reviewed for seams and facial readability.
- The final report includes API usage/cost, render time, failure count and asset provenance. Until then, quality is unverified.

## Local API pilot and Godot evidence

Four billable Image API calls were made with `gpt-image-2.5-sunburst`, medium quality, 1024×1536 transparent PNG: Pip reference generation, targeted Pip alpha edit, Rosette reference from Pip, targeted Rosette alpha edit. The bundled imagegen CLI did not report token usage; **actual API charges are unknown**. Do not infer a fixed cost from file size. The key was read from the local `.env` only for each child process and never written to the repository or output.

Selected local references (outside Git): `output/imagegen/pip_reference_v2.png` (SHA-256 `f7abebc49abb0df3beae991459e92d09c7136711591c9ecef48d4f8c38661f40`) and `output/imagegen/rosette_reference_v2.png` (SHA-256 `be2a15785985493d3ad1981353c6b94b93cdf0fc3c6965ec1dd5ed48c923df19`). Both are RGBA with transparent corners. Rosette still has one stray corner pixel with alpha 1, so the art intake correctly **cannot approve it as a rig piece**. The selected Pip and Rosette images are full-body references, not six independent sprites.

The offline `godot/concept_preview` scene loads the two full-body references and draws a labeled static composition with a small camera-scale progression. This is deliberately separate from `rig_v2` and is **not** a character animation feature. Local Godot 4.7.2 + FFmpeg output: `output/imagegen/pip_rosette_concept.mp4`, 144 frames, 24 FPS, 1080×1920, 6.000 s, 1,335,777 bytes, SHA-256 `9a9bcc77c63e14367b26d04083fa024e2ae03445ddcedde0697dddd658aa75d4`. A representative middle frame was inspected for composition and actual character visibility. The background remains a simple technical placeholder.

The next quality gate is an approved art direction followed by rig-ready body parts and face variants. Full-body images must not be passed off as an animated cutout pack.
