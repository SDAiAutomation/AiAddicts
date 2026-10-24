"""Gate 2 audio with Faceloop's ElevenLabs path (same model/settings as growthos/engine/tts.py), using the with-timestamps endpoint.
Mouth classes come from the character alignment returned by the API (vowels open/round, b/m/p/f/v closed) gated by the measured audio envelope.
Hard cap on characters (CAP_CHARS) with a ledger; key is read from a private file outside the repo and never printed."""
import base64, json, os, subprocess, sys, urllib.request, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "audio")
os.makedirs(OUT, exist_ok=True)
FPS = 24
CAP_CHARS = 3000
LEDGER = os.path.join(HERE, "..", "out", "eleven_ledger.json")
KEY = open(os.path.join(os.path.expanduser("~"), "story_studio_work", ".eleven_key")).read().strip()
MODEL = "eleven_multilingual_v2"
SETTINGS = {"stability": 0.4, "similarity_boost": 0.75, "style": 0.35}  # a little more acting than the product default (0.5/0.75)
VOICES = {"pip": "IHngRooVccHyPqB4uQkG", "ros": "XrExE9yKIg1WjnnlVkGX"}  # Corentin (GrowthOS), Matilda
LINES = [
    ("ros", "Monsieur Pip, votre réveil sonne encore !"),
    ("pip", "Impossible, madame ! Je l'ai réglé hier !"),
    ("ros", "Alors pourquoi il vous poursuit ?"),
]
LEAD, GAP, TAIL = 0.5, 0.3, 2.2
OPEN, ROUND, CLOSED_C = set("aàâeéèêëiîïy"), set("oôuùûw"), set("bmpfv")


def used():
    try:
        return sum(e["chars"] for e in json.load(open(LEDGER)))
    except FileNotFoundError:
        return 0


def log(e):
    try:
        d = json.load(open(LEDGER))
    except FileNotFoundError:
        d = []
    d.append(e)
    json.dump(d, open(LEDGER, "w"), indent=1)


def synth(text, who, i):
    if used() + len(text) > CAP_CHARS:
        sys.exit("character cap reached")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICES[who]}/with-timestamps"
    body = json.dumps({"text": text, "model_id": MODEL, "voice_settings": SETTINGS}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        sys.exit("HTTP %s: %s" % (e.code, e.read().decode()[:200]))
    log({"line": i, "who": who, "chars": len(text)})
    mp3 = os.path.join(OUT, f"el{i}.mp3")
    open(mp3, "wb").write(base64.b64decode(r["audio_base64"]))
    wav = os.path.join(OUT, f"line{i}.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-ac", "1", "-ar", "44100", wav], check=True)
    return wav, r["alignment"]


def envelope(path):
    w = wave.open(path)
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    n = int(sr / FPS)
    frames = len(x) // n + 1
    rms = np.array([np.sqrt(np.mean(x[i * n:(i + 1) * n] ** 2)) if len(x[i * n:(i + 1) * n]) else 0 for i in range(frames)])
    return rms / (np.percentile(rms, 95) + 1e-9), len(x) / sr


def classes(env, al):
    ch, st, en = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    out = []
    for f in range(len(env)):
        t = (f + 0.5) / FPS
        c = "c"
        for k, a, b in zip(ch, st, en):
            if a <= t < b:
                k = k.lower()
                c = "o" if k in OPEN else ("r" if k in ROUND else ("c" if k in CLOSED_C or not k.isalpha() else "r"))
                break
        if env[f] < 0.12:
            c = "c"
        out.append(c)
    for i in range(1, len(out) - 1):  # drop single-frame flicker
        if out[i] != out[i - 1] and out[i] != out[i + 1]:
            out[i] = out[i - 1]
    return "".join(out)


t = LEAD
lines, files = [], []
for i, (who, text) in enumerate(LINES):
    wav, al = synth(text, who, i)
    env, dur = envelope(wav)
    lines.append({"who": who, "text": text, "start": round(t, 3), "dur": round(dur, 3), "end": round(t + dur, 3), "mouth": classes(env, al)})
    files.append((wav, t))
    t += dur + GAP
total = round(lines[-1]["end"] + TAIL, 3)
inputs, filt = [], []
for k, (wav, st) in enumerate(files):
    inputs += ["-i", wav]
    filt.append(f"[{k}]adelay={int(st * 1000)}|{int(st * 1000)},loudnorm=I=-16:TP=-1.5[a{k}]")
mix = "".join(f"[a{k}]" for k in range(len(files))) + f"amix=inputs={len(files)}:normalize=0,apad=whole_dur={total}[m]"
subprocess.run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", ";".join(filt + [mix]), "-map", "[m]", "-t", str(total), os.path.join(OUT, "mix.wav")], check=True)
json.dump({"fps": FPS, "total": total, "lines": lines}, open(os.path.join(HERE, "..", "timeline.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for l in lines:
    print(l["who"], "start", l["start"], "dur", l["dur"], "open", l["mouth"].count("o"), "round", l["mouth"].count("r"), "closed", l["mouth"].count("c"), "of", len(l["mouth"]))
print("total", total, "chars used", used(), "of", CAP_CHARS)
