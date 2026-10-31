"""Reconstruit et VÉRIFIE la baseline A du harness P0 depuis des sources figées, sans chemin local ni état du worktree courant.

    python -m growthos.engine.narrative_review.harness.rebuild_baseline \
        --web-checkout <growthos-web au commit figé> --engine-checkout <AiAddicts au commit figé (PR #103)> [--write]

Sources FIGÉES = un commit git par dépôt (dans `baseline_manifest.json`) + le SHA-256 de chaque fichier source utilisé. Les sources ne sont PAS
copiées dans ce dépôt (growthos-web est privé ; les copier divulguerait du code produit) : un réviseur qui a accès aux deux dépôts rejoue ce
module et obtient, ou n'obtient pas, exactement les fichiers de `fixtures/`. Sans `--write` : vérification seule (code de sortie 1 au moindre écart).
Aucun accès réseau : lecture de fichiers, `git rev-parse`/`git show` locaux, `node` (rendu Standard) et `python` (rendu Story Visual).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .corpus import FIXTURES, load_corpus, sha256_text

RENDER_SCRIPT = "render_standard_A.mjs"
STANDARD_RENDER = {"language": "fr", "platform": "youtube", "profile": "standard"}
WEB_FILES = ("src/app/(app)/content/ai-actions.ts", "src/lib/script-length.ts", "src/lib/narrative-perspective.ts",
             "src/lib/niche-narrative.ts", "src/app/(app)/content/visual-styles.ts")
VISUAL_FILE = "growthos/engine/story_visual/formats.py"
# Type d'histoire Story Visual par sujet pilote (le sujet « documentaire » N05 est une histoire vraie sourcée ; la simulation N13, une explication).
STORY_TYPE_BY_TOPIC = {"N01": "moral", "N04": "metaphor", "N05": "true", "N13": "knowledge", "N18": "moral"}
VISUAL_RENDER = {"language": "fr", "target_duration_s": 75}


SHINGLES_FILE = "standard_A_shingles.json"
SHINGLE_WINDOW, SHINGLE_STRIDE = 80, 40


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def shingle_hashes(text: str) -> list[str]:
    """Empreintes (irréversibles) de fenêtres de 80 caractères du texte normalisé, une toutes les 40. Elles permettent de détecter la
    réintroduction du prompt, même partielle (>= 120 caractères contigus), sans en stocker une seule phrase."""
    n = _normalize(text)
    return sorted({_h(n[i:i + SHINGLE_WINDOW]) for i in range(0, max(len(n) - SHINGLE_WINDOW + 1, 1), SHINGLE_STRIDE)})


def contains_shingle(text: str, hashes: set[str]) -> bool:
    """Vrai si `text` contient une fenêtre du prompt protégé (balayage de TOUS les décalages)."""
    n = _normalize(text)
    return any(_h(n[i:i + SHINGLE_WINDOW]) in hashes for i in range(len(n) - SHINGLE_WINDOW + 1))


def load_shingles() -> set[str]:
    return set(json.loads((FIXTURES / SHINGLES_FILE).read_text(encoding="utf-8"))["hashes"])


def file_sha256(path: Path) -> str:
    return sha256_text(path.read_text(encoding="utf-8"))


def _git(checkout: Path, *args: str) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, check=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def check_commit(checkout: Path, expected: str, label: str) -> list[str]:
    head = _git(checkout, "rev-parse", "HEAD")
    if head is None:
        return [f"{label}: not a git checkout, the source commit cannot be proven (file hashes still verified)"]
    return [] if head.startswith(expected) else [f"{label}: checkout is at {head[:12]}, expected {expected}"]


def check_sources(checkout: Path, expected_hashes: dict[str, str], label: str) -> list[str]:
    problems = []
    for rel, wanted in expected_hashes.items():
        path = checkout / rel
        if not path.is_file():
            problems.append(f"{label}: missing source file {rel}")
        elif file_sha256(path) != wanted:
            problems.append(f"{label}: {rel} differs from the frozen source (sha256 mismatch)")
    return problems


def render_standard(web_checkout: Path, out: Path) -> str:
    """Rend le prompt A Standard ; retourne le texte (LF)."""
    script = FIXTURES / RENDER_SCRIPT
    cmd = ["node", str(script), "--checkout", str(web_checkout), "--language", STANDARD_RENDER["language"],
           "--platform", STANDARD_RENDER["platform"], "--profile", STANDARD_RENDER["profile"], "--out", str(out)]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise RuntimeError(f"node render failed: {done.stderr[-400:]}")
    return out.read_text(encoding="utf-8").replace("\r\n", "\n")


_VISUAL_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from growthos.engine.story_visual import formats
payload = json.loads(sys.argv[2])
out = {}
for topic_id, story_type in payload["story_types"].items():
    t = payload["topics"][topic_id]
    sources = [{"id": s["source_id"], "title": s["title"], "url": s["url"]} for s in t["sources"]]
    direction = formats.strategy_for(story_type)["default_art_direction"]
    idea = t["topic"] + ". " + t["brief"]
    out[topic_id] = {"story_type": story_type, "idea": idea,
                     "prompt": formats.build_planner_prompt(story_type, idea, payload["language"], payload["target_duration_s"], direction, sources)}
print(json.dumps(out))  # ASCII (échappements \uXXXX) : indépendant de l'encodage de la console
"""


