"""Gate 3 audio: 6 ElevenLabs lines (with-timestamps) -> measured durations, word timings -> subtitle chunks, mouth classes,
plus an original locally synthesised ragtime bed and clock-bell SFX (no third-party music: no licence issue), mixed with voice-led ducking.
Hard cap on ElevenLabs characters with a ledger; keys are read from private files outside the repo and never printed."""
import base64, json, os, subprocess, sys, urllib.request, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "audio")
os.makedirs(OUT, exist_ok=True)
FPS = 24
SR = 44100
CAP_CHARS = 3000
LEDGER = os.path.join(HERE, "..", "out", "eleven_ledger.json")
KEY = open(os.path.join(os.path.expanduser("~"), "story_studio_work", ".eleven_key")).read().strip()
MODEL = "eleven_multilingual_v2"
SETTINGS = {"stability": 0.4, "similarity_boost": 0.75, "style": 0.35}
VOICES = {"pip": "IHngRooVccHyPqB4uQkG", "ros": "XrExE9yKIg1WjnnlVkGX"}
LINES = [
    ("ros", "Monsieur Pip ! Votre réveil sonne depuis ce matin !"),
    ("pip", "Impossible, madame ! Je l'ai réglé hier soir !"),
    ("ros", "Alors pourquoi il me suit partout ?"),
    ("pip", "Il croit que vous êtes en retard !"),
    ("ros", "En retard ? Moi ? Depuis quarante ans, je suis à l'heure !"),
    ("pip", "Alors... c'est moi qui suis en retard ! Mon déjeuner !"),
]
LEAD, GAP, TAIL = 0.5, 0.35, 2.6
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
    log({"gate": 3, "line": i, "who": who, "chars": len(text)})
    mp3 = os.path.join(OUT, f"g3_{i}.mp3")
    open(mp3, "wb").write(base64.b64decode(r["audio_base64"]))
    wav = os.path.join(OUT, f"g3_{i}.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-ac", "1", "-ar", str(SR), wav], check=True)
    return wav, r["alignment"]


def envelope(path):
    w = wave.open(path)
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    n = int(w.getframerate() / FPS)
    frames = len(x) // n + 1
    rms = np.array([np.sqrt(np.mean(x[i * n:(i + 1) * n] ** 2)) if len(x[i * n:(i + 1) * n]) else 0 for i in range(frames)])
    return rms / (np.percentile(rms, 95) + 1e-9), len(x) / w.getframerate()


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
    for i in range(1, len(out) - 1):
        if out[i] != out[i - 1] and out[i] != out[i + 1]:
            out[i] = out[i - 1]
    return "".join(out)


def words(al, offset):
    ws, cur, s, e = [], "", None, None
    for k, a, b in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if k.isspace():
            if cur:
                ws.append((cur, offset + s, offset + e)); cur, s = "", None
            continue
        if s is None:
            s = a
        cur += k; e = b
    if cur:
        ws.append((cur, offset + s, offset + e))
    return ws


def chunks(ws):
    subs, cur, merged = [], [], []
    for w in ws:  # a lone punctuation mark stays with the previous word
        if merged and all(c in "?!.,…" for c in w[0]):
            merged[-1] = (merged[-1][0] + " " + w[0], merged[-1][1], w[2])
        else:
            merged.append(w)
    for w in merged:
        cur.append(w)
        if len(cur) >= 3 or w[0][-1] in ".!?,…":
            subs.append(cur); cur = []
    if cur:
        subs.append(cur)
    return [{"text": " ".join(x[0] for x in g), "start": round(g[0][1] - 0.04, 3), "end": round(g[-1][2] + 0.18, 3)} for g in subs]


# ---------- timeline ----------
t = LEAD
lines, files, subs = [], [], []
for i, (who, text) in enumerate(LINES):
    wav, al = synth(text, who, i)
    env, dur = envelope(wav)
    lines.append({"who": who, "text": text, "start": round(t, 3), "dur": round(dur, 3), "end": round(t + dur, 3), "mouth": classes(env, al)})
    files.append((wav, t))
    subs += chunks(words(al, t))
    t += dur + GAP
for a, b in zip(subs, subs[1:]):
    a["end"] = round(min(a["end"], b["start"] - 0.02), 3)
total = round(lines[-1]["end"] + TAIL, 3)
L = lines
rings = [[round(L[2]["start"] + 0.35, 3), round(L[3]["start"] - 0.1, 3)], [round(L[5]["start"] + 0.2, 3), round(total - 0.6, 3)]]

