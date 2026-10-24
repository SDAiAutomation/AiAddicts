"""Writing bench for Story Studio: does a better writing process make better stories, measured blind?

Systems under test (same concepts, same characters, same output format):
  A  production today: one call, gpt-5-mini, the prompt of animated-proposal.ts
  C  the same prompt on a stronger model (separates "model" from "process")
  B  the new process: premises -> pick -> scenes -> punch-up against the rubric, on the stronger model

Judge: a model reads two stories in random order (each pair is judged twice with the order swapped) and scores the rubric.
This measures what an LLM judge prefers, not what an audience watches: the final call stays with a human (see report).
The key is read from a private file outside the repo. Every call is counted; the run stops at TOKEN_CAP.

usage: bench.py OUT_DIR [--writer gpt-5.5] [--judge gpt-5.5] [--only 1,2,3]"""
import argparse
import json
import os
import random
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = open(os.path.join(os.path.expanduser("~"), "story_studio_work", ".openai_key")).read().strip()
TOKEN_CAP = 1_200_000
USED = {"in": 0, "out": 0}

SETTINGS = ["cafe_terrace", "clock_shop", "factory_alley", "street"]
SHOTS = ["wide", "medium", "close_up"]
MOODS = ["neutral", "worry", "angry", "surprise", "joy", "puzzled", "panic"]
GESTURES = ["idle", "accuse", "defend", "wring", "indignant", "clutch_head", "point", "hands_on_hips", "shrug", "wave", "run_away"]
CAST = "Pip: an anxious shop clerk in a bow tie, polite, over-explains, panics easily. Madame Rosette: the shopkeeper in a flowered hat, confident, brisk, always has an answer ready."

CONCEPTS = [
    "Pip essaie de rendre un objet défectueux à Madame Rosette, mais il n'a pas son ticket de caisse.",
    "Rosette découvre que son horloge la plus chère a une heure d'avance depuis dix ans.",
    "Pip veut démissionner, mais Rosette parle plus vite que lui.",
    "Un client mystérieux veut acheter du temps à la boutique.",
    "Rosette lance une promotion « tout doit disparaître » qui ne finit jamais.",
    "Pip jure qu'il n'a jamais menti, et le réveil sonne à chaque phrase.",
    "Une garantie à vie : la boutique n'existera plus demain.",
    "Pip découvre pourquoi la boutique n'a pas de fenêtre.",
    "Rosette vend un abonnement mensuel à l'heure qu'il est.",
    "Un conseil de sagesse de Rosette se retourne contre elle.",
    "Pip a trouvé un trésor dans le mur de la boutique, qui appartient à… tout le monde.",
    "L'assurance couvre tout, sauf ce qui arrive vraiment.",
]

# ---- the production prompt (animated-proposal.ts), as is ----
PROD_SYSTEM = f"""You write the scenes of a short animated cartoon story played by the given characters. Return JSON only:
{{"scenes":[{{"speaker":"exact character name","dialogue":"...","setting":"...","shot":"...","transition":"cut|fade","moods":{{"<character name>":"..."}},"gestures":{{"<character name>":"..."}},"clock":false}}]}}
Rules: each scene is spoken by exactly one of the listed characters. Dialogue is one or two short sentences in the idea's language, at most 400 characters, with no stage directions and no quotation marks. Choose setting from [{", ".join(SETTINGS)}], shot from [{", ".join(SHOTS)}], moods from [{", ".join(MOODS)}], gestures from [{", ".join(GESTURES)}]. Vary settings and shots across the story. clock is true only when a ringing alarm clock matters in the scene. The story is fiction: never present invented events as verified facts."""

# ---- the new process ----
RUBRIC = """1 hook: the first line makes you want the second (a conflict, a question, a surprise), no throat-clearing
2 stakes: it is clear within two lines what each character wants and what stands in the way
3 escalation: every scene makes things worse or funnier than the one before; nothing repeats
4 payoff: the last scenes deliver a twist or turn that reframes what came before, and it is earned by setup
5 button: the very last line is short, quotable, and lands the joke or the feeling
6 voice: Pip and Rosette sound different and stay in character; lines are speakable aloud, short, natural spoken French
7 specificity: concrete, surprising details instead of generic phrases; no filler
8 economy: nothing could be cut; no scene exists only to explain
9 clarity and faithfulness: a stranger understands every line the first time they hear it, and the story stays faithful to the creator's idea (their situation, their objects, their characters' relationship)"""

PREMISES = f"""You are a comedy writer for 20-30 second animated shorts in spoken French. Characters: {CAST}
Given the creator's idea, invent FOUR genuinely different premises. For each: "hook" (the first line spoken), "conflict", "escalation" (how it gets worse in 2 steps), "twist" (the turn that reframes the story, set up early), "button" (the final line). Stay faithful to the creator's situation and objects: be surprising INSIDE their idea, never replace it. Avoid the obvious first idea; avoid moral lessons; every line must be understood on first hearing; keep it fiction and light.
Then choose the one that would make a stranger watch to the end and share it, judged on: surprise of the twist, clarity in 25 seconds, fit with the two characters. Return JSON only: {{"premises":[{{"hook":"","conflict":"","escalation":"","twist":"","button":""}} x4],"chosen":0-3,"why":"one sentence"}}"""

