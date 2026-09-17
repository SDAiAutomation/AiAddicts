"""Un visuel par bloc de script pour que la vidéo ait un vrai fond derrière
les sous-titres au lieu d'une couleur unie. Deux modes selon `visual_style` :

- Style « stock footage » -> un **clip vidéo Pexels** par bloc (gratuit),
  photo Pexels en repli. Pour les sujets concrets (sport, cuisine, voyage,
  actu) qui rendent mieux en footage réel qu'en illustration.
- Sinon -> une **image IA** par groupe de `_BLOCKS_PER_IMAGE` blocs (défaut 1
  = une par bloc), Pexels photo en repli bloc par bloc. Jamais bloquant : un
  groupe raté n'empêche pas les autres.

Pipeline image (voir les modules dédiés pour le détail) :
  `image_style_bible`      -> identité visuelle du script (1x, réutilisée partout)
  `image_character_bible`  -> fiche personnage conditionnelle (1x, réutilisée partout)
  `image_prompt_builder`   -> assemble le prompt final d'UNE scène
  `image_model_router`     -> modèle/qualité selon l'usage (preview/final/edit)
  `openai_images`          -> appel API (retry/backoff, generate/edit)
  `image_quality_control`  -> QC vision OPT-IN + boucle edit/régénération

Texte vs visuel
---------------
`block["text"]` est la voix off (ce qu'on ENTEND). `block["visual"]`, généré
par le web en même temps que le texte (voir ai-actions.ts, buildBasePrompt),
est ce qu'on VOIT à l'écran pour ce plan précis — un cadrage/objet/action
concret, jamais une paraphrase du texte. `_block_visual_text()` utilise
`visual` s'il existe, sinon replie sur `text` (anciens scripts, bloc édité à
la main). Sans ce champ distinct, l'image n'a que la voix off à illustrer et
retombe systématiquement sur "portrait du personnage qui parle" — le prompt
web impose explicitement une règle anti-statique (personnage de face sur
~30% des blocs max, le reste en gros plans d'objet/POV/plans larges).

Cohérence des personnages
-------------------------
Chaque scène est une génération texte indépendante (`/v1/images/generations`) :
le modèle n'a aucune mémoire d'une scène à l'autre. Un prénom seul ("Léo")
pousse le modèle vers un humain par défaut, même si la première image montrait
un ourson.

Garde-fou : la fiche personnage (`image_character_bible.build_character_prefix`)
et la Style Bible (`image_style_bible.resolve_style_bible`) sont résolues UNE
FOIS par script, puis concaténées en tête de CHAQUE prompt de scène — voir
`image_prompt_builder.build_scene_prompt`. La description de chaque
personnage est explicitement CONDITIONNELLE ("si {name} apparaît dans cette
scène...") pour ne pas pousser le modèle à l'insérer sur les plans d'objet/
POV/décor où il n'a rien à faire.

Testé et écarté : dériver les scènes 2+ de l'image de la scène 1 via
`/v1/images/edits` (au lieu de régénérer chaque scène par texte) garde certes
le personnage, mais l'endpoint reproduit alors quasiment la même pose et le
même cadrage d'une scène à l'autre — il privilégie très fortement la fidélité
à l'image reçue sur la nouveauté demandée par le prompt. Chaque scène doit
illustrer SA propre action ; la cohérence du personnage repose donc uniquement
sur le character_prefix (texte), pas sur un enchaînement d'images. `/edits`
reste utilisé, mais uniquement pour la correction CIBLÉE d'une image déjà
générée (voir `image_quality_control` + `openai_images.edit_image`).

Optionnel : sans aucune clé (Pexels et/ou OpenAI), `fetch_block_images()`
retourne des None partout — `engine/video.render_final()` retombe sur le
fond couleur unie d'origine, rien ne casse pour les configs sans clé.
"""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from . import image_character_bible, image_model_router, image_prompt_builder, image_quality_control, image_style_bible, openai_images

# Les appels OpenAI /images sont indépendants par scène (I/O réseau) : quelques-uns
# en parallèle réduisent le temps total de "somme des scènes" à ~"scène la plus
# longue" — même logique que _MAX_TTS_WORKERS dans engine/assembler.py.
_MAX_IMAGE_WORKERS = 4

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

# Un visuel IA par groupe de `_BLOCKS_PER_IMAGE` blocs. Défaut 1 = une image
# par bloc (meilleur rythme, mais coût OpenAI ~x2-3 sur une vidéo de 6-8
# blocs) ; `VISUALS_BLOCKS_PER_IMAGE=3` retrouve l'ancien regroupement moins
# cher.
try:
    _BLOCKS_PER_IMAGE = max(1, int(os.environ.get("VISUALS_BLOCKS_PER_IMAGE", "1")))
