param([string]$Scene = "main.tscn", [string]$Name = "pip", [string]$Out = "out")
# Renders a scene with Godot (--write-movie, fixed 24 fps, 540x960) then encodes H.264 with ffmpeg.
$godot = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter 'Godot*console*.exe' | Select-Object -First 1).FullName
$here = $PSScriptRoot
New-Item -ItemType Directory -Force "$here\$Out" | Out-Null
$sw = [Diagnostics.Stopwatch]::StartNew()
& $godot --path $here --rendering-driver opengl3 --write-movie "$here\$Out\$Name.avi" --fixed-fps 24 $Scene
$t1 = $sw.Elapsed.TotalSeconds
ffmpeg -v error -y -i "$here\$Out\$Name.avi" -c:v libx264 -pix_fmt yuv420p -crf 18 -an "$here\$Out\$Name.mp4"
"godot_render_s=$([math]::Round($t1,1)) total_s=$([math]::Round($sw.Elapsed.TotalSeconds,1))"
