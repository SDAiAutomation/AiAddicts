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
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from . import image_character_bible, image_model_router, image_prompt_builder, image_quality_control, image_style_bible, motion_graphics, openai_images, stock_planner, style_treatments, video

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

# `visual_style` qui déclenche le rendu Motion Graphics local (numéros
# animés, graphiques, checklists...) au lieu des images IA — voir
# engine/motion_graphics/. Aucun appel réseau, donc pas de repli "aucune clé".
_MOTION_GRAPHICS_IDS = {"motion_graphics", "motion_graphic", "infographic"}

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


_KINETIC_TYPOGRAPHY_IDS = {"flat_color"}


def prefers_kinetic_typography(visual_style_id: str, visual_style_consigne: str) -> bool:
    """True si le style demandé est « fond uni + texte » — Phase 2 : ce
    style bascule sur une typographie cinétique locale (voir
    engine/kinetic_typography.py) plutôt que sur une image IA générique,
    contrairement à avant où un OPENAI_API_KEY configuré déclenchait quand
    même une image photo-réaliste pour ce style (incohérent avec son
    intention). Aucun appel réseau, jamais bloquant."""
    vid = (visual_style_id or "").strip().lower()
    return vid in _KINETIC_TYPOGRAPHY_IDS


def fetch_kinetic_typography_clips(
    blocks: list[dict],
    durations: list[float],
    aspect_ratio: str,
    work_dir: Path,
    theme_overrides: dict | None = None,
) -> list[str | None]:
    """Un clip `.mp4` de typographie cinétique local par bloc — voir
    `engine.kinetic_typography.build_emphasis_scene` (Phase 2.6) pour l'ordre
    de priorité : `motion_graphic` explicite déjà présent sur le bloc,
    sinon un nombre/pourcentage/montant détecté dans `visual` OU `text`
    (narration inspectée même quand `visual` est renseigné — correctif du
    benchmark : un `visual` sans chiffre masquait un chiffre présent dans la
    narration), sinon une courte phrase dérivée déterministiquement (jamais
    inventée). `None` pour CE bloc précis seulement si rien d'exploitable
    n'existe : contrairement à `fetch_motion_graphics_clips`, l'absence
    n'est jamais comblée par `_fill_missing_visuals` — un `None` ici est un
    état final valide (repli sur le fond uni existant côté
    `engine/video.py`, pas un échec)."""
    from . import kinetic_typography

    images_dir = Path(work_dir) / "images"
    paths: list[str | None] = [None] * len(blocks)
    resolution = video.RESOLUTIONS.get(aspect_ratio, video.RESOLUTIONS["9:16"])
    for i, block in enumerate(blocks):
        if i > 0 and block.get("reuse_visual_from_previous"):
            paths[i] = paths[i - 1]
            continue
        scene = kinetic_typography.build_emphasis_scene(block)
        if not scene:
            continue  # rien d'exploitable -> fond uni (comportement d'avant cette phase)
        clip_path = images_dir / f"kinetic-{i + 1:02d}.mp4"
        if _exists_nonempty(clip_path):
            paths[i] = str(clip_path)
            continue
        try:
            motion_graphics.render_scene_clip(
                scene, durations[i] if i < len(durations) else 3.0, str(clip_path),
                resolution=resolution, theme_overrides=theme_overrides,
            )
            paths[i] = str(clip_path)
        except RuntimeError as exc:
            print(f"       bloc {i + 1} : typographie cinétique échouée ({exc}) — fond uni")
    return paths


def prefers_stock_footage(visual_style_id: str, visual_style_consigne: str) -> bool:
    """True si le style demandé veut des vidéos de stock (Pexels) plutôt que
    des images IA."""
    vid = (visual_style_id or "").strip().lower()
    if vid in _STOCK_FOOTAGE_IDS:
        return True
    haystack = f"{vid} {(visual_style_consigne or '').lower()}"
    return any(k in haystack for k in ("stock footage", "vidéo de stock", "footage réel", "images d'archives"))


def prefers_motion_graphics(visual_style_id: str, visual_style_consigne: str) -> bool:
    """True si le style demandé veut le rendu Motion Graphics local plutôt
    que des images IA ou du stock footage."""
    vid = (visual_style_id or "").strip().lower()
    if vid in _MOTION_GRAPHICS_IDS:
        return True
    haystack = f"{vid} {(visual_style_consigne or '').lower()}"
    return any(k in haystack for k in ("motion graphics", "motion graphic", "infographic", "infographie"))


