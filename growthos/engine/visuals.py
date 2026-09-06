"""Un visuel par bloc de script pour que la vidéo ait un vrai fond derrière
les sous-titres au lieu d'une couleur unie. Deux modes selon `visual_style` :

- Style « stock footage » -> un **clip vidéo Pexels** par bloc (gratuit),
  photo Pexels en repli. Pour les sujets concrets (sport, cuisine, voyage,
  actu) qui rendent mieux en footage réel qu'en illustration.
- Sinon -> une **image IA** (OpenAI `gpt-image-1-mini`) par groupe de
  `_BLOCKS_PER_IMAGE` blocs (défaut 1 = une par bloc), Pexels photo en repli
  bloc par bloc. Jamais bloquant : un groupe raté n'empêche pas les autres.

Cohérence des personnages
-------------------------
Chaque appel image est indépendant : le modèle n'a aucune mémoire d'une
scène à l'autre. Un prénom seul ("Léo") pousse le modèle vers un humain par
défaut, même si la première image montrait un ourson. Deux garde-fous :

1. La *fiche personnage* du script (`script["characters"]`, description
   physique fixe + contrainte négative) et le *style graphique* fixe
   (`script["visual_style"]`) sont concaténés EN TÊTE de CHAQUE prompt de
   scène, avant l'action — voir `build_character_prefix` / `_scene_prompt`.
2. L'image de la première scène sert d'*ancre visuelle* : les scènes
   suivantes sont générées via `/v1/images/edits` à partir d'elle
   (`reference_image_path`), pas régénérées de zéro.

Optionnel : sans aucune clé (Pexels et/ou OpenAI), `fetch_block_images()`
retourne des None partout — `engine/video.render_final()` retombe sur le
fond couleur unie d'origine, rien ne casse pour les configs sans clé.
"""
import os
import re
import time
from pathlib import Path

import requests

from . import openai_images

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

# Un visuel IA par groupe de `_BLOCKS_PER_IMAGE` blocs. Défaut 1 = une image
# par bloc (meilleur rythme, mais coût OpenAI ~x2-3 sur une vidéo de 6-8
# blocs) ; `VISUALS_BLOCKS_PER_IMAGE=3` retrouve l'ancien regroupement moins
# cher. La 1re image sert d'ancre, les suivantes en dérivent via /edits, donc
# passer à 1 ne casse pas la cohérence des personnages.
try:
    _BLOCKS_PER_IMAGE = max(1, int(os.environ.get("VISUALS_BLOCKS_PER_IMAGE", "1")))
except ValueError:
    _BLOCKS_PER_IMAGE = 1

# `visual_style` (id ou phrase) qui déclenche les vidéos de stock Pexels au
# lieu des images IA — pour les sujets concrets (sport, cuisine, voyage,
# actu) qui rendent mieux en footage réel qu'en illustration.
_STOCK_FOOTAGE_IDS = {"stock_footage", "stock_video", "stock"}

# `visual_style` côté script peut être un id (pack choisi dans l'UI Faceloop,
# ou raccourci dans un script CLI) ou une phrase libre. Les ids connus sont
# traduits en consigne de style ; toute autre valeur non vide est utilisée
# telle quelle. Doit rester aligné avec VISUAL_STYLES de growthos-web
# (content-config.tsx) — Faceloop écrit de toute façon la phrase résolue dans
# `visual_style_prompt`, ceci n'est que le repli / le chemin CLI.
_VISUAL_STYLE_PROMPTS = {
    "flat_color": "",  # "fond uni + texte" : pas de visuel IA, géré par video.py
    "stock_footage": "photographie réaliste style contenu réseaux sociaux, lumière naturelle",
    "minimal_slides": "illustration minimaliste, aplats de couleur, formes géométriques simples",
    "pixar_3d": (
        "rendu 3D façon film d'animation Pixar, personnages expressifs aux formes "
        "arrondies, éclairage doux, textures léchées, couleurs chaudes"
    ),
    "anime": (
        "style anime japonais, cel-shading, traits nets, grands yeux expressifs, "
        "arrière-plans peints, couleurs saturées"
    ),
    "comic_book": (
        "style bande dessinée, encrage noir marqué, aplats de couleur, trames, "
        "ombres franches"
    ),
    "storybook": (
        "illustration album jeunesse, aquarelle et crayon, couleurs douces et pastel, "
        "formes arrondies, contours doux"
    ),
    "gta_loading": (
        "illustration façon écran de chargement de jeu vidéo type GTA, semi-réaliste "
        "stylisé, contours nets, ombrage cell, ambiance cinématique contrastée"
    ),
    "cinematic_real": (
        "photo cinématique réaliste, objectif 35mm, faible profondeur de champ, "
        "étalonnage type film, lumière naturelle"
    ),
    # rétro-compat : ancien id
    "anime_3d": (
        "rendu 3D façon film d'animation, couleurs vives, personnages aux formes "
        "arrondies, rendu doux et léché"
    ),
}

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

