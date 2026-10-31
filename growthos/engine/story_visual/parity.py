"""Cas partagés avec le miroir TypeScript (growthos-web `src/lib/story-studio/visual-plan.ts`) : mêmes verdicts des deux côtés.
`write_parity_fixture()` régénère `fixtures/story_plan_parity.json` ; un test garantit que le fichier est à jour."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from . import sample, schema

PATH = Path(__file__).parent / "fixtures" / "story_plan_parity.json"


def _m(base, fn):
    plan = copy.deepcopy(base())
    fn(plan)
    return plan


def mutations() -> list[tuple[str, dict]]:
    f, m = sample.factual_plan, sample.moral_plan
    cases = [("valid factual", f()), ("valid moral", m())]
    def add(name, base, fn):
        cases.append((name, _m(base, fn)))
    add("schema version 2", m, lambda p: p.update(schema_version=2))
    add("unsafe story id", m, lambda p: p.update(story_id="../x"))
    add("unknown story type", m, lambda p: p.update(story_type="x"))
    add("unknown language", m, lambda p: p.update(language="de"))
    add("unknown art direction", m, lambda p: p.update(art_direction="x"))
    add("duration too short", m, lambda p: p.update(target_duration_s=10))
    add("duration far from scenes", m, lambda p: p.update(target_duration_s=120))
    add("empty title", m, lambda p: p.update(title=" "))
    add("moral classified verified", m, lambda p: p.update(factuality="verified"))
    add("true classified fiction", f, lambda p: p.update(factuality="fiction"))
    add("verified without sources", f, lambda p: p.update(sources=[]))
    add("source http url", f, lambda p: p["sources"][0].update(url="http://example.com"))
    add("source private ip", f, lambda p: p["sources"][0].update(url="https://10.0.0.5/x"))
    add("source metadata ip", f, lambda p: p["sources"][0].update(url="https://169.254.169.254/x"))
    add("source credentials", f, lambda p: p["sources"][0].update(url="https://u:p@example.com/"))
    add("source localhost", f, lambda p: p["sources"][0].update(url="https://localhost/x"))
    add("fact cites unknown source", f, lambda p: p["scenes"][1].update(source_ids=["nope"]))
    add("interpretation without source", f, lambda p: p["scenes"][6].update(source_ids=[]))
    add("fact without source", f, lambda p: p["scenes"][6].update(claim_kind="fact", source_ids=[]))
    add("quote without source", f, lambda p: p["scenes"][1].update(quote="x"))
    add("quote with source", f, lambda p: p["scenes"][1].update(quote="x", quote_source_id="nobel"))
    add("fiction scene as fact", m, lambda p: p["scenes"][0].update(claim_kind="fact"))
    add("invented quote of real person", m, lambda p: p["scenes"][0].update(quote="x", quote_attributed_to_real_person=True))
    add("too few scenes", m, lambda p: p.update(scenes=p["scenes"][:3]))
    add("beats out of order", m, lambda p: (p["scenes"][0].update(beat="resolution"), p["scenes"][-1].update(beat="hook")))
    add("missing revelation", m, lambda p: [s.update(beat="development") for s in p["scenes"] if s["beat"] == "revelation"])
    add("duplicate scene id", m, lambda p: p["scenes"][1].update(id="s1"))
    add("scene without direction key", m, lambda p: p["scenes"][2]["visual_direction"].pop("omit"))
    add("empty visual intention", m, lambda p: p["scenes"][3].update(visual_intention=""))
    add("html in on-screen text", m, lambda p: p["scenes"][0].update(on_screen_text="<b>x</b>"))
    add("on-screen text too long", m, lambda p: p["scenes"][0].update(on_screen_text="x" * 91))
    add("unknown transition", m, lambda p: p["scenes"][0].update(transition="wipe"))
    add("unknown camera", m, lambda p: p["scenes"][0].update(camera="shake"))
    add("scene duration 25s", m, lambda p: p["scenes"][0].update(duration_s=25))
    add("non finite duration", m, lambda p: p["scenes"][0].update(duration_s=None))
    add("unknown character ref", m, lambda p: p["scenes"][0].update(characters=["ghost"]))
    add("character missing identity", m, lambda p: p["characters"][0].pop("distinctive"))
    add("duplicate character id", m, lambda p: p["characters"].append(copy.deepcopy(p["characters"][0])))
    add("narration too long", m, lambda p: p["scenes"][0].update(narration="x" * 421))
    add("no characters is fine", m, lambda p: (p.update(characters=[]), [s.update(characters=[]) for s in p["scenes"]]))
    # entrées hostiles : types inattendus, bornes, URL déguisées, voix (revue indépendante)
    add("hostile characters list", m, lambda p: p["scenes"][0].update(characters=[{}]))
    add("hostile source ids", f, lambda p: p["scenes"][1].update(source_ids=[{}]))
    add("hostile quote source", f, lambda p: p["scenes"][1].update(quote="x", quote_source_id={}))
    add("scenes not a list", m, lambda p: p.update(scenes="x"))
    add("visual direction as list", m, lambda p: p["scenes"][0].update(visual_direction=[1]))
    add("visual direction oversized", m, lambda p: p["scenes"][0]["visual_direction"].update(feel="x" * 301))
    add("visual direction non-string", m, lambda p: p["scenes"][0]["visual_direction"].update(omit=["a"]))
    add("character environment oversized", m, lambda p: p["characters"][0].update(environment="y" * 301))
    add("character negative object", m, lambda p: p["characters"][0].update(negative={"a": 1}))
    add("source trailing dot localhost", f, lambda p: p["sources"][0].update(url="https://localhost./x"))
    add("source hex ip", f, lambda p: p["sources"][0].update(url="https://0x7f.0.0.1/x"))
    add("source decimal ip", f, lambda p: p["sources"][0].update(url="https://2130706433/x"))
    add("source ipv6", f, lambda p: p["sources"][0].update(url="https://[::1]/x"))
    add("source public ip literal", f, lambda p: p["sources"][0].update(url="https://8.8.8.8/x"))
    add("valid voice id", m, lambda p: p.update(voice_id="VoiceId12345"))
    add("bad voice id", m, lambda p: p.update(voice_id="a/b"))
    add("short voice id", m, lambda p: p.update(voice_id="abc"))
    # revue de parité (Unicode, types, URL) : mêmes verdicts exigés des deux côtés
    add("emoji narration within limit", m, lambda p: p["scenes"][0].update(narration="😀" * 300))
    add("emoji narration over limit", m, lambda p: p["scenes"][0].update(narration="😀" * 421))
    add("emoji url within limit", f, lambda p: p["sources"][0].update(url="https://example.com/" + "😀" * 250))
    add("title is only NEL", m, lambda p: p.update(title="\x85"))
    add("title is only BOM", m, lambda p: p.update(title="\ufeff"))
    add("title is separators", m, lambda p: p.update(title="\x1c\x1c"))
    add("schema version true", m, lambda p: p.update(schema_version=True))
    add("schema version float", m, lambda p: p.update(schema_version=1.0))
    add("huge duration", m, lambda p: p.update(target_duration_s=10 ** 400))
    add("huge scene duration", m, lambda p: p["scenes"][0].update(duration_s=10 ** 400))
    add("invented quote empty list flag", m, lambda p: p["scenes"][0].update(quote="x", quote_attributed_to_real_person=[]))
    add("invented quote true flag", m, lambda p: p["scenes"][0].update(quote="x", quote_attributed_to_real_person=True))
    add("source id empty object", f, lambda p: p["sources"][0].update(id={}))
    add("source title list", f, lambda p: p["sources"][0].update(title=[]))
    for name, url in (("scheme without slashes", "https:example.com/x"), ("single slash", "https:/example.com/x"), ("idn host", "https://exämple.com/"),
                      ("percent host", "https://exa%6dple.com/"), ("ideographic dot", "https://example。com/"),
                      ("backslash userinfo", "https://example.com\\@evil.com/"), ("bad port", "https://example.com:abc/x"),
                      ("port too high", "https://example.com:99999/x"), ("good port", "https://example.com:8443/x"),
                      ("query only", "https://example.com?q=1"), ("no path", "https://example.com"), ("uppercase host", "https://EXAMPLE.com/x"),
                      ("space in url", "https://example.com/a b")):
        add("url " + name, f, lambda p, u=url: p["sources"][0].update(url=u))
    return cases


def build() -> dict:
    return {"cases": [{"name": n, "plan": p, "valid": not schema.validate_story_plan(p)} for n, p in mutations()]}


def write_parity_fixture() -> Path:
    PATH.write_text(json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return PATH


API_PATH = Path(__file__).parent / "fixtures" / "story_api_parity.json"


def api_cases() -> dict:
    """Cas d'API (requêtes -> verdict, code d'erreur, invalidations) partagés avec `visual-api.ts` côté web."""
    from . import api
    plan = sample.moral_plan()
    ok = {"idea": "Pourquoi on procrastine", "story_type": "knowledge"}
    src = [{"id": "a", "title": "t", "url": "https://www.nobelprize.org/x"}]
    plan_requests = [
        ("duration 60.0", dict(ok, target_duration_s=60.0)), ("voice id integer", dict(ok, voice_id=12345678)),
        ("emoji idea two chars", dict(ok, idea="😀😀")), ("emoji idea long", dict(ok, idea="😀" * 600)),
        ("idea control chars", dict(ok, idea="\x1c\x1c\x1c")), ("idea nel suffix", dict(ok, idea="ab\x85")), ("idea bom", dict(ok, idea="\ufeffab")),
        ("source id empty object", dict(ok, sources=[dict(src[0], id={})])), ("source title empty list", dict(ok, sources=[dict(src[0], title=[])])),
        ("minimal", ok), ("full", dict(ok, language="en", target_duration_s=90, art_direction="conceptual_metaphor", voice_id="VoiceId12345")),
        ("true with source", dict(ok, story_type="true", sources=src)), ("true without source", dict(ok, story_type="true")),
        ("unknown field", dict(ok, tenant_id="other")), ("bad type", dict(ok, story_type="x")), ("empty idea", dict(ok, idea="")),
        ("idea too long", dict(ok, idea="x" * 1001)), ("duration low", dict(ok, target_duration_s=10)),
        ("duration bool", dict(ok, target_duration_s=True)), ("duration float", dict(ok, target_duration_s=60.5)),
        ("bad voice", dict(ok, voice_id="a/b")), ("unsafe source", dict(ok, sources=[dict(src[0], url="http://127.0.0.1/x")])),
        ("sources not list", dict(ok, sources="x")), ("body list", []), ("body null", None), ("bad language", dict(ok, language="de")),
    ]
    edits = [
        ("prototype key constructor", {"scene_id": "s2", "constructor": "x"}), ("prototype key toString", {"scene_id": "s2", "toString": "x"}),
        ("prototype key __proto__", {"scene_id": "s2", "__proto__": "x"}), ("camera null on absent", {"scene_id": "s2", "camera": None}),
        ("direction reordered", {"scene_id": "s2", "visual_direction": dict(reversed(list(plan["scenes"][1]["visual_direction"].items())))}),
        ("scene id not a string", {"scene_id": 5, "narration": "x"}),
        ("narration", {"scene_id": "s2", "narration": "Another line."}), ("on screen text", {"scene_id": "s2", "on_screen_text": "New"}),
        ("same narration", {"scene_id": "s2", "narration": plan["scenes"][1]["narration"]}),
        ("image prompt", {"scene_id": "s4", "image_prompt": "A lantern in the dark."}),
        ("tone", {"scene_id": "s4", "emotional_tone": "joy"}),
        ("unknown scene", {"scene_id": "zz", "narration": "x"}), ("immutable id", {"scene_id": "s1", "id": "s9"}),
        ("immutable beat", {"scene_id": "s1", "beat": "resolution"}), ("no change fields", {"scene_id": "s1"}),
        ("html text", {"scene_id": "s1", "on_screen_text": "<b>"}), ("not an object", "x"),
        ("narration too long", {"scene_id": "s1", "narration": "x" * 421}),
    ]
    regens = [("ok", {"scene_id": "s3"}), ("unknown", {"scene_id": "zz"}), ("extra field", {"scene_id": "s3", "force": True}),
              ("empty", {}), ("null", None)]
    replaces = []
    base = copy.deepcopy(plan["scenes"][2])
    replaces.append(("replace ok", {"scene_id": "s3", "scene": dict(base, narration="Replaced narration.")}))
    replaces.append(("replace id hijack", {"scene_id": "s3", "scene": dict(base, id="hijack")}))
    replaces.append(("replace incomplete", {"scene_id": "s3", "scene": {"id": "s3"}}))
    replaces.append(("replace unknown scene", {"scene_id": "zz", "scene": base}))
    replaces.append(("replace no scene", {"scene_id": "s3"}))
    cases = []
    for name, body in replaces:
        new, meta = api.replace_scene(plan, body)
        cases.append({"kind": "replace_scene", "name": name, "body": body, "valid": new is not None,
                      "code": meta["error"]["code"] if new is None else None,
                      "invalidated": meta["invalidated"] if new is not None else None})
    for name, body in plan_requests:
        request, err = api.parse_plan_request(body)
        cases.append({"kind": "plan_request", "name": name, "body": body, "valid": err is None,
                      "code": err["error"]["code"] if err else None})
    for name, body in edits:
        new, meta = api.edit_scene(plan, body)
        cases.append({"kind": "edit_scene", "name": name, "body": body, "valid": new is not None,
                      "code": meta["error"]["code"] if new is None else None,
                      "invalidated": meta["invalidated"] if new is not None else None})
    for name, body in regens:
        sid, err = api.parse_regenerate(plan, body)
        cases.append({"kind": "regenerate", "name": name, "body": body, "valid": err is None,
                      "code": err["error"]["code"] if err else None})
    return {"plan": plan, "cases": cases}


COST_PATH = Path(__file__).parent / "fixtures" / "story_cost_parity.json"


def cost_cases() -> dict:
    """Estimations (mêmes arrondis par ligne, mêmes comptes de caractères) partagées avec `estimateEpisode` côté web."""
    from . import cost
    rate_sets = {
        "full": {"STORY_IMAGE_USD_EACH": "0.08", "ELEVENLABS_USD_PER_1K_CHARS": "0.18", "SCRIPT_PRICE_IN_PER_M": "1",
                 "SCRIPT_PRICE_OUT_PER_M": "4", "STORY_PLAN_TOKENS_IN": "4000", "STORY_PLAN_TOKENS_OUT": "3500",
                 "STORY_RENDER_USD": "0", "STORY_STORAGE_USD": "0.01"},
        "tiny lines": {"STORY_IMAGE_USD_EACH": "0.1", "ELEVENLABS_USD_PER_1K_CHARS": "0.2", "SCRIPT_PRICE_IN_PER_M": "1",
                       "SCRIPT_PRICE_OUT_PER_M": "1", "STORY_PLAN_TOKENS_IN": "10", "STORY_PLAN_TOKENS_OUT": "10",
                       "STORY_RENDER_USD": "0.00004", "STORY_STORAGE_USD": "0.00004"},
        "images only": {"STORY_IMAGE_USD_EACH": "0.1"}, "nothing": {}, "zero rates": {"STORY_IMAGE_USD_EACH": "0", "ELEVENLABS_USD_PER_1K_CHARS": "0",
                       "SCRIPT_PRICE_IN_PER_M": "0", "SCRIPT_PRICE_OUT_PER_M": "0", "STORY_PLAN_TOKENS_IN": "1", "STORY_PLAN_TOKENS_OUT": "1",
                       "STORY_RENDER_USD": "0", "STORY_STORAGE_USD": "0"},
    }
    emoji = sample.moral_plan()
    emoji["scenes"][0]["narration"] = "  " + "😀" * 40 + "\x85  "
    plans = {"moral": sample.moral_plan(), "factual": sample.factual_plan(), "emoji narration": emoji}
    out = []
    for pn, plan in plans.items():
        for rn, env in rate_sets.items():
            est = cost.estimate_episode(plan, env)
            out.append({"name": f"{pn} / {rn}", "plan": pn, "rates": rn, "env": env, "total_usd": est["total_usd"],
                        "complete": est["complete"], "unpriced": est["unpriced"], "images": est["images"],
                        "voice_characters": est["voice_characters"],
                        "status": cost.check_budget(est, cost.Budget())["status"]})
    return {"plans": plans, "cases": out}


def write_cost_fixture() -> Path:
    COST_PATH.write_text(json.dumps(cost_cases(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return COST_PATH


def write_api_fixture() -> Path:
    API_PATH.write_text(json.dumps(api_cases(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return API_PATH
