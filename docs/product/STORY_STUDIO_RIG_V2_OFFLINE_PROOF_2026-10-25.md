# Story Studio rig v2: offline proof (2026-10-25)

Status: **experimental technical preview; not wired into the worker or exposed in Story Studio**.
The existing `rig_v1` remains the path for saved Pip/Rosette stories. This is a character-rendering slice, not a second story-generation engine or job-state model.

## Boundary

`rig_v2.RigV2Renderer` receives a frame timeline plus a server-selected private pack root. Each character folder contains `rig.json` and PNGs named by asset ID. `rig_manifest.load_manifest` rejects unknown fields, path-like IDs, symlinks, out-of-range geometry, unsupported actions and expressions, missing assets, size mismatches and SHA-256 mismatches **before** Godot starts. No manifest can name a script, URL, command or arbitrary path. The child process uses argument arrays, a stripped environment and a timeout.

Godot reads only these validated files. It draws limbs from anchors and six sprite roles, then composes expressions, mouth cues, gestures, camera motion and subtitles at a fixed 24 FPS. Neither `godot/rig_v2/scene.gd` nor `rig_v2.py` contains a character-specific branch. The demonstration generator supplies three distinct sets of dimensions and anchors: a tall Pip stand-in, a broad Rosette stand-in, and Tavi the owl with a short body and wide wings. The stand-ins are **new developer drawings**, not the approved production assets. Adding Tavi changes only its manifest, sprites and timeline.

The renderer timeline is versioned (`rig_schema_version: 1`) and uses integer frame boundaries. An actor names a validated character, an action, expression, facing, horizontal position and a `c/o/r` mouth track with one cue per frame. A shot names its camera move, zoom endpoints, transition and subtitle. All shots must cover the timeline continuously. This is an internal render input; Story Studio's saved project and queue contract have not changed.

## Reproduce

```powershell
python -m unittest discover -s growthos/engine/story_animation -p 'test_*.py' -q
python -m growthos.engine.story_animation.benchmark_rig_v2 --out .artifacts/story-rig-v2 --godot Godot_v4.7.2-stable_win64_console.exe
```

The second command needs local Godot 4.7.2, FFmpeg/FFprobe and Pillow. CI runs it with software OpenGL in a network-isolated namespace and uploads the MP4 and JSON report.

Local Windows run: 576 frames, 1080×1920, 24 FPS, **24.000 s** measured by FFprobe, 61.73 s Godot render, 16.11 s H.264 encode, 961,657 bytes. A repeat render took 50.51 s plus 17.49 s encode and produced the **same SHA-256**: `a6ac4f1a7d6a676671d353dfe0892a709944849f8f4283bc0e835a5576e4454a`. FFmpeg found no black interval of at least 0.5 s or frozen interval of at least 1 s. Frame comparisons measured 374,967 pixels changed during the camera push and 74,695 during the walk sample; these checks establish a visible change, not its artistic merit. The first export had an extra terminal frame; the encoder now caps output at exactly 576 frames, and the benchmark asserts the frame count. CPU, peak memory and audio sync were **not measured**. No provider call or licensed media was used.

Representative frames were visually inspected at approximately 2, 12 and 20 seconds. Three silhouettes and distinct proportions are visible; the owl's pointing wing, expressions, camera framing, subtitle and forest backdrop change. The drawing quality is intentionally elementary, body motion is limited, and the silent mouth track is synthetic. This is **not** evidence of compelling finished animation, emotional dialogue or measured lip sync.

## Required before production

1. Adapt the private pack fetcher to the new per-character manifests without weakening its closed catalog or tenant isolation.
2. Test production Pip/Rosette assets in the new rig and compare representative frames against the legacy renderer. Keep old projects on `rig_v1` until an explicit migration succeeds.
3. Compile the existing measured voice timeline into this renderer's frame cues; test mouth/audio error, transitions and subtitle timing against real audio fixtures.
4. Replace placeholder drawings with approved assets, obtain human visual review, and expand the animation repertoire based on observed story needs.
5. Route through the existing reservation, refund, QC and private storage pipeline only after the above gates pass. Keep `STORY_ANIMATION_ENABLED` off publicly.
