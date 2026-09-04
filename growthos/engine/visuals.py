"""Fetch a background image per script block from Pexels (stock photos,
free API) so the rendered video has real visuals instead of a flat color
card behind the captions.

Optionnel : sans PEXELS_API_KEY, `fetch_block_images()` retourne des None
partout — `engine/video.render_final()` retombe sur le fond couleur unie
d'origine, rien ne casse pour les configs sans clé.
"""
import re
from pathlib import Path

import requests

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

# Extraction de mots-clés volontairement simple (pas de dépendance NLP, le
# pipeline reste léger) : mots de 4+ lettres hors stop-words français
# courants, dans l'ordre d'apparition.
_STOPWORDS_FR = {
    "alors", "aussi", "avec", "avez", "avoir", "aux", "bien", "car", "cela",
    "cette", "ceux", "chaque", "chez", "comme", "dans", "depuis", "deja",
    "donc", "elle", "elles", "encore", "entre", "etre", "faire", "juste",
    "leur", "leurs", "meme", "mais", "moins", "nous", "notre", "pour",
    "quand", "quoi", "sans", "selon", "sera", "seront", "sont", "sous",
    "tous", "toute", "toutes", "tout", "tres", "un", "une", "vers", "votre",
    "vous", "cette", "cet", "ces",
}

_WORD_RE = re.compile(r"[a-zàâäéèêëïîôöùûüçœ]+", re.IGNORECASE)

_ORIENTATION = {"16:9": "landscape", "1:1": "square"}


def _keywords(text: str, max_words: int = 3) -> list[str]:
    words: list[str] = []
    for w in _WORD_RE.findall(text.lower()):
        if len(w) >= 4 and w not in _STOPWORDS_FR and w not in words:
            words.append(w)
        if len(words) >= max_words:
            break
    return words


def _search_query(block_text: str, niche: str | None) -> str:
    keywords = _keywords(block_text)
    niche_word = niche.replace("-", " ") if niche else ""
    if keywords and niche_word:
        # les 2 mots-clés du bloc + le premier mot de la niche pour le
        # contexte visuel (ex. bloc "signaux d'un bon lead" + niche
        # "coach-business" -> "signaux lead coach")
        return " ".join(keywords[:2] + [niche_word.split()[0]])
    return " ".join(keywords) or niche_word or "business"


def search_image_url(query: str, api_key: str, orientation: str = "portrait") -> str | None:
    """Cherche une photo Pexels pour `query`. Retourne l'URL (taille
    "large") ou None si rien trouvé / erreur réseau — ne lève jamais,
    l'appelant doit pouvoir retomber sur le fond uni pour ce bloc."""
    try:
        resp = requests.get(
            PEXELS_SEARCH_URL,
            headers={"Authorization": api_key},
            params={"query": query, "per_page": 1, "orientation": orientation},
            timeout=20,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos") or []
        return photos[0]["src"]["large"] if photos else None
    except (requests.RequestException, KeyError, ValueError, IndexError):
        return None


def download_image(url: str, out_path: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(resp.content)
    return out_path


def fetch_block_images(
    blocks: list[dict],
    niche: str | None,
    aspect_ratio: str,
    work_dir: Path,
    api_key: str | None,
) -> list[str | None]:
    """Une image locale par bloc, ou None (pas de clé / pas de résultat /
    échec réseau pour ce bloc précis) — jamais bloquant, chaque bloc sans
    image retombe sur le fond couleur unie côté video.py. Résultats mis en
    cache sur disque comme le reste du pipeline (relance = pas de re-fetch)."""
    if not api_key:
        return [None] * len(blocks)

    orientation = _ORIENTATION.get(aspect_ratio, "portrait")
    paths: list[str | None] = []
    for i, block in enumerate(blocks, start=1):
        image_path = Path(work_dir) / "images" / f"block-{i:02d}.jpg"
        if image_path.exists() and image_path.stat().st_size > 0:
            paths.append(str(image_path))
            continue
        query = _search_query(block["text"], niche)
        url = search_image_url(query, api_key, orientation)
        if not url:
            paths.append(None)
            continue
        try:
            download_image(url, str(image_path))
            paths.append(str(image_path))
        except requests.RequestException:
            paths.append(None)
    return paths
