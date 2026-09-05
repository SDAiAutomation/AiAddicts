"""Fetch a background image per script block — IA (OpenAI `gpt-image-1-mini`,
style illustré cohérent) en priorité si configurée, Pexels (stock photos,
gratuit) sinon ou en repli, pour que la vidéo ait un vrai visuel au lieu
d'un fond couleur uni derrière les sous-titres.

Une image IA par bloc serait inutilement cher pour une vidéo de 60-75s (une
image tiendrait ~8-10s à l'écran, personne ne remarque un changement aussi
fréquent) : les blocs sont regroupés par paquets de `_BLOCKS_PER_IMAGE`
(une "scène"), chaque groupe ne coûtant qu'un seul appel OpenAI, réutilisé
sur tous ses blocs. Pexels comble ensuite les blocs restés sans image
(clé OpenAI absente, échec réseau/API pour ce groupe précis) — jamais
bloquant, jamais un groupe raté n'empêche les autres d'avoir leur visuel.

Optionnel : sans aucune clé (Pexels et/ou OpenAI), `fetch_block_images()`
retourne des None partout — `engine/video.render_final()` retombe sur le
fond couleur unie d'origine, rien ne casse pour les configs sans clé.
"""
import re
import time
from pathlib import Path

import requests

from . import openai_images

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

# ~20-25s d'écran par image générée (un bloc dure ~7-10s de voix off) : une
# vidéo de 60-75s n'a besoin que de 2-3 visuels distincts, pas d'un par bloc.
_BLOCKS_PER_IMAGE = 3

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
    "vous", "cette", "cet", "ces", "voici", "voila", "ainsi", "certain",
    "certains", "certaine", "certaines", "quelque", "quelques", "toujours",
    "jamais", "peut", "peuvent", "doit", "doivent", "veut", "veulent",
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


def _group_blocks(n_blocks: int, group_size: int) -> list[list[int]]:
    """Indices (0-based) des blocs regroupés par paquets de `group_size` —
    un groupe = une seule image IA générée, réutilisée sur tous ses blocs."""
    return [list(range(i, min(i + group_size, n_blocks))) for i in range(0, n_blocks, group_size)]


def _scene_prompt(texts: list[str], niche: str | None) -> str:
    # "Sans aucun texte" explicite : sinon le modèle a tendance à incruster le
    # texte comme légende dans l'image (déjà géré par les sous-titres ffmpeg —
    # un doublon qui se chevauche, en plus de fautes de frappe vues en test).
    niche_part = f", niche {niche.replace('-', ' ')}" if niche else ""
    combined = " ".join(t.strip() for t in texts)
    return (
        f"Photo réaliste, style contenu réseaux sociaux, SANS AUCUN TEXTE ni mot ni "
        f"légende dans l'image : scène illustrant « {combined} »{niche_part}"
    )


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
    échec réseau) — jamais bloquant, chaque bloc sans image retombe sur le
    fond couleur unie côté video.py. Résultats mis en cache sur disque comme
    le reste du pipeline (relance = pas de re-fetch).

    IA (OpenAI, un groupe de `_BLOCKS_PER_IMAGE` blocs = une image) en
    priorité, Pexels en repli bloc par bloc pour tout ce que l'IA n'a pas
    couvert (pas de clé OpenAI, ou échec pour ce groupe précis)."""
    n = len(blocks)
    paths: list[str | None] = [None] * n

    for group in _group_blocks(n, _BLOCKS_PER_IMAGE):
        image_path = Path(work_dir) / "images" / f"scene-{group[0] + 1:02d}.jpg"
        if _exists_nonempty(image_path):
            for i in group:
                paths[i] = str(image_path)
            continue
        texts = [blocks[i]["text"] for i in group]
        scene_path = _try_scene_image(texts, niche, aspect_ratio, str(image_path))
        if scene_path:
            for i in group:
                paths[i] = scene_path

    if not api_key:
        return paths

    orientation = _ORIENTATION.get(aspect_ratio, "portrait")
    for i, block in enumerate(blocks):
        if paths[i]:
            continue
        image_path = Path(work_dir) / "images" / f"block-{i + 1:02d}.jpg"
        if _exists_nonempty(image_path):
            paths[i] = str(image_path)
            continue
        query = _search_query(block["text"], niche)
        url = search_image_url(query, api_key, orientation)
        if not url:
            continue
        try:
            download_image(url, str(image_path))
            paths[i] = str(image_path)
        except requests.RequestException:
            pass
    return paths


def _exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _try_scene_image(texts: list[str], niche: str | None, aspect_ratio: str, out_path: str) -> str | None:
    """Tente une image IA (OpenAI) pour un groupe de blocs. None si pas de
    clé configurée ou échec — l'appelant retombe alors sur Pexels bloc par
    bloc pour ce groupe."""
    t0 = time.monotonic()
    path = openai_images.generate_image(_scene_prompt(texts, niche), out_path, aspect_ratio)
    if path:
        print(f"       scène : image IA générée ({time.monotonic() - t0:.1f}s)")
    return path
