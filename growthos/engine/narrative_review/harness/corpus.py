"""Corpus P0 (20 sujets) : chargement, validation et garde contre toute fuite vers le générateur ou le critique.

Le générateur ne reçoit que `defaults` + `generator_input` + les dossiers de `source_ids`. `evaluator_only` et les sujets
réservés (`holdout`) n'atteignent JAMAIS un payload de campagne : `generator_view` refuse les sujets hors campagne et
`assert_no_leak` inspecte chaque payload sortant.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SPLITS = {"pilot": 5, "development": 5, "holdout": 10}
PILOT_IDS = ("N01", "N04", "N05", "N13", "N18")
_INPUT_KEYS = {"topic", "brief", "truth_mode", "illustration_mode", "central_question", "learning_intention", "source_ids",
               "constraints", "prohibited_claims"}


class CorpusError(ValueError):
    pass


class HoldoutAccessError(PermissionError):
    """Un sujet hors des splits de la campagne (réserve, ou développement en pilote) a été demandé."""


class LeakError(RuntimeError):
    """Une valeur réservée à l'évaluateur (ou un sujet réservé) figure dans un payload destiné au modèle."""


def sha256_text(text: str) -> str:
    """Empreinte indépendante de la fin de ligne du dépôt (git peut convertir LF/CRLF selon la machine)."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def load_corpus(path: Path | None = None, sources_path: Path | None = None) -> dict:
    path, sources_path = path or FIXTURES / "corpus_20.json", sources_path or FIXTURES / "sources_bornees.json"
    corpus_text, sources_text = path.read_text(encoding="utf-8"), sources_path.read_text(encoding="utf-8")
    corpus, sources = json.loads(corpus_text), json.loads(sources_text)
    by_id = {s["source_id"]: s for s in sources["sources"]}
    validate_corpus(corpus, by_id)
    return {"defaults": corpus["defaults"], "topics": {t["id"]: t for t in corpus["topics"]}, "sources": by_id,
            "hashes": {"corpus_sha256": sha256_text(corpus_text), "sources_sha256": sha256_text(sources_text)},
            "versions": {"corpus": corpus["version"], "sources": sources.get("version")}}


def validate_corpus(corpus: dict, sources: dict) -> None:
    topics = corpus["topics"]
    ids = [t["id"] for t in topics]
    if len(ids) != 20 or len(set(ids)) != 20:
        raise CorpusError("the corpus needs exactly 20 unique topic ids")
    counts = {s: sum(t["split"] == s for t in topics) for s in SPLITS}
    if counts != SPLITS:
        raise CorpusError(f"splits must be {SPLITS}, got {counts}")
    if tuple(sorted(t["id"] for t in topics if t["split"] == "pilot")) != tuple(sorted(PILOT_IDS)):
        raise CorpusError("the pilot split must be exactly N01, N04, N05, N13, N18")
    for t in topics:
        gi = t["generator_input"]
        if set(gi) != _INPUT_KEYS:
            raise CorpusError(f"{t['id']}: generator_input keys differ from the frozen contract")
        if "evaluator_only" not in t:
            raise CorpusError(f"{t['id']}: evaluator_only is missing")
        unknown = [s for s in gi["source_ids"] if s not in sources]
        if unknown:
            raise CorpusError(f"{t['id']}: unresolved source ids {unknown}")


def generator_view(corpus: dict, topic_id: str, *, allowed_splits=("pilot",)) -> dict:
    """Ce que le rédacteur (et le critique, via le snapshot) a le droit de voir pour ce sujet. Rien d'autre."""
    topic = corpus["topics"][topic_id]
    if topic["split"] not in allowed_splits:
        raise HoldoutAccessError(f"{topic_id} is in split {topic['split']!r}, outside this campaign {allowed_splits}")
    packets = [corpus["sources"][s] for s in topic["generator_input"]["source_ids"]]
    return {"topic_id": topic_id, "defaults": corpus["defaults"], "generator_input": topic["generator_input"], "sources": packets}


def _leaf_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _leaf_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _leaf_strings(v)


def assert_no_leak(payload_text: str, corpus: dict, *, own_topic_id: str | None = None, min_len: int = 12) -> None:
    """Refuse un payload contenant une valeur `evaluator_only` (tous sujets) ou le sujet/brief d'un autre sujet réservé."""
    for tid, topic in corpus["topics"].items():
        for text in _leaf_strings(topic["evaluator_only"]):
            if len(text) >= min_len and text in payload_text:
                raise LeakError(f"evaluator_only value of {tid} found in an outgoing payload")
        if topic["split"] == "holdout" and tid != own_topic_id:
            for key in ("topic", "brief"):
                value = topic["generator_input"][key]
                if len(value) >= min_len and value in payload_text:
                    raise LeakError(f"holdout subject {tid} ({key}) found in an outgoing payload")
