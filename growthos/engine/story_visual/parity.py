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
    return cases


def build() -> dict:
    return {"cases": [{"name": n, "plan": p, "valid": not schema.validate_story_plan(p)} for n, p in mutations()]}


def write_parity_fixture() -> Path:
    PATH.write_text(json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return PATH
