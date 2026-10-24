"""Capped OpenAI image helper for the Gate 1B test. Key is read from a private file outside the repo.
usage: gen.py OUT.png "prompt" [--q low|medium] [--size 1024x1536] [--bg transparent|opaque] [--ref IMG.png]
Every call appends to out/cost_ledger.json and refuses to run past CAP_USD (estimates from the repo's image_model_router table)."""
import argparse, base64, json, os, sys, urllib.request, uuid

MODEL = "gpt-image-1-mini"
COST = {"low": 0.015, "medium": 0.03}  # growthos/engine/image_model_router.py, not verified live
CAP_USD = 5.0
HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "..", "out", "cost_ledger.json")
KEY = open(os.path.join(os.path.expanduser("~"), "story_studio_work", ".openai_key")).read().strip()


def spent():
    try:
        return sum(e["est_usd"] for e in json.load(open(LEDGER)))
    except FileNotFoundError:
        return 0.0


def log(entry):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    try:
        data = json.load(open(LEDGER))
    except FileNotFoundError:
        data = []
    data.append(entry)
    json.dump(data, open(LEDGER, "w"), indent=1)


def multipart(fields, files):
    b = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (name, data) in files.items():
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'.encode() + data + b"\r\n"
    return body + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("prompt")
    ap.add_argument("--q", default="low"); ap.add_argument("--size", default="1024x1536")
    ap.add_argument("--bg", default="opaque"); ap.add_argument("--ref")
    a = ap.parse_args()
    est = COST[a.q]
    if spent() + est > CAP_USD:
        sys.exit(f"cap reached: spent {spent():.3f} + {est} > {CAP_USD}")
    fields = {"model": MODEL, "prompt": a.prompt, "quality": a.q, "size": a.size, "background": a.bg, "output_format": "png"}
    if a.ref:
        body, ctype = multipart(fields, {"image": (os.path.basename(a.ref), open(a.ref, "rb").read())})
        url = "https://api.openai.com/v1/images/edits"
    else:
        body, ctype, url = json.dumps(fields).encode(), "application/json", "https://api.openai.com/v1/images/generations"
    req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {KEY}", "Content-Type": ctype})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=180))
    except urllib.error.HTTPError as e:
        sys.exit("HTTP %s: %s" % (e.code, e.read().decode()[:300]))
    open(a.out, "wb").write(base64.b64decode(r["data"][0]["b64_json"]))
    log({"out": os.path.basename(a.out), "model": MODEL, "q": a.q, "est_usd": est, "usage": r.get("usage")})
    print(f"saved {a.out}; spent_est={spent():.3f} USD of {CAP_USD}")


main()