WRITE = f"""You write a 5 to 6 scene animated short in spoken French from a chosen premise. Characters: {CAST}
Hard rules: each scene is ONE line spoken by one character, at most 14 words, speakable aloud; the two characters alternate unless a double line is funnier; no stage directions, no quotation marks; the first line is the hook; the last line is the button; the twist is planted before it pays off.
Return JSON only: {{"title":"","scenes":[{{"speaker":"exact character name","dialogue":"","setting":"","shot":"","transition":"cut|fade","moods":{{"<name>":""}},"gestures":{{"<name>":""}},"clock":false}}]}}
setting in [{", ".join(SETTINGS)}], shot in [{", ".join(SHOTS)}], moods in [{", ".join(MOODS)}], gestures in [{", ".join(GESTURES)}]. Vary settings and shots; use a close_up for the twist and the button. clock true only when a ringing alarm clock matters."""

PUNCH = f"""You are the script editor. Score the draft against this rubric (1-10 each), find the two weakest points, then REWRITE the whole script to fix them, keeping the same JSON format, the same catalogs, at most 14 words per line, 5 to 6 scenes. Cut anything generic; make each line more specific and more surprising; make sure the last line is the strongest.
Rubric:
{RUBRIC}
Return JSON only: {{"scores":{{"hook":0,"stakes":0,"escalation":0,"payoff":0,"button":0,"voice":0,"specificity":0,"economy":0,"clarity":0}},"weakest":["",""],"title":"","scenes":[...same format...]}}"""

JUDGE = f"""You judge two short animated scripts (spoken French) written from the same idea. Score each 1-10 on this rubric, then pick the one a stranger would more likely watch to the end and share. Be strict and specific; do not favour the longer or the first.
Rubric:
{RUBRIC}
Return JSON only: {{"X":{{"hook":0,"stakes":0,"escalation":0,"payoff":0,"button":0,"voice":0,"specificity":0,"economy":0,"clarity":0}},"Y":{{...}},"winner":"X"|"Y","reason":"two sentences"}}"""


def chat(model, system, user, effort="low"):
    if USED["in"] + USED["out"] > TOKEN_CAP:
        sys.exit("token cap reached")
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}}
    if effort:
        body["reasoning_effort"] = effort
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=300))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")
    u = r.get("usage", {})
    USED["in"] += u.get("prompt_tokens", 0)
    USED["out"] += u.get("completion_tokens", 0)
    return json.loads(r["choices"][0]["message"]["content"])


def user_prompt(concept, n):
    return f"Idea: {concept}\nCharacters: Pip, Madame Rosette\nNumber of scenes: {n}"


def sys_a(concept, model):
    return chat(model, PROD_SYSTEM, user_prompt(concept, 5), "minimal" if model.endswith("mini") else "low")


def sys_b(concept, model):
    prem = chat(model, PREMISES, f"Idea: {concept}", "medium")
    chosen = prem["premises"][int(prem["chosen"])]
    draft = chat(model, WRITE, f"Idea: {concept}\nChosen premise: {json.dumps(chosen, ensure_ascii=False)}", "low")
    final = chat(model, PUNCH, f"Idea: {concept}\nDraft: {json.dumps(draft, ensure_ascii=False)}", "medium")
    return {"title": final.get("title", ""), "scenes": final["scenes"], "premise": chosen, "scores": final.get("scores"), "weakest": final.get("weakest")}


def as_text(story):
    return "\n".join(f"{s['speaker']}: {s['dialogue']}" for s in story["scenes"])


def judge(model, concept, first, second):
    out = chat(model, JUDGE, f"Idea: {concept}\n\nSCRIPT X\n{as_text(first)}\n\nSCRIPT Y\n{as_text(second)}", "low")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--writer", default="gpt-5.5")
    ap.add_argument("--judge", default="gpt-5.5")
    ap.add_argument("--only")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    idx = [int(x) - 1 for x in a.only.split(",")] if a.only else range(len(CONCEPTS))
    rnd = random.Random(7)
    rows = []
    for i in idx:
        concept = CONCEPTS[i]
        stories = {"A": sys_a(concept, "gpt-5-mini"), "C": sys_a(concept, a.writer), "B": sys_b(concept, a.writer)}
        verdicts = []
        for p, q in (("B", "A"), ("C", "A"), ("B", "C")):
            for swap in (False, True):
                x, y = (q, p) if swap else (p, q)
                v = judge(a.judge, concept, stories[x], stories[y])
                win = x if v["winner"] == "X" else y
                verdicts.append({"pair": f"{p}>{q}", "order": f"{x}/{y}", "winner": win, "reason": v.get("reason"), "X": v.get("X"), "Y": v.get("Y"), "x": x, "y": y})
        rows.append({"concept": concept, "stories": stories, "verdicts": verdicts})
        json.dump(rows, open(os.path.join(a.out, "bench.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{i + 1}/{len(CONCEPTS)} done; tokens in={USED['in']} out={USED['out']}", flush=True)


if __name__ == "__main__":
    main()