_RATIO_PHRASE = {
    "9:16": "cadrage vertical plein cadre (format 9:16, TikTok/Reels/Shorts)",
    "1:1": "cadrage carré plein cadre (format 1:1)",
    "16:9": "cadrage horizontal plein cadre (format 16:9)",
}


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


def _style_consigne(visual_style: str | None) -> str:
    """Traduit `script["visual_style"]` en consigne de style pour le prompt.
    Id connu -> phrase dédiée ; phrase libre -> telle quelle ; vide -> ''."""
    if not visual_style:
        return ""
    key = visual_style.strip()
    if key in _VISUAL_STYLE_PROMPTS:
        return _VISUAL_STYLE_PROMPTS[key]
    return key


def build_character_prefix(characters: list[dict] | None, visual_style: str | None) -> str:
    """Bloc de texte figé, identique pour toutes les scènes d'une vidéo :
    description physique complète de chaque personnage + contrainte négative
    + style graphique. Concaténé en tête de chaque prompt de scène.

    `characters` : liste de dicts `{name, description, negative?}` venant de
    `script["characters"]`. Entrées incomplètes ignorées. Retourne '' si
    rien d'exploitable (le prompt retombe alors sur son style générique)."""
    lines: list[str] = []
    for character in characters or []:
        if not isinstance(character, dict):
            continue
        name = str(character.get("name", "")).strip()
        description = str(character.get("description", "")).strip()
        if not name or not description:
            continue
        sentence = f"{name} est {description}."
        negative = str(character.get("negative", "")).strip()
        if negative:
            sentence += f" Ne jamais le représenter autrement : {negative}."
        lines.append(sentence)

    style = _style_consigne(visual_style)
    if style:
        lines.append(f"Style graphique identique pour toute la vidéo : {style}.")

    return " ".join(lines)


def _scene_prompt(
    texts: list[str],
    niche: str | None,
    character_prefix: str = "",
    aspect_ratio: str = "9:16",
) -> str:
    # "Sans aucun texte" explicite : sinon le modèle a tendance à incruster le
    # texte comme légende dans l'image (déjà géré par les sous-titres ffmpeg —
    # un doublon qui se chevauche, en plus de fautes de frappe vues en test).
    niche_part = f" Contexte : niche {niche.replace('-', ' ')}." if niche else ""
    combined = " ".join(t.strip() for t in texts)
    ratio_part = _RATIO_PHRASE.get(aspect_ratio, _RATIO_PHRASE["9:16"])
    prefix = character_prefix.strip()

    if prefix:
        header = prefix + "\n"
    else:
        # Pas de fiche personnage : on garde l'ancien comportement générique.
        header = "Photo réaliste, style contenu réseaux sociaux. "

    return (
        f"{header}"
        f"{ratio_part}. "
        f"SANS AUCUN TEXTE, mot, chiffre, légende, sous-titre, logo ni filigrane dans l'image."
        f"{niche_part}\n"
        f"Scène : {combined}"
    )


def prefers_stock_footage(visual_style_id: str, visual_style_consigne: str) -> bool:
    """True si le style demandé veut des vidéos de stock (Pexels) plutôt que
    des images IA."""
    vid = (visual_style_id or "").strip().lower()
    if vid in _STOCK_FOOTAGE_IDS:
        return True
    haystack = f"{vid} {(visual_style_consigne or '').lower()}"
    return any(k in haystack for k in ("stock footage", "vidéo de stock", "footage réel", "images d'archives"))


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


def search_video_url(query: str, api_key: str, orientation: str = "portrait") -> str | None:
    """Cherche un clip vidéo Pexels pour `query` (durée 3-30s, mp4, résolution
    la plus proche du plein cadre vertical). Retourne l'URL du fichier .mp4 ou
    None — ne lève jamais."""
    try:
        resp = requests.get(
            PEXELS_VIDEO_SEARCH_URL,
            headers={"Authorization": api_key},
            params={"query": query, "per_page": 8, "orientation": orientation},
            timeout=20,
        )
        resp.raise_for_status()
        for video in resp.json().get("videos") or []:
            if not (3 <= (video.get("duration") or 0) <= 30):
                continue
            mp4s = [f for f in (video.get("video_files") or []) if f.get("file_type") == "video/mp4" and f.get("link")]
            if not mp4s:
                continue
            mp4s.sort(key=lambda f: (f.get("height") or 0))
            # la plus petite qui atteint 1080 de haut (assez pour un 1080x1920
            # recadré), sinon la plus grande disponible.
            pick = next((f for f in mp4s if (f.get("height") or 0) >= 1080), mp4s[-1])
            return pick["link"]
        return None
    except (requests.RequestException, KeyError, ValueError, IndexError):
        return None


def _download(url: str, out_path: str, timeout: int = 30) -> str:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(resp.content)
    return out_path


def download_image(url: str, out_path: str) -> str:
    return _download(url, out_path, timeout=30)