def fetch_motion_graphics_clips(
    blocks: list[dict],
    durations: list[float],
    aspect_ratio: str,
    work_dir: Path,
    theme_overrides: dict | None = None,
    preflight_report: list | None = None,
) -> list[str | None]:
    """Un clip `.mp4` Motion Graphics local par bloc, rendu à la durée EXACTE
    de sa voix off (voir engine/motion_graphics/renderer.py) — jamais bloquant :
    un bloc dont le rendu échoue reste `None`, comblé ensuite par
    `_fill_missing_visuals` comme n'importe quel autre visuel manquant.
    Mis en cache sur disque comme les scènes IA (relance = pas de re-rendu)."""
    images_dir = Path(work_dir) / "images"
    paths: list[str | None] = [None] * len(blocks)
    resolution = video.RESOLUTIONS.get(aspect_ratio, video.RESOLUTIONS["9:16"])
    for i, block in enumerate(blocks):
        if i > 0 and block.get("reuse_visual_from_previous"):
            paths[i] = paths[i - 1]
            continue
        clip_path = images_dir / f"motion-{i + 1:02d}.mp4"
        if _exists_nonempty(clip_path):
            paths[i] = str(clip_path)
            continue
        # Fallback text = the scene's own content, else the narration — never the
        # `visual` shot description (see preflight.fallback_text).
        from .motion_graphics import preflight as _preflight

        narration = str(block.get("text") or "")
        fallback_text = _preflight.fallback_text(block.get("motion_graphic"), narration)
        scene = motion_graphics.resolve_scene(block.get("motion_graphic"), fallback_text)
        duration = durations[i] if i < len(durations) else 3.0
        scene = _sync_and_preflight(
            scene, fallback_text, duration, Path(work_dir) / "audio" / f"block-{i + 1:02d}.words.json",
            (int(v) for v in resolution.split("x")), theme_overrides, i, preflight_report,
        )
        try:
            motion_graphics.render_scene_clip(
                scene, duration, str(clip_path),
                resolution=resolution, theme_overrides=theme_overrides,
            )
            paths[i] = str(clip_path)
        except RuntimeError as exc:
            print(f"       bloc {i + 1} : motion graphics échoué ({exc})")
    return _fill_missing_visuals(paths)


def _sync_and_preflight(
    scene: dict, fallback_text: str, duration: float, words_path: Path, size, theme_overrides: dict | None,
    block_index: int, report: list | None,
) -> dict:
    """1) révélations calées sur la voix (engine/motion_graphics/sync.py),
    2) contrôle de mise en page de l'image finale (preflight.py) — une erreur
    grave (chevauchement, sortie du cadre, zone des sous-titres) remplace la
    scène par le repli `icon_text` plutôt que de publier une scène cassée.
    Jamais bloquant : toute exception ici laisse la scène telle quelle."""
    from .motion_graphics import preflight, sync
    from .motion_graphics.theme import resolve_theme

    entry: dict = {"blockIndex": block_index, "sceneType": scene.get("sceneType"), "synced": False, "action": "none"}
    try:
        w, h = tuple(size)
        if words_path.exists():
            scene = sync.attach_reveals(scene, json.loads(words_path.read_text(encoding="utf-8")), duration)
            entry["synced"] = "_reveals" in scene
        result = preflight.check_scene(scene, resolve_theme(theme_overrides), (w, h))
        entry.update({"minFontPx": result["minFontPx"], "errors": result["errors"], "warnings": result["warnings"]})
        if not result["ok"]:
            scene = motion_graphics.resolve_scene(None, preflight.fallback_text(scene, fallback_text))
            entry["action"] = "fallback_icon_text"
            print(f"       bloc {block_index + 1} : mise en page {entry['sceneType']} invalide "
                  f"({', '.join(e['kind'] for e in result['errors'])}) — repli icon_text")
    except Exception as exc:  # noqa: BLE001 — jamais bloquant
        entry["error"] = str(exc)[:160]
    if report is not None:
        report.append(entry)
    return scene


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


