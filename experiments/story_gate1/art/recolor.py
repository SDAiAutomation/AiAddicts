"""Repaint the prototype sprites in a second look with OpenAI image edits (capped; the key is read from a private file outside the repo).

The rig reads sprites by NAME and anchors limbs to their silhouettes, so a repainted sprite must keep the exact size and the exact
alpha of the original: each sprite is placed on a transparent canvas, repainted, cut back out, resized to its original size and
masked with the original alpha. Only the colour and the shading may change.

usage: recolor.py PACK_DIR_OUT STYLE [--only name,name] [--q low|medium]
Every call appends to out/cost_ledger.json and refuses to run past CAP_USD."""
import argparse
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

from PIL import Image

MODEL = "gpt-image-1-mini"
COST = {"low": 0.015, "medium": 0.03}  # growthos/engine/image_model_router.py, not verified live
CAP_USD = 5.0
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "sprites")
LEDGER = os.path.join(HERE, "..", "out", "cost_ledger.json")
KEY = open(os.path.join(os.path.expanduser("~"), "story_studio_work", ".openai_key")).read().strip()

COMMON = ("Repaint this exact cartoon sprite in full colour, in the style of an early-1930s two-strip Technicolor cel cartoon: flat gouache colours, "
          "warm cream paper whites, a little soft cel shading. Keep the black ink outlines, the shape, the pose, the proportions and the silhouette "
          "EXACTLY as they are: change only the colours. Do not add, remove, move or redraw anything. Transparent background.")

SPRITES = {
    # Pip
    "hat": "The black bowler hat becomes warm brown felt with a darker hat band.",
    "torso": "The black suit becomes deep teal; the bow tie stays vermilion red; the shirt front stays cream.",
    "glove_l": "The gloves stay cream white with soft warm shading.", "glove_r": "The gloves stay cream white with soft warm shading.",
    "shoe_l": "The black shoe becomes glossy oxblood brown with a soft highlight.", "shoe_r": "The black shoe becomes glossy oxblood brown with a soft highlight.",
    "head_neutral": "The white face becomes warm peach-cream; the glasses frames, moustache and eyebrows stay black.",
    "head_talk": "The white face becomes warm peach-cream; the glasses frames, moustache and eyebrows stay black.",
    "head_worried": "The white face becomes warm peach-cream; the glasses frames, moustache and eyebrows stay black.",
    "head_o": "The white face becomes warm peach-cream; the glasses frames, moustache and eyebrows stay black.",
    "head_blank_pip": "The white face becomes warm peach-cream; the glasses frames, moustache and nose stay as drawn, the nose a little pinker.",
    "clock": "The case becomes polished brass yellow, the bells stay vermilion red, the clock face stays cream.",
    # Rosette
    "ros_head_blank": "The white face becomes warm peach-cream; the hat becomes dark plum with a vermilion red flower; the hair stays dark brown.",
    "ros_head_blank2": "The white face becomes warm peach-cream; the hat becomes dark plum with a vermilion red flower; the hair stays dark brown.",
    "ros_torso": "The black dress becomes deep plum purple with a small cream collar.",
    "ros_glove_l": "The gloves stay cream white with soft warm shading.", "ros_glove_r": "The gloves stay cream white with soft warm shading.",
    "ros_shoe_l": "The black shoe becomes dark plum-brown with a soft highlight.", "ros_shoe_r": "The black shoe becomes dark plum-brown with a soft highlight.",
}
BACKGROUNDS = {
    "bg_shop": "A clockmaker's shop interior: warm honey-wood walls and floor boards, brass clocks, amber lamp light.",
    "bg_alley": "A factory alley: blue-grey brick walls, a smoking chimney, an orange-pink sunset sky.",
    "bg_cafe": "A cafe terrace: a red and cream striped awning, teal window shutters, warm stone cobbles.",
    "bg_street": "A cobbled town street: pastel cream and rose buildings, a soft blue sky, a black iron street lamp.",
}


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


def edit(png: bytes, prompt: str, q: str, size: str, transparent: bool, tag: str) -> Image.Image:
    est = COST[q]
    if spent() + est > CAP_USD:
        sys.exit(f"cap reached: spent {spent():.3f} + {est} > {CAP_USD}")
    fields = {"model": MODEL, "prompt": prompt, "quality": q, "size": size, "output_format": "png"}
    if transparent:
        fields["background"] = "transparent"
    body, ctype = multipart(fields, {"image": ("ref.png", png)})
    req = urllib.request.Request("https://api.openai.com/v1/images/edits", data=body, headers={"Authorization": f"Bearer {KEY}", "Content-Type": ctype})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=240))
    except urllib.error.HTTPError as e:
        sys.exit("HTTP %s: %s" % (e.code, e.read().decode()[:300]))
    log({"out": tag, "model": MODEL, "q": q, "est_usd": est, "usage": r.get("usage")})
    return Image.open(io.BytesIO(base64.b64decode(r["data"][0]["b64_json"]))).convert("RGBA")


def repaint_sprite(name: str, extra: str, q: str) -> Image.Image:
    src = Image.open(os.path.join(SRC, name + ".png")).convert("RGBA")
    w, h = src.size
    canvas_w, canvas_h, size = (1024, 1024, "1024x1024") if w * 1.0 / h > 0.75 else (1024, 1536, "1024x1536")
    scale = min((canvas_w - 40) / w, (canvas_h - 40) / h)
    sw, sh = max(int(w * scale), 1), max(int(h * scale), 1)
    ox, oy = (canvas_w - sw) // 2, (canvas_h - sh) // 2
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    canvas.alpha_composite(src.resize((sw, sh), Image.LANCZOS), (ox, oy))
    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    out = edit(buf.getvalue(), f"{COMMON} {extra}", q, size, True, name + ".png")
    out = out.resize((canvas_w, canvas_h), Image.LANCZOS).crop((ox, oy, ox + sw, oy + sh)).resize((w, h), Image.LANCZOS)
    alpha = src.getchannel("A")  # the original silhouette is kept exactly
    out.putalpha(alpha)
    return out


def repaint_background(name: str, extra: str, q: str) -> Image.Image:
    src = Image.open(os.path.join(SRC, name + ".png")).convert("RGB")
    buf = io.BytesIO()
    src.save(buf, "PNG")
    prompt = ("Repaint this exact cartoon background in full colour, in the style of an early-1930s two-strip Technicolor cel cartoon: flat gouache colours, "
              "soft cel shading, gentle warm light. Keep every line, object, perspective and composition EXACTLY as they are: change only the colours. "
              "Do not add or remove anything, no characters, no text. " + extra)
    out = edit(buf.getvalue(), prompt, q, "1024x1536", False, name + ".png").convert("RGB")
    return out.resize(src.size, Image.LANCZOS).convert("RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("style")
    ap.add_argument("--only")
    ap.add_argument("--q", default="low")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    wanted = set(a.only.split(",")) if a.only else None
    for name, extra in {**SPRITES, **BACKGROUNDS}.items():
        if wanted and name not in wanted:
            continue
        img = repaint_background(name, extra, a.q) if name in BACKGROUNDS else repaint_sprite(name, extra, a.q)
        img.save(os.path.join(a.out_dir, name + ".png"))
        print(f"{name}: ok, spent_est={spent():.3f} USD of {CAP_USD}", flush=True)


if __name__ == "__main__":
    main()