def fetch_block_images(
    blocks: list[dict],
    niche: str | None,
    aspect_ratio: str,
    work_dir: Path,
    api_key: str | None,
    characters: list[dict] | None = None,
    visual_style: str | None = None,
    visual_style_prompt: str | None = None,
) -> list[str | None]:
    """Un visuel local par bloc (chemin `.jpg` image ou `.mp4` clip vidéo), ou
    None (pas de clé / pas de résultat / échec réseau) — jamais bloquant, un
    bloc sans visuel retombe sur le fond couleur unie côté video.py. Résultats
    mis en cache sur disque (relance = pas de re-fetch).

    - Style « stock footage » -> un clip vidéo Pexels par bloc (photo Pexels
      en repli, `api_key` = clé Pexels).
    - Sinon -> une image IA (OpenAI) par groupe de `_BLOCKS_PER_IMAGE` blocs
      (défaut 1), Pexels photo en repli bloc par bloc.

    `characters` / `visual_style(_prompt)` : fiche personnage figée + style
    graphique fixe, injectés en tête de chaque prompt d'image (cohérence)."""
    n = len(blocks)
    paths: list[str | None] = [None] * n
    images_dir = Path(work_dir) / "images"
    orientation = _ORIENTATION.get(aspect_ratio, "portrait")

    style_id = (visual_style or "").strip()
    style_consigne = (visual_style_prompt or "").strip() or _style_consigne(style_id)

    if prefers_stock_footage(style_id, style_consigne):
        if not api_key:
            print("       style « stock footage » demandé mais PEXELS_API_KEY absente — fond uni")
            return paths
        for i, block in enumerate(blocks):
            paths[i] = _fetch_stock_clip(block["text"], niche, orientation, images_dir, i, api_key)
        return paths

    character_prefix = build_character_prefix(characters, style_consigne)
    # Le visuel du 1er groupe sert d'ancre : les suivants en dérivent via
    # /edits, ce qui empêche le personnage de dériver d'un bloc à l'autre.
    reference_path: str | None = None

    for group in _group_blocks(n, _BLOCKS_PER_IMAGE):
        image_path = images_dir / f"scene-{group[0] + 1:02d}.jpg"
        if _exists_nonempty(image_path):
            for i in group:
                paths[i] = str(image_path)
            reference_path = reference_path or str(image_path)
            continue
        texts = [blocks[i]["text"] for i in group]
        prompt = _scene_prompt(texts, niche, character_prefix, aspect_ratio)
        scene_path = _try_scene_image(prompt, aspect_ratio, str(image_path), reference_path)
        if scene_path:
            for i in group:
                paths[i] = scene_path
            reference_path = reference_path or scene_path

    if not api_key:
        return paths

    for i, block in enumerate(blocks):
        if paths[i]:
            continue
        photo_path = images_dir / f"block-{i + 1:02d}.jpg"
        if _exists_nonempty(photo_path):
            paths[i] = str(photo_path)
            continue
        url = search_image_url(_search_query(block["text"], niche), api_key, orientation)
        if not url:
            continue
        try:
            download_image(url, str(photo_path))
            paths[i] = str(photo_path)
        except requests.RequestException:
            pass
    return paths


def _fetch_stock_clip(
    text: str, niche: str | None, orientation: str, images_dir: Path, i: int, api_key: str
) -> str | None:
    """Un clip vidéo Pexels pour ce bloc, ou une photo Pexels en repli, ou
    None. Mis en cache : `block-NN.mp4` puis `block-NN.jpg`."""
    video_path = images_dir / f"block-{i + 1:02d}.mp4"
    if _exists_nonempty(video_path):
        return str(video_path)
    photo_path = images_dir / f"block-{i + 1:02d}.jpg"
    if _exists_nonempty(photo_path):
        return str(photo_path)

    query = _search_query(text, niche)
    url = search_video_url(query, api_key, orientation)
    if url:
        try:
            t0 = time.monotonic()
            _download(url, str(video_path), timeout=90)
            print(f"       bloc {i + 1} : clip vidéo Pexels ({time.monotonic() - t0:.1f}s)")
            return str(video_path)
        except requests.RequestException:
            pass

    url = search_image_url(query, api_key, orientation)
    if url:
        try:
            download_image(url, str(photo_path))
            return str(photo_path)
        except requests.RequestException:
            pass
    return None


def _exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _try_scene_image(
    prompt: str,
    aspect_ratio: str,
    out_path: str,
    reference_image_path: str | None = None,
) -> str | None:
    """Tente une image IA (OpenAI) pour un groupe de blocs. None si pas de
    clé configurée ou échec — l'appelant retombe alors sur Pexels bloc par
    bloc pour ce groupe. Avec `reference_image_path`, l'image est dérivée de
    l'ancre visuelle (scène 1) plutôt que régénérée de zéro."""
    t0 = time.monotonic()
    path = openai_images.generate_image(prompt, out_path, aspect_ratio, reference_image_path)
    if path:
        kind = "dérivée de la scène 1" if reference_image_path else "générée"
        print(f"       scène : image IA {kind} ({time.monotonic() - t0:.1f}s)")
    return path