except ValueError:
    _BLOCKS_PER_IMAGE = 1

# `visual_style` (id ou phrase) qui déclenche les vidéos de stock Pexels au
# lieu des images IA — pour les sujets concrets (sport, cuisine, voyage,
# actu) qui rendent mieux en footage réel qu'en illustration.
_STOCK_FOOTAGE_IDS = {"stock_footage", "stock_video", "stock"}

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


def _block_visual_text(block: dict) -> str:
    """Ce qu'on VOIT à l'écran pour ce bloc — cadrage/objet/action, généré par
    le web en même temps que le texte (voir ai-actions.ts, buildBasePrompt) —
    si présent. Sinon replie sur le texte de la voix off (anciens scripts sans
    "visual", ou bloc ajouté/édité à la main sans le renseigner)."""
    visual = str(block.get("visual") or "").strip()
    return visual or block["text"]


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
        best_low = None  # repli si aucun clip n'a de fichier >= 1080 de haut
        for video in resp.json().get("videos") or []:
            if not (3 <= (video.get("duration") or 0) <= 30):
                continue
            mp4s = [f for f in (video.get("video_files") or []) if f.get("file_type") == "video/mp4" and f.get("link")]
            if not mp4s:
                continue
            # En portrait, c'est la largeur qui limite le rendu 1080 de large :
            # on veut un fichier >= 1080px de large. Priorité au 1er clip qui
            # en a un (sa plus petite version >= 1080), repli sur le plus grand.
            mp4s.sort(key=lambda f: (f.get("width") or 0))
            hi = next((f for f in mp4s if (f.get("width") or 0) >= 1080), None)
            if hi:
                return hi["link"]
            if best_low is None:
                best_low = mp4s[-1]["link"]
        return best_low
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
) -> tuple[list[str | None], list[dict]]:
    """Un visuel local par bloc (chemin `.jpg` image ou `.mp4` clip vidéo), ou
    None (pas de clé / pas de résultat / échec réseau) — jamais bloquant, un
    bloc sans visuel retombe sur le fond couleur unie côté video.py. Résultats
    mis en cache sur disque (relance = pas de re-fetch).

    - Style « stock footage » -> un clip vidéo Pexels par bloc (photo Pexels
      en repli, `api_key` = clé Pexels).
    - Sinon -> une image IA par groupe de `_BLOCKS_PER_IMAGE` blocs (défaut
      1), Pexels photo en repli bloc par bloc. Passe par
      `image_quality_control` si `IMAGE_QC_ENABLED` (sinon comportement
      identique à avant : une génération, jamais de QC/boucle).

    `characters` / `visual_style(_prompt)` : fiche personnage figée + style
    graphique fixe, injectés en tête de chaque prompt d'image (cohérence).

    Retourne `(image_paths, scene_reports)` — `scene_reports` : une entrée
    par scène RÉELLEMENT (re)générée cette fois (pas les scènes servies par
    le cache disque), voir `_generate_scene_with_qc`. Consommé par
    `assembler.py` pour construire `image_generation_report`."""
    n = len(blocks)
    paths: list[str | None] = [None] * n
    images_dir = Path(work_dir) / "images"
    orientation = _ORIENTATION.get(aspect_ratio, "portrait")

    style_bible = image_style_bible.resolve_style_bible(visual_style, visual_style_prompt)
    style_id = style_bible["visual_style_id"]
    style_consigne = style_bible["consigne"]

    if prefers_stock_footage(style_id, style_consigne):
        if not api_key:
            print("       style « stock footage » demandé mais PEXELS_API_KEY absente — fond uni")
            return paths, []
        for i, block in enumerate(blocks):
            paths[i] = _fetch_stock_clip(_block_visual_text(block), niche, orientation, images_dir, i, api_key)
        return paths, []

    character_prefix = image_character_bible.build_character_prefix(characters, style_consigne)

    # 1re passe (rapide, pas de réseau) : sert le cache disque et repère ce
    # qui reste vraiment à générer.
    pending: list[tuple[list[int], Path, str]] = []
    for group in _group_blocks(n, _BLOCKS_PER_IMAGE):
        image_path = images_dir / f"scene-{group[0] + 1:02d}.jpg"
        if _exists_nonempty(image_path):
            for i in group:
                paths[i] = str(image_path)
            continue
        texts = [_block_visual_text(blocks[i]) for i in group]
        prompt = image_prompt_builder.build_scene_prompt(texts, niche, character_prefix, aspect_ratio, style_bible)
        pending.append((group, image_path, prompt))

    scene_reports: list[dict] = []
    if pending:
        def _generate(item: tuple[list[int], Path, str]) -> tuple[list[int], str | None, dict]:
            group, image_path, prompt = item
            path, report = _generate_scene_with_qc(prompt, aspect_ratio, str(image_path), character_prefix)
            return group, path, report

        with ThreadPoolExecutor(max_workers=min(_MAX_IMAGE_WORKERS, len(pending))) as pool:
            for group, scene_path, report in pool.map(_generate, pending):
                if scene_path:
                    for i in group:
                        paths[i] = scene_path
                scene_reports.append(report)

    if not api_key:
        return _fill_missing_visuals(paths), scene_reports

    for i, block in enumerate(blocks):
        if paths[i]:
            continue
        photo_path = images_dir / f"block-{i + 1:02d}.jpg"
        if _exists_nonempty(photo_path):
            paths[i] = str(photo_path)
            continue
        url = search_image_url(_search_query(_block_visual_text(block), niche), api_key, orientation)
        if not url:
            continue
        try:
            download_image(url, str(photo_path))
            paths[i] = str(photo_path)
        except requests.RequestException:
            pass
    return _fill_missing_visuals(paths), scene_reports