def search_video_candidates(query: str, api_key: str, orientation: str | None = "portrait") -> list[dict]:
    """Pool de candidats Pexels normalisés (métadonnées réelles uniquement —
    voir `stock_planner.normalize_pexels_video`) pour `query`. `orientation`
    None = toutes orientations. Ne lève jamais : liste vide en cas d'échec."""
    params = {"query": query, "per_page": stock_planner.CANDIDATES_PER_SEARCH}
    if orientation:
        params["orientation"] = orientation
    try:
        resp = requests.get(PEXELS_VIDEO_SEARCH_URL, headers={"Authorization": api_key}, params=params, timeout=20)
        resp.raise_for_status()
        raw = resp.json().get("videos") or []
    except (requests.RequestException, ValueError):
        return []
    out = []
    for rank, item in enumerate(raw):
        cand = stock_planner.normalize_pexels_video(item, rank)
        if cand:
            out.append(cand)
    return out


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
    durations: list[float] | None = None,
    language: str | None = None,
    stock_report: dict | None = None,
) -> tuple[list[str | None], list[dict], list[dict], list[dict]]:
    """Un visuel local par bloc (chemin `.jpg` image ou `.mp4` clip vidéo), ou
    None (pas de clé / pas de résultat / échec réseau) — jamais bloquant, un
    bloc sans visuel retombe sur le fond couleur unie côté video.py. Résultats
    mis en cache sur disque (relance = pas de re-fetch).

    - Style « stock footage » -> un clip vidéo Pexels par bloc, choisi par
      le planificateur sémantique (engine/stock_planner.py, Phase 4 ; photo
      Pexels en dernier repli, `api_key` = clé Pexels). `durations`/`language`
      affinent le classement/le plan ; `stock_report` (dict, optionnel) est
      rempli avec le plan, les requêtes tentées et le choix par bloc.
    - Sinon -> une image IA par groupe de `_BLOCKS_PER_IMAGE` blocs (défaut
      1). Passe par `image_quality_control` si `IMAGE_QC_ENABLED` (sinon
      comportement identique à avant : une génération, jamais de QC/boucle).
      Repli sur Pexels UNIQUEMENT si OpenAI n'est pas configuré DU TOUT pour
      cette vidéo (Pexels est alors la stratégie principale, pas un repli
      d'identité) ; si OpenAI est configuré et qu'une scène précise échoue,
      le repli est la réutilisation d'une scène déjà générée dans la MÊME
      vidéo (jamais Pexels) — voir `_build_fallback_events` (Phase 2.6,
      correctif du benchmark visuel : un repli Pexels sur un style à
      identité IA cassait visiblement le style et le personnage).

    `characters` / `visual_style(_prompt)` : fiche personnage figée + style
    graphique fixe, injectés en tête de chaque prompt d'image (cohérence).

    Retourne `(image_paths, scene_reports, fallback_events, style_treatments)` :
    - `scene_reports` : une entrée par scène RÉELLEMENT (re)générée cette
      fois (pas les scènes servies par le cache disque), voir
      `_generate_scene_with_qc`. Consommé par `assembler.py` pour construire
      `image_generation_report`.
    - `fallback_events` : une entrée par bloc dont le visuel a dû être
      comblé par réutilisation (block index, style demandé, stratégie
      d'asset, type d'échec, source de repli, intégrité de style préservée
      ou non) — voir `_build_fallback_events`. Vide si aucun repli n'a été
      nécessaire.
    - `style_treatments` (Phase 3) : une entrée par bloc traité par
      `engine.style_treatments` (`comic_book`/`gta_loading` uniquement) —
      voir `_apply_style_treatments`. `image_paths` pointe alors vers le
      fichier `.treated.jpg`, jamais vers l'original (conservé sur disque)."""
    n = len(blocks)
    paths: list[str | None] = [None] * n
    images_dir = Path(work_dir) / "images"
    orientation = _ORIENTATION.get(aspect_ratio, "portrait")

    style_bible = image_style_bible.resolve_style_bible(visual_style, visual_style_prompt)
    style_id = style_bible["visual_style_id"]
    style_consigne = style_bible["consigne"]

    def _treat(filled: list[str | None]) -> tuple[list[str | None], list[dict]]:
        return _apply_style_treatments(filled, blocks, style_id, images_dir)

    if prefers_stock_footage(style_id, style_consigne):
        if not api_key:
            print("       style « stock footage » demandé mais PEXELS_API_KEY absente — fond uni")
            return paths, [], [], []
        paths = _fetch_stock_blocks(
            blocks, niche, orientation, images_dir, api_key, durations, language, Path(work_dir), stock_report,
        )
        return paths, [], [], []

    character_prefix = image_character_bible.build_character_prefix(characters, style_consigne)

    # 1re passe (rapide, pas de réseau) : sert le cache disque et repère ce
    # qui reste vraiment à générer.
    pending: list[tuple[list[int], Path, str]] = []
    for group in _group_blocks(n, _BLOCKS_PER_IMAGE):
        if len(group) == 1 and group[0] > 0 and blocks[group[0]].get("reuse_visual_from_previous"):
            continue
        image_path = images_dir / f"scene-{group[0] + 1:02d}.jpg"
        if _exists_nonempty(image_path):
            for i in group:
                paths[i] = str(image_path)
            continue
        texts = [_block_visual_text(blocks[i]) for i in group]
        # Le shotType du 1er bloc du groupe représente la scène — un groupe
        # >1 bloc (VISUALS_BLOCKS_PER_IMAGE) reste l'exception, voir plus haut.
        shot_type = blocks[group[0]].get("shotType")
        prompt = image_prompt_builder.build_scene_prompt(
            texts, niche, character_prefix, aspect_ratio, style_bible, shot_type=shot_type
        )
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
                # `blockIndex` (0-based, 1er bloc du groupe) : sert à retrouver
                # la raison d'échec d'un bloc précis pour `_build_fallback_events`.
                report["blockIndex"] = group[0]
                scene_reports.append(report)

    for i, block in enumerate(blocks):
        if i > 0 and block.get("reuse_visual_from_previous"):
            paths[i] = paths[i - 1]

    motion_profile = style_bible["motion_profile"]
    openai_enabled = bool(os.environ.get("OPENAI_API_KEY"))
    if openai_enabled:
        # AI-image est la stratégie principale de cette vidéo (Phase 2.6,
        # correctif du benchmark) : un bloc encore sans visuel a échoué à la
        # génération (moderation, réseau, timeout...) — basculer sur une
        # photo Pexels sans rapport casserait le style ET le personnage pour
        # CE seul bloc, alors que le reste de la vidéo reste dans le style
        # demandé. Repli : réutilisation d'une scène déjà générée dans la
        # MÊME vidéo (voisin le plus proche, précédent en priorité — voir
        # `_fill_missing_visuals`), jamais Pexels. Le mouvement de caméra
        # (engine/motion_profiles.py) est recalculé pour le bloc receveur —
        # jamais pour le bloc source — donc la scène réutilisée ne bouge pas
        # à l'identique (voir `resolve_motion_sequence`).
        fallback_sources = _nearest_fallback_sources(paths)
        filled = _fill_missing_visuals(paths)
        fallback_events = _build_fallback_events(
            filled, fallback_sources, scene_reports, style_id, motion_profile, "ai_image",
        )
        treated, treatment_reports = _treat(filled)
        return treated, scene_reports, fallback_events, treatment_reports

    if not api_key:
        treated, treatment_reports = _treat(_fill_missing_visuals(paths))
        return treated, scene_reports, [], treatment_reports

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

    # Ici, OpenAI n'est pas configuré du tout : Pexels EST la stratégie
    # principale de cette vidéo (pas un repli d'identité IA) — une
    # réutilisation entre blocs Pexels ne casse aucun style.
    fallback_sources = _nearest_fallback_sources(paths)
    filled = _fill_missing_visuals(paths)
    fallback_events = _build_fallback_events(
        filled, fallback_sources, scene_reports, style_id, motion_profile, "pexels_photo",
    )
    treated, treatment_reports = _treat(filled)
    return treated, scene_reports, fallback_events, treatment_reports


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


