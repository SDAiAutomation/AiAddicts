# Story Gate 1 spike (rig 2D, Godot 4.7.2)

Original character "Pip", 1930s rubber-hose style, drawn from code as a pure function of time.
Not wired to Faceloop. Reference videos are not used as assets.

Render: `./render.ps1` (needs Godot via winget `GodotEngine.GodotEngine`, and ffmpeg). Output in `out/`.
Measured on i3-1005G1 / 8 GB / no dedicated GPU: ~10-16 s to render 7 s (169 frames) at 540x960.
Known: `--resolution 1080x1920` rendered 540x960 on this machine; final-res render is not solved yet.
