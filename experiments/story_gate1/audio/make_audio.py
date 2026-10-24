"""Gate 2 audio, fully local and free: Windows SAPI voice (Hortense) -> two voices by pitch shift -> measured durations
-> per-frame mouth classes from the audio envelope -> mixed track + timeline.json read by scene3.gd.
Placeholder voices: swap `synth()` for Faceloop's ElevenLabs path later; everything downstream is measured, not assumed."""
import json, os, subprocess, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "audio")
os.makedirs(OUT, exist_ok=True)
FPS = 24
LINES = [
    ("ros", "Monsieur Pip, votre réveil sonne encore !"),
    ("pip", "Impossible, madame ! Je l'ai réglé hier !"),
    ("ros", "Alors pourquoi il vous poursuit ?"),
]
# voice shaping per character: asetrate factor (pitch), then atempo to restore speed
VOICE = {"ros": (1.00, "-1"), "pip": (0.78, "1")}
LEAD, GAP, TAIL = 0.5, 0.4, 2.2


def synth(text, who, path):
    ps = os.path.join(OUT, "tts.ps1")
    rate = VOICE[who][1]
    open(ps, "w", encoding="utf-8-sig").write(
        "Add-Type -AssemblyName System.Speech\n$s=New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$s.SelectVoice('Microsoft Hortense Desktop')\n$s.Rate=%s\n$s.SetOutputToWaveFile('%s')\n$s.Speak(@'\n%s\n'@)\n$s.Dispose()\n" % (rate, path, text))
    subprocess.run(["powershell", "-NoProfile", "-File", ps], check=True)


def shape(src, dst, factor):
    af = f"asetrate=22050*{factor},aresample=44100,atempo={1/factor:.4f},loudnorm=I=-16:TP=-1.5"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-ac", "1", "-af", af, "-ar", "44100", dst], check=True)


def envelope(path):
    w = wave.open(path)
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    n = int(sr / FPS)
    frames = len(x) // n + 1
    rms = np.array([np.sqrt(np.mean(x[i * n:(i + 1) * n] ** 2)) if len(x[i * n:(i + 1) * n]) else 0 for i in range(frames)])
    return rms / (np.percentile(rms, 95) + 1e-9), len(x) / sr


def classes(env):
    c = ["c"] * len(env)
    for i, e in enumerate(env):
        c[i] = "o" if e > 0.55 else ("r" if e > 0.2 else "c")
    for i in range(1, len(c) - 1):  # drop single-frame flicker
        if c[i] != c[i - 1] and c[i] != c[i + 1]:
            c[i] = c[i - 1]
    return "".join(c)


t = LEAD
lines, files = [], []
for i, (who, text) in enumerate(LINES):
    raw = os.path.join(OUT, f"raw{i}.wav")
    wav = os.path.join(OUT, f"line{i}.wav")
    synth(text, who, raw)
    shape(raw, wav, VOICE[who][0])
    env, dur = envelope(wav)
    lines.append({"who": who, "text": text, "start": round(t, 3), "dur": round(dur, 3), "end": round(t + dur, 3), "mouth": classes(env)})
    files.append((wav, t))
    t += dur + GAP
total = round(lines[-1]["end"] + TAIL, 3)
inputs, filt = [], []
for k, (wav, st) in enumerate(files):
    inputs += ["-i", wav]
    filt.append(f"[{k}]adelay={int(st * 1000)}|{int(st * 1000)}[a{k}]")
mix = "".join(f"[a{k}]" for k in range(len(files))) + f"amix=inputs={len(files)}:normalize=0,apad=whole_dur={total}[m]"
subprocess.run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", ";".join(filt + [mix]), "-map", "[m]", "-t", str(total), os.path.join(OUT, "mix.wav")], check=True)
json.dump({"fps": FPS, "total": total, "lines": lines}, open(os.path.join(HERE, "..", "timeline.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for l in lines:
    print(l["who"], "start", l["start"], "dur", l["dur"], "open/round frames", l["mouth"].count("o"), l["mouth"].count("r"), "of", len(l["mouth"]))
print("total", total)