# ---------- music: original ragtime bed (synthesised) ----------
def tone(f, d, vel=1.0):
    n = int(d * SR)
    x = np.arange(n) / SR
    y = sum(a * np.sin(2 * np.pi * f * (k + 1) * x) for k, a in enumerate([1.0, 0.5, 0.28, 0.14, 0.07]))
    env = np.exp(-x * 5.0) * np.minimum(1.0, x * 400)
    return y * env * vel


def mix_into(buf, sig, start):
    s = int(start * SR)
    e = min(len(buf), s + len(sig))
    if e > s:
        buf[s:e] += sig[:e - s]


NOTE = {"C": 261.63, "D": 293.66, "E": 329.63, "F": 349.23, "G": 392.0, "A": 440.0, "B": 493.88}
CH = {"C": ["C", "E", "G"], "A": ["A", "C", "E"], "D": ["D", "F", "A"], "G": ["G", "B", "D"]}
prog = ["C", "A", "D", "G", "C", "A", "D", "G"]
bass_root = {"C": 130.81, "A": 110.0, "D": 146.83, "G": 98.0}
mel = [("E", 2), ("G", 2), ("A", 1), ("G", 1), ("E", 2), ("D", 1), ("E", 1)]
bpm = 132
beat = 60.0 / bpm
music = np.zeros(int((total + 1) * SR))
bar = 4 * beat
for b in range(int(total / bar) + 2):
    ch = prog[b % len(prog)]
    for k in range(4):
        st = b * bar + k * beat
        if k in (0, 2):
            mix_into(music, tone(bass_root[ch] * (1.5 if k == 2 else 1.0), beat * 0.9, 0.9), st)
        else:
            for n in CH[ch]:
                mix_into(music, tone(NOTE[n] * 2.0, beat * 0.45, 0.28), st)
    pos = 0.0
    for n, d in mel:
        mix_into(music, tone(NOTE[n] * (4.0 if b % 2 else 2.0), d * beat * 0.5, 0.35), b * bar + pos * beat * 0.5)
        pos += d
music = music[:int(total * SR)]
music /= np.max(np.abs(music)) + 1e-9
noise = np.random.default_rng(3).normal(0, 0.012, len(music))  # vinyl hiss for the 1930s feel
music = (music * 0.9 + noise).astype(np.float32)
sfx = np.zeros(len(music))
for a, b in rings:
    n0, n1 = int(a * SR), int(min(b, total) * SR)
    x = np.arange(n1 - n0) / SR
    gate = (np.sin(2 * np.pi * 14 * x) > 0).astype(float)
    sfx[n0:n1] = (np.sin(2 * np.pi * 1760 * x) + 0.6 * np.sin(2 * np.pi * 2349 * x)) * gate * 0.25

def save(path, a):
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()

save(os.path.join(OUT, "g3_music.wav"), music)
save(os.path.join(OUT, "g3_sfx.wav"), sfx)

# ---------- mix ----------
inputs, filt = [], []
for k, (wav, st) in enumerate(files):
    inputs += ["-i", wav]
    filt.append(f"[{k}]adelay={int(st * 1000)}|{int(st * 1000)},loudnorm=I=-16:TP=-1.5[a{k}]")
n = len(files)
voice = "".join(f"[a{k}]" for k in range(n)) + f"amix=inputs={n}:normalize=0,apad=whole_dur={total}[v]"
inputs += ["-i", os.path.join(OUT, "g3_music.wav"), "-i", os.path.join(OUT, "g3_sfx.wav")]
filt += [voice, "[v]asplit[v1][v2]", f"[{n}]volume=0.55,lowpass=f=4200[m]", "[m][v2]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300[md]",
         f"[{n + 1}]volume=0.5[s]", "[v1][md][s]amix=inputs=3:normalize=0,alimiter=limit=0.95[out]"]
subprocess.run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", ";".join(filt), "-map", "[out]", "-t", str(total), os.path.join(OUT, "g3_mix.wav")], check=True)
json.dump({"fps": FPS, "total": total, "lines": lines, "subs": subs, "rings": rings}, open(os.path.join(HERE, "..", "timeline.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for l in lines:
    print(l["who"], "start", l["start"], "dur", l["dur"])
print("subs", len(subs), "total", total, "chars used", used(), "of", CAP_CHARS)
