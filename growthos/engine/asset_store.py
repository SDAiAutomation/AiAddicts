"""Cache d'actifs payants réutilisables entre deux générations (lot L1).

Le worker tourne sur un runner éphémère : sans ce cache, voix et images déjà
payées étaient perdues entre deux passages et corriger un mot coûtait une
régénération complète. Chaque actif (voix d'un bloc + son timing, image d'une
scène) est rangé dans le bucket privé `content-assets` sous une clé qui est
l'empreinte de TOUTES ses entrées (texte, voix, prompt final, modèle...). Une
correction ne régénère donc que les actifs dont l'empreinte a changé.

Garanties :
- Jamais bloquant : toute erreur (table absente, réseau, bucket) dégrade en
  « pas de cache » et la génération se déroule comme avant.
- Inactif tant que `configure()` n'a pas été appelé (CLI, tests) : aucune
  fonction ne touche le réseau dans ce cas.
- Une clé change dès qu'une entrée change : on ne réutilise jamais un actif
  dont les conditions de production diffèrent.
"""
import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

BUCKET = "content-assets"
TABLE = "content_assets"

_lock = threading.Lock()
_ctx: dict | None = None


def configure(client, content_item_id: str) -> None:
    """Active le cache pour un content_item et précharge son manifeste (une
    seule requête). Un échec laisse le cache inactif."""
    global _ctx
    with _lock:
        _ctx = None
    try:
        rows = (
            client.table(TABLE)
            .select("id, kind, input_hash, storage_path")
            .eq("content_item_id", content_item_id)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        print(f"       (cache d'actifs indisponible : {exc})")
        return
    with _lock:
        _ctx = {
            "client": client,
            "item_id": content_item_id,
            "rows": {(r["kind"], r["input_hash"]): r for r in rows},
            "used": set(),
            "stats": {"voice": {"reused": 0, "generated": 0}, "image": {"reused": 0, "generated": 0}},
        }


def reset() -> None:
    global _ctx
    with _lock:
        _ctx = None


def enabled() -> bool:
    return _ctx is not None


def make_key(**parts) -> str:
    """Empreinte stable des entrées d'un actif."""
    canonical = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _restore_file(kind: str, key: str, dest: Path) -> bool:
    ctx = _ctx
    if ctx is None:
        return False
    row = ctx["rows"].get((kind, key))
    if not row:
        return False
    try:
        data = ctx["client"].storage.from_(BUCKET).download(row["storage_path"])
        if not data:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except Exception as exc:
        print(f"       (actif {kind} non restauré : {exc})")
        return False
    with _lock:
        ctx["used"].add(row["id"])
    return True


def _save_file(kind: str, key: str, src: Path, estimated_cost: float | None, provider: str | None) -> bool:
    ctx = _ctx
    if ctx is None or not src.exists() or src.stat().st_size == 0:
        return False
    client, item_id = ctx["client"], ctx["item_id"]
    path = f"{item_id}/{kind}/{key}{src.suffix}"
    try:
        client.storage.from_(BUCKET).upload(
            path, str(src.resolve()), file_options={"upsert": "true", "content-type": _content_type(src)}
        )
        row = (
            client.table(TABLE)
            .upsert(
                {
                    "content_item_id": item_id,
                    "kind": kind,
                    "input_hash": key,
                    "storage_path": path,
                    "bytes": src.stat().st_size,
                    "estimated_cost": estimated_cost,
                    "provider": provider,
                    "last_used_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="content_item_id,kind,input_hash",
            )
            .execute()
            .data
        )
    except Exception as exc:
        print(f"       (actif {kind} non conservé : {exc})")
        return False
    with _lock:
        if row:
            ctx["rows"][(kind, key)] = row[0]
            ctx["used"].add(row[0]["id"])
    return True


def _content_type(path: Path) -> str:
    return {".mp3": "audio/mpeg", ".json": "application/json", ".jpg": "image/jpeg", ".png": "image/png"}.get(
        path.suffix.lower(), "application/octet-stream"
    )


def _count(category: str, field: str) -> None:
    ctx = _ctx
    if ctx is None:
        return
    with _lock:
        ctx["stats"][category][field] += 1


def restore_voice(key: str, audio_path: Path, words_path: Path) -> bool:
    """Restaure la voix d'un bloc ET son timing mot à mot, ou rien."""
    if _ctx is None:
        return False
    if _restore_file("voice", key, audio_path) and _restore_file("voice_words", key, words_path):
        _count("voice", "reused")
        return True
    for leftover in (audio_path, words_path):
        leftover.unlink(missing_ok=True)
    return False


def save_voice(key: str, audio_path: Path, words_path: Path, estimated_cost: float | None = None) -> None:
    if _ctx is None:
        return
    _count("voice", "generated")
    if _save_file("voice", key, audio_path, estimated_cost, "elevenlabs"):
        _save_file("voice_words", key, words_path, None, None)


def restore_image(key: str, dest: Path) -> bool:
    if _restore_file("image", key, dest):
        _count("image", "reused")
        return True
    return False


def save_image(key: str, src: Path, estimated_cost: float | None = None, provider: str | None = None) -> None:
    if _ctx is None:
        return
    _count("image", "generated")
    _save_file("image", key, src, estimated_cost, provider)


def stats() -> dict | None:
    """Compteurs réutilisé/généré par catégorie, ou None si le cache est inactif."""
    ctx = _ctx
    if ctx is None:
        return None
    with _lock:
        return {name: dict(values) for name, values in ctx["stats"].items()}


def finish() -> None:
    """Marque les actifs utilisés par ce run (sert à purger les plus anciens)."""
    ctx = _ctx
    if ctx is None:
        return
    with _lock:
        ids = list(ctx["used"])
    if not ids:
        return
    try:
        ctx["client"].table(TABLE).update(
            {"last_used_at": datetime.now(timezone.utc).isoformat()}
        ).in_("id", ids).execute()
    except Exception as exc:
        print(f"       (last_used_at non mis à jour : {exc})")