def _nearest_fallback_sources(paths: list[str | None]) -> dict[int, int]:
    """Pour chaque bloc encore sans visuel, l'index (0-based) du bloc déjà
    généré qui va le combler — MÊME règle de voisinage que `_fill_missing_visuals`
    (bloc précédent d'abord, sinon suivant), calculée séparément AVANT l'appel à
    `_fill_missing_visuals` pour construire les métadonnées de repli
    (`_build_fallback_events`) sans toucher à cette fonction historique."""
    available = [i for i, path in enumerate(paths) if path]
    sources: dict[int, int] = {}
    if not available:
        return sources
    for i, path in enumerate(paths):
        if path is None:
            sources[i] = min(available, key=lambda candidate: (abs(candidate - i), candidate > i))
    return sources


# Identité visuelle : un profil de mouvement "kinetic"/"none" correspond à un
# style sans image IA (typographie/stock/rendu local) — un repli Pexels n'y
# casse rien puisqu'il n'y a pas d'identité graphique IA à préserver. Tout
# autre profil (cinematic/gentle/energetic/comic) EST une identité graphique
# IA : un fichier `block-NN.*` (photo Pexels, voir `_search_query`/`_fetch_stock_clip`)
# à la place d'un `scene-NN.jpg` y casse le style — voir `is_style_integrity_preserved`.
_AI_IMAGE_MOTION_PROFILES = {"cinematic", "gentle", "energetic", "comic"}
_PEXELS_PHOTO_FALLBACK_RE = re.compile(r"[/\\]block-\d+\.jpg$", re.IGNORECASE)


