"""Clés de cache déterministes pour les illustrations, isolées par locataire, et cache disque sûr.

La clé couvre tout ce qui change le pixel : prompt, modèle, qualité, taille, version de direction artistique et
empreinte des références. Le `tenant_id` fait partie de la clé ET du chemin : un locataire ne peut jamais lire l'actif
d'un autre (voir test d'isolation).
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .. import asset_store
from .art_directions import ART_DIRECTION_VERSION

_SAFE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def image_key(tenant_id: str, prompt: str, model: str, quality: str, size: str = "1024x1536",
              direction: str = "", reference_digest: str = "") -> str:
    return asset_store.make_key(kind="story_visual_image", tenant=tenant_id, prompt=prompt.strip(), model=model,
                                quality=quality, size=size, direction=direction,
                                direction_version=ART_DIRECTION_VERSION, reference=reference_digest)


class DiskImageCache:
    """Cache disque d'actifs (images par défaut ; `ext=".mp3"` pour la voix), un dossier par locataire."""

    def __init__(self, root: str | Path, tenant_id: str, ext: str = ".jpg"):
        if not re.fullmatch(r"\.[a-z0-9]{2,5}", ext):
            raise ValueError("invalid extension")
        self.ext = ext
        if not _SAFE.fullmatch(tenant_id or ""):
            raise ValueError("invalid tenant id")
        self.dir = Path(root).resolve() / tenant_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            raise ValueError("invalid cache key")
        return self.dir / f"{key}{self.ext}"

    def restore(self, key: str, dest: str | Path) -> bool:
        src = self._path(key)
        if src.is_symlink() or not src.is_file() or src.stat().st_size == 0:
            return False
        shutil.copyfile(src, dest)
        return True

    def save(self, key: str, src: str | Path) -> None:
        target = self._path(key)
        tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, target)  # jamais d'actif tronqué resservi