def render_story_visual(engine_checkout: Path) -> dict:
    corpus = load_corpus()
    topics = {}
    for tid in STORY_TYPE_BY_TOPIC:
        gi = corpus["topics"][tid]["generator_input"]
        topics[tid] = {"topic": gi["topic"], "brief": gi["brief"], "sources": [corpus["sources"][s] for s in gi["source_ids"]]}
    payload = {"story_types": STORY_TYPE_BY_TOPIC, "topics": topics, "language": VISUAL_RENDER["language"],
               "target_duration_s": VISUAL_RENDER["target_duration_s"]}
    done = subprocess.run([sys.executable, "-I", "-c", _VISUAL_SNIPPET, str(engine_checkout), json.dumps(payload, ensure_ascii=False)],
                          capture_output=True, text=True, timeout=120, encoding="utf-8")
    if done.returncode != 0:
        raise RuntimeError(f"story visual render failed: {done.stderr[-400:]}")
    return json.loads(done.stdout)


def verify(web_checkout: Path | None, engine_checkout: Path | None, manifest: dict | None = None) -> list[str]:
    """Liste des écarts ; vide = la baseline A est reproduite à l'identique depuis ces sources."""
    manifest = manifest or json.loads((FIXTURES / "baseline_manifest.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    std = manifest["standard"]
    script = FIXTURES / RENDER_SCRIPT
    if file_sha256(script) != manifest["tooling"]["render_script_sha256"]:
        problems.append("render_standard_A.mjs changed since the manifest was written")
    if web_checkout is not None:
        problems += check_commit(web_checkout, std["source_commit"], "growthos-web")
        problems += check_sources(web_checkout, std["source_files_sha256"], "growthos-web")
        with tempfile.TemporaryDirectory() as tmp:
            rendered = render_standard(web_checkout, Path(tmp) / "A.txt")
        if sha256_text(rendered) != std["rendered_sha256"]:
            problems.append("Standard A: the rebuilt prompt hash differs from the manifest")
        if shingle_hashes(rendered) != json.loads((FIXTURES / SHINGLES_FILE).read_text(encoding="utf-8"))["hashes"]:
            problems.append("Standard A: the stored non-reintroduction fingerprints do not match the rebuilt prompt")
    if engine_checkout is not None:
        sv = manifest["story_visual"]
        problems += check_commit(engine_checkout, sv["source_commit"], "AiAddicts (#103)")
        problems += check_sources(engine_checkout, {VISUAL_FILE: sv["formats_py_sha256"]}, "AiAddicts (#103)")
        rebuilt = render_story_visual(engine_checkout)
        frozen = json.loads((FIXTURES / sv["rendered_file"]).read_text(encoding="utf-8"))["prompts"]
        if rebuilt != frozen:
            problems.append("Story Visual A: the rebuilt prompts differ from the frozen fixture")
    return problems


def write_manifest_and_fixtures(web_checkout: Path, engine_checkout: Path) -> None:  # pragma: no cover - maintenance (re-gel d'une baseline)
    """Re-gèle la baseline depuis ces checkouts. À n'utiliser que pour créer une NOUVELLE version de baseline (nouvelle campagne)."""
    manifest = json.loads((FIXTURES / "baseline_manifest.json").read_text(encoding="utf-8"))
    std, sv = manifest["standard"], manifest["story_visual"]
    with tempfile.TemporaryDirectory() as tmp:
        text = render_standard(web_checkout, Path(tmp) / "A.txt")
    # Le texte du prompt n'est JAMAIS écrit dans ce dépôt (public) : seulement son empreinte et des empreintes de fenêtres.
    std["rendered_sha256"] = sha256_text(text)
    (FIXTURES / SHINGLES_FILE).write_text(json.dumps({"window": SHINGLE_WINDOW, "stride": SHINGLE_STRIDE, "normalization": "whitespace collapsed, casefold",
                                                      "whole_sha256": std["rendered_sha256"], "hashes": shingle_hashes(text)}, indent=1) + "\n",
                                          encoding="utf-8", newline="\n")
    std["source_commit"] = (_git(web_checkout, "rev-parse", "HEAD") or std["source_commit"])[:8]
    std["source_files_sha256"] = {rel: file_sha256(web_checkout / rel) for rel in WEB_FILES}
    prompts = render_story_visual(engine_checkout)
    commit = _git(engine_checkout, "rev-parse", "HEAD") or sv["source_commit"]
    raw = json.dumps({"commit": commit, "builder": sv["builder"], "prompts": prompts}, ensure_ascii=False, indent=1)
    (FIXTURES / sv["rendered_file"]).write_text(raw, encoding="utf-8", newline="\n")
    sv.update(source_commit=commit, formats_py_sha256=file_sha256(engine_checkout / VISUAL_FILE), rendered_sha256=sha256_text(raw))
    manifest["tooling"]["render_script_sha256"] = file_sha256(FIXTURES / RENDER_SCRIPT)
    (FIXTURES / "baseline_manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--web-checkout", type=Path, help="growthos-web au commit figé du manifeste")
    parser.add_argument("--engine-checkout", type=Path, help="AiAddicts au commit figé du manifeste (PR #103)")
    parser.add_argument("--write", action="store_true", help="RE-GEL : réécrit fixtures et manifeste (nouvelle version de baseline)")
    args = parser.parse_args(argv)
    if not args.web_checkout and not args.engine_checkout:
        parser.error("give at least one checkout to verify")
    if args.write:
        if not (args.web_checkout and args.engine_checkout):
            parser.error("--write needs both checkouts")
        write_manifest_and_fixtures(args.web_checkout, args.engine_checkout)
        print("baseline re-frozen: review the diff and version the campaign")
        return 0
    problems = verify(args.web_checkout, args.engine_checkout)
    for p in problems:
        print("MISMATCH:", p)
    print("OK: baseline A reproduced byte for byte" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