def is_style_integrity_preserved(motion_profile: str, asset_path: str | None) -> bool:
    """Signal de qualité déterministe (aucun appel IA) : `False` seulement
    quand un style à identité graphique IA (`_AI_IMAGE_MOTION_PROFILES`) se
    retrouve avec une photo Pexels de repli (`block-NN.jpg`) — le seul cas qui
    casse visiblement le style. Une réutilisation d'un `scene-NN.jpg` du même
    style, ou tout asset pour un style qui n'a pas d'identité IA à préserver
    (stock footage, motion graphics, typographie cinétique), est `True`."""
    if motion_profile not in _AI_IMAGE_MOTION_PROFILES:
        return True
    if not asset_path:
        return True  # fond uni neutre : pas idéal, mais ne casse pas le style
    return not bool(_PEXELS_PHOTO_FALLBACK_RE.search(asset_path.replace("\\", "/")))


def _build_fallback_events(
    paths_after: list[str | None],
    fallback_sources: dict[int, int],
    scene_reports: list[dict],
    style_id: str,
    motion_profile: str,
    asset_strategy: str,
) -> list[dict]:
    """Section 5/6 du benchmark (Phase 2.6) : une entrée par bloc dont le
    visuel a dû être comblé par réutilisation — jamais pour un bloc qui avait
    déjà son propre visuel. Consommée par `assembler.py` (metrics) et
    `engine.quality` (pénalité si l'identité de style est cassée)."""
    reports_by_block = {r["blockIndex"]: r for r in scene_reports if "blockIndex" in r}
    events: list[dict] = []
    for block_index, source_index in fallback_sources.items():
        report = reports_by_block.get(block_index)
        events.append({
            "blockIndex": block_index,
            "requestedVisualStyle": style_id,
            "assetStrategy": asset_strategy,
            "failureType": (report or {}).get("failureReason") or "generation_unavailable",
            "fallbackStrategy": "reuse_same_video_scene",
            "fallbackSource": source_index,
            "styleIntegrityPreserved": is_style_integrity_preserved(motion_profile, paths_after[block_index]),
        })
    return events


def _apply_style_treatments(
    paths: list[str | None], blocks: list[dict], style_id: str, images_dir: Path,
) -> tuple[list[str | None], list[dict]]:
    """Phase 3 : passe de compositing locale (`engine.style_treatments`,
    `comic_book`/`gta_loading` uniquement) sur les visuels déjà résolus —
    génération fraîche OU réutilisation Phase 2.6, peu importe : ce qui
    compte est l'image FINALEMENT assignée à CE bloc, traitée avec les
    métadonnées shotType/visualPurpose de CE bloc (voir la section 13 du
    brief Phase 3 : un bloc qui réutilise la scène d'un voisin reçoit quand
    même SON PROPRE traitement, jamais celui du voisin).

    Un fichier `.treated.jpg` par bloc, nommage prévisible — l'original
    (`scene-NN.jpg`/`block-NN.jpg`) n'est jamais modifié (debug/comparaison,
    voir section 12). Mis en cache sur disque comme le reste du pipeline
    (relance = pas de retraitement). Jamais bloquant : un échec de filtre
    graphique retombe sur l'image d'origine pour ce bloc, jamais un échec de
    rendu."""
    if not style_treatments.has_treatment(style_id):
        return paths, []
    treated_paths = list(paths)
    reports: list[dict] = []
    for i, (path, block) in enumerate(zip(paths, blocks)):
        if not path:
            continue
        out_path = images_dir / f"scene-{i + 1:02d}.treated.jpg"
        if _exists_nonempty(out_path):
            treated_paths[i] = str(out_path)
            reports.append({"blockIndex": i, "styleTreatment": style_id, "treatmentApplied": True, "cached": True})
            continue
        try:
            metadata = style_treatments.apply_treatment(
                style_id, path, str(out_path), block.get("shotType"), block.get("visualPurpose"),
            )
            treated_paths[i] = str(out_path)
            reports.append({"blockIndex": i, **(metadata or {})})
        except Exception as exc:  # noqa: BLE001 - un filtre graphique ne casse jamais le rendu
            print(f"       bloc {i + 1} : traitement de style « {style_id} » échoué ({exc}) — image d'origine conservée")
            reports.append({"blockIndex": i, "styleTreatment": style_id, "treatmentApplied": False, "error": str(exc)})
    return treated_paths, reports