def _fill_missing_visuals(paths: list[str | None]) -> list[str | None]:
    """Réutilise le plan disponible le plus proche si tous les fournisseurs ont échoué."""
    available = [i for i, path in enumerate(paths) if path]
    if not available:
        return paths
    for i, path in enumerate(paths):
        if path is None:
            nearest = min(available, key=lambda candidate: (abs(candidate - i), candidate > i))
            paths[i] = paths[nearest]
            print(f"       bloc {i + 1} : réutilisation du visuel du bloc {nearest + 1}")
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


def _generate_scene_with_qc(
    prompt: str,
    aspect_ratio: str,
    out_path: str,
    character_prefix: str,
) -> tuple[str | None, dict]:
    """Génère une scène en mode "final", puis — si `IMAGE_QC_ENABLED` —
    applique la boucle QC vision -> edit ciblé / régénération, plafonnée à
    `image_quality_control.max_attempts()`. QC désactivée (par défaut) :
    comportement strictement identique à l'ancien `_try_scene_image` (une
    génération, pas de QC).

    Retourne `(chemin_ou_None, rapport)` — `rapport` alimente
    `image_generation_report` côté `assembler.py`, y compris quand la
    génération échoue (coût 0, `qualityScore` None)."""
    selection = image_model_router.select_model("final")
    t0 = time.monotonic()
    path = openai_images.generate_image(prompt, out_path, aspect_ratio, None, selection.model, selection.quality)
    report = {
        "model": selection.model,
        "quality": selection.quality,
        "purpose": "final",
        "attempts": 1,
        "estimatedCost": image_model_router.estimate_cost(selection.model, selection.quality) if path else 0.0,
        "qualityScore": None,
        "approved": None,
        "manualReview": False,
    }
    if not path:
        print(f"       scène : image IA échouée ({time.monotonic() - t0:.1f}s)")
        return None, report
    print(f"       scène : image IA générée ({time.monotonic() - t0:.1f}s)")

    if not image_quality_control.qc_enabled():
        return path, report

    attempts = 1
    max_attempts = image_quality_control.max_attempts()
    qc = image_quality_control.evaluate_image(path, prompt, character_prefix)
    if qc is None:
        return path, report  # QC indisponible (modèle non configuré, échec réseau...)

    report["qualityScore"] = qc.overall_score
    report["approved"] = qc.approved

    while not qc.approved and attempts < max_attempts:
        attempts += 1
        report["attempts"] = attempts
        if qc.recommended_action == "EDIT" and qc.edit_instructions:
            edit_selection = image_model_router.select_model("edit")
            fixed = openai_images.edit_image(
                " ".join(qc.edit_instructions), path, out_path, edit_selection.model, edit_selection.quality, aspect_ratio
            )
            report["estimatedCost"] += (
                image_model_router.estimate_cost(edit_selection.model, edit_selection.quality) if fixed else 0.0
            )
        else:
            regen_selection = image_model_router.select_model("final")
            fixed = openai_images.generate_image(
                prompt, out_path, aspect_ratio, None, regen_selection.model, regen_selection.quality
            )
            report["estimatedCost"] += (
                image_model_router.estimate_cost(regen_selection.model, regen_selection.quality) if fixed else 0.0
            )

        if not fixed:
            break  # échec de la correction -> on garde la dernière image valable
        path = fixed
        qc = image_quality_control.evaluate_image(path, prompt, character_prefix)
        if qc is None:
            break
        report["qualityScore"] = qc.overall_score
        report["approved"] = qc.approved

    if not report["approved"]:
        report["manualReview"] = True
        print(f"       scène : QC {report['qualityScore']}/100 après {attempts} tentative(s) — revue manuelle")

    return path, report