def _fetch_stock_photo(query: str, photo_path: Path, orientation: str, api_key: str) -> str | None:
    """Dernier repli d'un bloc stock : une photo Pexels pour la requête la plus
    large de son échelle (comportement historique, mais après l'échelle
    sémantique). `None` -> fond uni."""
    url = search_image_url(query, api_key, orientation)
    if url:
        try:
            download_image(url, str(photo_path))
            return str(photo_path)
        except requests.RequestException:
            pass
    return None


def _fetch_stock_blocks(
    blocks: list[dict], niche: str | None, orientation: str, images_dir: Path, api_key: str,
    durations: list[float] | None, language: str | None, work_dir: Path, report: dict | None,
) -> list[str | None]:
    """Phase 4 : plan sémantique (1 appel LLM max pour toute la vidéo) -> échelle
    de requêtes -> pool de candidats classés de façon déterministe ->
    téléchargement du gagnant. Voir engine/stock_planner.py."""
    t0 = time.monotonic()
    plans, planning = stock_planner.plan_blocks(blocks, niche, language, work_dir)
    paths, block_reports = stock_planner.select_stock_clips(
        blocks, plans, images_dir=images_dir, durations=durations, orientation=orientation,
        search_fn=lambda q, o: search_video_candidates(q, api_key, o),
        download_fn=lambda url, out: _download(url, out, timeout=90),
        photo_fn=lambda q, out: _fetch_stock_photo(q, out, orientation, api_key),
    )
    for r in block_reports:
        if r.get("fallback") not in {"reused_previous"} and not r.get("cached"):
            print(
                f"       bloc {r['blockIndex'] + 1} : « {r.get('selectedQuery')} » "
                f"({r.get('fallback')}, {r.get('candidateCount', 0)} candidats, {r.get('searches', 0)} recherche(s))"
            )
    if report is not None:
        report["planning"] = planning
        report["blocks"] = block_reports
        report["searches"] = sum(r.get("searches", 0) for r in block_reports)
        report["seconds"] = round(time.monotonic() - t0, 2)
    return paths


def _exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _merge_usage(total: dict | None, usage: dict | None) -> dict | None:
    """Somme les tokens de plusieurs appels image d'une même scène (génération
    + éventuelles corrections QC). None tant qu'aucun usage n'a été renvoyé."""
    if not usage:
        return total
    if not total:
        return dict(usage)
    return {key: total.get(key, 0) + usage.get(key, 0) for key in ("input_text", "input_image", "output")}


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
    usage = openai_images.pop_last_usage() if path else None
    report = {
        "model": selection.model,
        "quality": selection.quality,
        "purpose": "final",
        "attempts": 1,
        "estimatedCost": image_model_router.estimate_cost(selection.model, selection.quality, usage) if path else 0.0,
        "usage": _merge_usage(None, usage),
        "qualityScore": None,
        "approved": None,
        "manualReview": False,
    }
    report["failureReason"] = None if path else openai_images.pop_last_error()
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
            usage = openai_images.pop_last_usage() if fixed else None
            report["usage"] = _merge_usage(report["usage"], usage)
            report["estimatedCost"] += (
                image_model_router.estimate_cost(edit_selection.model, edit_selection.quality, usage) if fixed else 0.0
            )
        else:
            regen_selection = image_model_router.select_model("final")
            fixed = openai_images.generate_image(
                prompt, out_path, aspect_ratio, None, regen_selection.model, regen_selection.quality
            )
            usage = openai_images.pop_last_usage() if fixed else None
            report["usage"] = _merge_usage(report["usage"], usage)
            report["estimatedCost"] += (
                image_model_router.estimate_cost(regen_selection.model, regen_selection.quality, usage) if fixed else 0.0
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
