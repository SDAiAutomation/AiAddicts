"""Orchestrate one script.json into a finished, ready-to-publish clip.

Re-running on the same script is cheap: any per-block audio and the final
video already present under output/<slug>/ are reused. Delete that folder to
force a clean rebuild (e.g. after editing the script text).
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .explainer import access as explainer_access, integration as explainer_integration
from .story_animation import contract as story_animation_contract
from . import (
    asset_store, captions, db, editorial_quality, events, generation_cache, image_style_bible,
    math_narration, moderation, motion_profiles, originality, poster, publish_pack, quality, quiz_backdrop, quiz_cover, quiz_motion, quiz_shorts, repo, retention,
    script as script_module, shot_planning, storage, thumbnail, tts, versions, video, visuals, voices,
)

# Les appels ElevenLabs sont indépendants par bloc (I/O réseau) : quelques-uns
# en parallèle réduisent le temps total de "somme des blocs" à ~"bloc le plus
# long", sans risquer de se faire rate-limiter par l'API.
_MAX_TTS_WORKERS = 4

# Le programme TikTok Creator Rewards (monétisation) n'accepte que les vidéos
# d'au moins 60s — voir https://www.tiktok.com/creators/creator-rewards-program.
MIN_MONETIZABLE_DURATION_S = 60.0


def _exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def block_voice_id(data: dict, block: dict, default: str) -> str:
    """Voix d'un bloc. Seul le format `story` (un personnage = une voix) peut en imposer une par bloc ; pour tous les
    autres formats un `voice_id` de bloc est ignoré, donc Standard et Quiz gardent une seule voix par vidéo."""
    if data.get("content_format") == "story":
        voice = block.get("voice_id")
        if isinstance(voice, str) and voice.strip():
            return voice.strip()
    return default


def voice_text_for(data: dict, block: dict) -> str:
    """Texte réellement envoyé à la synthèse vocale (partagé avec l'export des chapitres : même clé de cache)."""
    is_french_math = str(data.get("language", "fr")).startswith("fr") and "math" in str(data.get("niche", "")).lower()
    return math_narration.for_voice(block["text"]) if is_french_math else block["text"]


def _generate(
    data: dict,
    output_root: str,
    voice_override: str | None,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[str, Path, dict | None]:
    """Étapes 1-4, communes aux deux points d'entrée : script -> voix off ->
    assemblage -> vidéo finale sous-titrée. Mute `data` (ajoute `voice_id`
    quand une voix est résolue). Retourne (chemin vidéo finale, dossier de
    travail, métriques de contrôle qualité — ou None si la vidéo était déjà
    rendue, rien de neuf à juger).

    `on_progress`, si fourni, est appelé à chaque étape majeure avec un libellé
    court (ex: "Voix off (ElevenLabs)") — c'est ce qui alimente la colonne
    `content_items.generation_step` affichée sur /content/[id] côté
    growthos-web. Optionnel : le CLI (`run()`) n'a pas encore de content_item_id
    à ce stade et passe None, sans que rien ne change pour lui."""
    step = on_progress or (lambda _label: None)

    slug = script_module.slug(data)
    voice_id = voices.resolve_voice(data, voice_override)
    data["voice_id"] = voice_id
    cache_key = generation_cache.fingerprint(data, voice_id)
    work_dir = Path(output_root) / f"{slug}-{cache_key}"
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    pexels_key = os.environ.get("PEXELS_API_KEY")

    n_blocks = len(data["blocks"])
    print(f"[1/5] Script chargé : {data['title']} ({n_blocks} blocs)")
    step("Chargement du script")
    editorial_report = editorial_quality.analyze_script(data)
    if editorial_report["issues"]:
        print(f"       qualité éditoriale : {editorial_report['score']}/100")
        for issue in editorial_report["issues"]:
            print(f"         - {issue}")

    final_path = work_dir / "final" / f"{slug}.mp4"
    srt_path = work_dir / "captions.srt"
    quiz_report_path = work_dir / "quiz-presentation.json"

    if _exists_nonempty(final_path) and _exists_nonempty(srt_path):
        # Chemin de re-run le moins cher : la vidéo finale et ses sous-titres
        # sont déjà là, on ne retouche ni ElevenLabs ni ffmpeg. Supprime
        # output/<slug>/ pour forcer une reconstruction (script modifié).
        print("[2-5/5] Vidéo finale + sous-titres déjà présents — réutilisés")
        step("Finalisation (vidéo déjà rendue)")
        presentation = quiz_motion.presentation_info(data)
        if presentation:
            cached_report = {**presentation, "timingSource": "unavailable",
                             "renderSeconds": None, "renderCostUsd": None}
            try:
                stored_report = json.loads(quiz_report_path.read_text(encoding="utf-8"))
                if isinstance(stored_report, dict) and all(stored_report.get(k) == v for k, v in presentation.items()):
                    cached_report = stored_report
            except (OSError, ValueError):
                # A missing diagnostic does not invalidate a completed video.
                # Missing measurements stay unknown, never zero.
                pass
            quiz_motion.attach_report(data, {**cached_report, "reusedFinalVideo": True})
        return str(final_path), work_dir, None

    # Caractères réellement facturés par ElevenLabs cette fois (les blocs dont
    # l'audio est réutilisé depuis le disque ne coûtent rien). `list.append`
    # est atomique : sûr depuis les threads du pool.
    synthesized_chars: list[int] = []

    def _synthesize_block(i: int, block: dict) -> tuple[str, float, list[dict]]:
        audio_path = work_dir / "audio" / f"block-{i:02d}.mp3"
        words_path = work_dir / "audio" / f"block-{i:02d}.words.json"
        voice_text = voice_text_for(data, block)
        block_voice = block_voice_id(data, block, voice_id)
        # Cache d'actifs (lot L1) : clé = texte + voix + réglages de synthèse.
        # Un bloc dont ces entrées n'ont pas changé garde sa voix et son timing.
        voice_key = asset_store.make_key(
            kind="voice", text=voice_text, voice_id=block_voice,
            model=tts.TTS_MODEL_ID, settings=tts.TTS_VOICE_SETTINGS,
        )
        if _exists_nonempty(audio_path) and words_path.exists():
            print(f"[2/5] Voix off {i}/{n_blocks} — fichier existant réutilisé")
            words = json.loads(words_path.read_text(encoding="utf-8"))
        elif asset_store.restore_voice(voice_key, audio_path, words_path):
            print(f"[2/5] Voix off {i}/{n_blocks} — réutilisée (entrées identiques)")
            words = json.loads(words_path.read_text(encoding="utf-8"))
        else:
            print(f"[2/5] Voix off {i}/{n_blocks} (voix {block_voice})…")
            # Timing mot par mot (pas juste l'audio) : sert aux sous-titres
            # animés par groupes de mots, voir captions.build_cues.
            words = tts.synthesize_with_timestamps(voice_text, block_voice, str(audio_path), api_key)
            synthesized_chars.append(len(voice_text))
            words_path.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
            rate = _voice_rate_per_1k_chars()
            asset_store.save_voice(
                voice_key, audio_path, words_path,
                round(len(voice_text) / 1000 * rate, 4) if rate is not None else None,
            )
        rendered_audio = str(audio_path)
        hold_after = float(block.get("hold_after_seconds") or 0)
        motion_graphic = block.get("motion_graphic")
        if isinstance(motion_graphic, dict) and motion_graphic.get("sceneType") == "equation_steps" and hold_after <= 0:
            # Temps de lecture du résultat : la voix s'arrête sur « x égale quatre », l'écran doit
            # rester le temps de le lire. Le silence est ajouté À L'AUDIO (donc à la durée du bloc,
            # des sous-titres et de la timeline), jamais en compressant l'animation.
            from .motion_graphics import math_steps

            extra = math_steps.extra_hold_seconds(motion_graphic, words, tts.get_duration_seconds(str(audio_path)))
            if extra > 0:
                held_path = work_dir / "audio" / f"block-{i:02d}-hold-{int(extra * 100)}.mp3"
                if not _exists_nonempty(held_path):
                    video.pad_audio(str(audio_path), extra, str(held_path))
                rendered_audio = str(held_path)
        hold_after = float(block.get("hold_after_seconds") or 0)
        beat = float(block.get("quiz_reveal_beat_seconds") or 0) if hold_after > 0 else 0.0
        if hold_after > 0:
            padded_path = work_dir / "audio" / f"block-{i:02d}-padded.mp3"
            quiz_shorts.ensure_padded_audio(block, audio_path, padded_path)
            rendered_audio = str(padded_path)
        # Quiz : durée DÉCODÉE (celle que concat_audio assemble) ; la durée d'en-tête mp3 dérive d'~25 ms par bloc,
        # soit ~3 s sur les ~107 blocs d'un quiz de 50 questions.
        measure = tts.get_playback_duration_seconds if data.get("content_format") == "quiz" else tts.get_duration_seconds
        return rendered_audio, measure(rendered_audio), words

    step(f"Voix off (ElevenLabs, {n_blocks} bloc(s))")
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(_MAX_TTS_WORKERS, n_blocks)) as pool:
        # I/O réseau (requests) libère le GIL pendant l'attente : des threads
        # suffisent, pas besoin de multiprocessing pour ce genre de parallélisme.
        results = list(pool.map(_synthesize_block, range(1, n_blocks + 1), data["blocks"]))
    print(f"       voix off terminées en {time.monotonic() - t0:.1f}s")

    audio_paths = [path for path, _duration, _words in results]
    durations = [duration for _path, duration, _words in results]
    block_words = [(words, duration) for _path, duration, words in results]
    quiz_report = quiz_motion.build_timeline(data, durations)

    total_duration = sum(durations)
    if data.get("content_goal") == "monetization" and total_duration < MIN_MONETIZABLE_DURATION_S:
        print(
            f"       ATTENTION : voix off de {total_duration:.1f}s (< {MIN_MONETIZABLE_DURATION_S:.0f}s) — "
            "non éligible au programme TikTok Creator Rewards (monétisation), qui exige 60s minimum. "
            "Allonge le script si la monétisation est visée."
        )

    openai_enabled = bool(os.environ.get("OPENAI_API_KEY"))
    quiz_format = data.get("content_format") == "quiz"
    # Explainer animé (bêta admin) : testé avant les autres styles, exclusif avec eux (ni image IA ni personnage).
    explainer_style = not quiz_format and visuals.prefers_explainer(data)
    motion_graphics_style = not quiz_format and not explainer_style and visuals.prefers_motion_graphics(
        (data.get("visual_style") or ""),
        (data.get("visual_style_prompt") or ""),
    )
    kinetic_typography_style = not quiz_format and not explainer_style and not motion_graphics_style and visuals.prefers_kinetic_typography(
        (data.get("visual_style") or ""),
        (data.get("visual_style_prompt") or ""),
    )
    stock_footage = not explainer_style and not motion_graphics_style and not kinetic_typography_style and visuals.prefers_stock_footage(
        (data.get("visual_style") or ""),
        (data.get("visual_style_prompt") or ""),
    )
    if explainer_style:
        visuals_desc = "Explainer animé (Chromium, plan par plan ; coût LLM au rapport)"
    elif motion_graphics_style:
        visuals_desc = "motion graphics (rendu local, sans appel API)"
    elif kinetic_typography_style:
        visuals_desc = "typographie cinétique (rendu local, sans appel API) + fond uni en repli"
    elif quiz_format and (data.get("quiz") or {}).get("illustrations") is False:
        visuals_desc = "quiz sans illustration (aucune image générée)"
    elif stock_footage:
        visuals_desc = "vidéos de stock Pexels par bloc" if pexels_key else "fond uni — pas de clé Pexels"
    elif openai_enabled:
        visuals_desc = "OpenAI, une image par bloc" + (" + Pexels en repli" if pexels_key else "")
    else:
        visuals_desc = "Pexels photo par bloc" if pexels_key else "fond uni — pas de clé"
    if openai_enabled and not explainer_style and not stock_footage and not motion_graphics_style and not kinetic_typography_style and data.get("characters"):
        names = ", ".join(str(c.get("name", "?")) for c in data["characters"])
        visuals_desc += f" — fiche personnage : {names}"
    print(f"[3/5] Visuels ({visuals_desc})…")
    step(f"Visuels ({visuals_desc})")
    t0 = time.monotonic()
    # `visual_fallbacks` (Phase 2.6) : observabilité des reprises de visuel —
    # voir `visuals._build_fallback_events`. Seul `fetch_block_images` (styles
    # image IA) l'alimente aujourd'hui : motion_graphics/kinetic_typography
    # gèrent déjà leurs propres reprises sans casser leur identité (rendu
    # local dans les deux cas), stock_footage n'a pas d'identité IA à casser.
    stock_selection: dict = {}
    motion_preflight: list = []
    backdrop_flags = [False] * n_blocks  # blocs dont l'image est un fond illustré (pas une fenêtre d'illustration)
    explainer_report: dict | None = None
    if explainer_style:
        # Voix déjà synthétisée (ci-dessus) : on réutilise l'audio et les mots par bloc, on ne resynthétise rien.
        image_paths, explainer_report = explainer_integration.generate_clips(
            data, durations, [words for words, _duration in block_words], work_dir,
        )
        print(f"       Explainer : {explainer_report['plans']} plan(s), {explainer_report['fallbacks']} repli(s), "
              f"LLM {explainer_report['llmCostUsd']} $, rendu {explainer_report['renderSeconds']} s")
        image_reports = []
        visual_fallbacks = []
        style_treatment_reports = []
    elif motion_graphics_style:
        image_paths = visuals.fetch_motion_graphics_clips(
            data["blocks"], durations, data["aspect_ratio"], work_dir,
            theme_overrides=data.get("motion_graphics_theme"), preflight_report=motion_preflight,
        )
        image_reports: list[dict] = []
        visual_fallbacks: list[dict] = []
        style_treatment_reports: list[dict] = []
    elif kinetic_typography_style:
        image_paths = visuals.fetch_kinetic_typography_clips(
            data["blocks"], durations, data["aspect_ratio"], work_dir,
        )
        image_reports = []
        visual_fallbacks = []
        style_treatment_reports = []
    elif quiz_format and (data.get("quiz") or {}).get("illustrations") is False:
        # Quiz « sans illustration » : aucune image générée (ni appel API), la
        # fenêtre d'image disparaît et les réponses remontent (voir captions.py).
        image_paths = [None] * n_blocks
        image_reports = []
        visual_fallbacks = []
        style_treatment_reports = []
        if quiz_backdrop.enabled(data):
            # Fond illustré : une image de sujet par partie (4), en bichromie, jamais bloquant (voir quiz_backdrop).
            backdrops = quiz_backdrop.generate(data, work_dir)
            for index, block in enumerate(data["blocks"]):
                path = backdrops[quiz_motion.part_index(block)]
                if path:
                    image_paths[index], backdrop_flags[index] = path, True
            print(f"       fond illustré : {sum(1 for p in backdrops if p)}/{len(backdrops)} image(s)")
    else:
        image_paths, image_reports, visual_fallbacks, style_treatment_reports = visuals.fetch_block_images(
            data["blocks"], data.get("niche"), data["aspect_ratio"], work_dir, pexels_key,
            characters=data.get("characters"),
            # `visual_style` = id du pack (sert la décision "stock footage vs IA") ;
            # `visual_style_prompt` = phrase de style résolue par Faceloop pour le
            # prompt d'image. En CLI seul `visual_style` est renseigné.
            visual_style=data.get("visual_style"),
            visual_style_prompt=data.get("visual_style_prompt"),
            durations=durations, language=data.get("language"), stock_report=stock_selection,
        )
    found = sum(1 for p in image_paths if p)
    suffix = f"{found}/{n_blocks} image(s) trouvée(s), le reste en fond uni" if pexels_key else ""
    print(f"       terminé en {time.monotonic() - t0:.1f}s" + (f" — {suffix}" if suffix else ""))

    print("[4/5] Assemblage audio + sous-titres…")
    step("Assemblage audio + sous-titres")
    full_wav = work_dir / "audio" / "full.wav"
    if _exists_nonempty(full_wav):
        print("       piste audio complète existante réutilisée")
        full_audio = str(full_wav)
    else:
        full_audio = video.concat_audio(audio_paths, str(full_wav))

    if explainer_report:
        # Bruitages de l'Explainer sous la voix (même réglage que le rendu de l'Explainer) ; jamais silencieux : le rapport
        # dit s'ils sont inclus.
        mixed = explainer_integration.mix_sfx(full_audio, explainer_report["video"], work_dir / "audio" / "full-with-sfx.wav")
        explainer_report["sfxIncluded"] = bool(mixed)
        explainer_report["sfxMix"] = explainer_integration.sfx_mix_settings() if mixed else None
        if mixed:
            full_audio = mixed
        print(f"       bruitages Explainer : {'mixés sous la voix' if mixed else 'absents (aucune piste audio dans le MP4)'}")

    render_blocks = data["blocks"]
    render_durations = durations
    render_image_paths = image_paths
    render_backdrops = backdrop_flags
    cover = (data.get("quiz") or {}).get("cover") or {}
    if data.get("content_format") == "quiz" and cover.get("enabled"):
        cover_duration = float(cover.get("duration_seconds") or 0.8)
        covered_wav = work_dir / "audio" / "full-with-cover.wav"
        if not _exists_nonempty(covered_wav):
            video.prepend_silence(full_audio, cover_duration, str(covered_wav))
        full_audio = str(covered_wav)
        cover_block = {
            "role": "hook", "text": "", "quiz_phase": "cover",
            "quiz_theme": (data.get("quiz") or {}).get("theme", "studio"),
            "quiz_cover_title": cover.get("title"), "quiz_cover_brand": cover.get("brand", "BrainLoop"),
        }
        render_blocks = [cover_block, *data["blocks"]]
        render_durations = [cover_duration, *durations]
        render_image_paths = [quiz_cover.generate_cover(data, work_dir), *image_paths]
        render_backdrops = [False, *backdrop_flags]
    cue_words = ([([], render_durations[0])] + block_words) if render_blocks is not data["blocks"] else block_words
    cues = captions.build_cues(
        cue_words,
        block_roles=[str(block.get("role") or "") for block in render_blocks],
    )
    captions.write_srt(cues, str(srt_path))  # gardé pour debug / repli
    # Style Identity (Phase 2) : résolu une seconde fois ici (déjà fait une
    # fois à l'intérieur de `visuals.fetch_block_images` pour les styles
    # image IA) — appel pur et bon marché, plus simple que de faire remonter
    # le dict depuis `visuals.py` pour ce seul besoin.
    style_bible = image_style_bible.resolve_style_bible(data.get("visual_style"), data.get("visual_style_prompt"))
    motion_profile = style_bible["motion_profile"]
    transition = style_bible["transition"]
    fade_duration = 0.3 if transition == "fade" and not explainer_style else 0.0   # l'Explainer a ses propres transitions
    caption_style = captions.caption_style_or_default(data.get("caption_style"))
    resolution = video.RESOLUTIONS.get(data["aspect_ratio"], video.RESOLUTIONS["9:16"])
    # Quiz Motion : fond de base de la couleur de la scène (une teinte par partie d'un quiz long) plutôt
    # qu'un rectangle plein écran par image.
    block_backgrounds = [quiz_motion.base_background_for(data, fade_duration, block) for block in render_blocks]
    # Police de marque (celle de la miniature) pour la mise en scène Motion ; SUBTITLE_FONT garde la priorité,
    # et sans les fichiers de police on reste sur la police par défaut plutôt que de risquer des tailles fausses.
    motion_scene = (quiz_motion.presentation_info(data) or {}).get("mode") == "motion"
    brand_font = quiz_motion.BRAND_FONT if motion_scene and not os.environ.get("SUBTITLE_FONT") and quiz_motion.brand_font_available() else None
    caption_blocks = [
        ({**block, "quiz_visual_available": bool(render_image_paths[index]) and not render_backdrops[index]}
         if block.get("quiz_phase") in {"question", "reveal"} else block)
        for index, block in enumerate(render_blocks)
    ]
    if any(block_backgrounds):
        caption_blocks = [
            ({**block, "quiz_base_background": "#" + colour[2:].lower()} if colour else block)
            for block, colour in zip(caption_blocks, block_backgrounds)
        ]
    ass_file = captions.write_ass(
        cues, str(work_dir / "captions.ass"), caption_style, resolution,
        blocks=caption_blocks, block_durations=render_durations,
        centre_reserved=kinetic_typography_style, font=brand_font,
    )
    print(f"       sous-titres : style « {caption_style} »")

    render_shots = video.plan_shots(render_durations, render_image_paths)
    resolved_moves = motion_profiles.resolve_motion_sequence(render_shots, render_blocks, motion_profile)
    print(f"       mouvement : profil « {motion_profile} », transition « {transition} »")

    print(f"[5/5] Rendu vidéo finale ({n_blocks} clip(s))…")
    mode_label = " — Motion design" if quiz_report and quiz_report["mode"] == "motion" else ""
    step(f"Rendu vidéo final{mode_label} ({n_blocks} clip(s))")
    t0 = time.monotonic()
    final_video = video.render_final(
        full_audio, ass_file, str(final_path), render_durations,
        image_paths=render_image_paths, aspect_ratio=data["aspect_ratio"],
        static_blocks=render_backdrops if any(render_backdrops) else None,
        moves=resolved_moves, fade_duration=fade_duration,
        **({"bg_colors": block_backgrounds} if any(block_backgrounds) else {}),
        **({"fonts_dir": str(quiz_motion.FONT_DIR)} if brand_font else {}),
    )
    render_seconds = time.monotonic() - t0
    print(f"       vidéo finale rendue en {render_seconds:.1f}s")

    shots = video.plan_shots(durations, image_paths)
    hook_duration = next(
        (durations[i] for i, block in enumerate(data["blocks"]) if block.get("role") == "hook"),
        None,
    )
    # Retention Engine : diagnostics déterministes (aucun appel externe), écrits
    # dans le script (jsonb existant, pas de migration) pour /content/[id] et
    # la future boucle d'analytique. Ne modifie ni le rendu ni le cache.
    retention_report = retention.analyze(data, durations=durations, scene_reports=motion_preflight)
    data["retentionDiagnostics"] = retention_report
    data["generationMetadata"] = retention.build_generation_metadata(data, retention_report)
    if quiz_report:
        quiz_report["renderSeconds"] = round(render_seconds, 4)
        quiz_motion.attach_report(data, quiz_report)
        quiz_report_path.write_text(json.dumps(quiz_report, ensure_ascii=False, indent=2), encoding="utf-8")

    metrics = {
        "total_duration": total_duration,
        "content_goal": data.get("content_goal", "reach"),
        "n_blocks": n_blocks,
        "n_shots": len(shots),
        "max_shot_duration": max((shot[2] for shot in shots), default=0.0),
        "hook_duration": hook_duration,
        "blocks_with_image": found,
        "n_cues": len(cues),
        "visuals_possible": bool(os.environ.get("OPENAI_API_KEY")) or bool(pexels_key),
        "image_reports": image_reports,
        "voice_characters": sum(synthesized_chars),
        "script_usage": data.get("script_usage"),
        "editorial": editorial_report,
        "retention": retention_report,
        "shot_planning": shot_planning.analyze_shot_diversity(data["blocks"]),
        "motion_direction": {
            "visualStyle": data.get("visual_style"),
            "motionProfile": motion_profile,
            "transition": transition,
            "moves": resolved_moves,
            **motion_profiles.analyze_motion_diversity(resolved_moves, shots=render_shots),
        },
        "visual_fallbacks": visual_fallbacks,
        "style_treatments": style_treatment_reports,
        # Phase 4 : plan sémantique + choix par bloc (style stock footage), sinon None.
        "stock_selection": stock_selection or None,
        # Motion Graphics : synchro voix + contrôle de mise en page par bloc (liste vide sinon).
        "motion_preflight": motion_preflight,
        "quiz_presentation": quiz_report,
        "explainer": explainer_report,
    }
    return final_video, work_dir, metrics


# Limite par fichier de Supabase Storage (50 Mo par défaut, indépendante de la
# limite du bucket) : au-delà l'upload échoue avec "exceeds the maximum allowed
# size". Les vidéos longues (quiz ~125 s) à CRF 19 la dépassent.
_UPLOAD_LIMIT_BYTES = 45 * 1024 * 1024


def _shrink_to_upload_limit(local_path: str) -> None:
    """Ré-encode en place à un débit calculé pour tenir sous la limite d'upload."""
    import subprocess

    path = Path(local_path)
    if not path.exists() or path.stat().st_size <= _UPLOAD_LIMIT_BYTES:
        return
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    duration = float(probe.stdout.strip())
    audio_bps = 128_000
    video_bps = int((_UPLOAD_LIMIT_BYTES * 8 * 0.95) / duration) - audio_bps
    print(f"       fichier {path.stat().st_size / 1048576:.0f} Mo > limite, ré-encodage à {video_bps // 1000} kbit/s")
    tmp = path.with_suffix(".small.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-preset", "veryfast", "-b:v", str(video_bps), "-maxrate", str(int(video_bps * 1.3)),
         "-bufsize", str(video_bps * 2), "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", str(tmp)],
        check=True, capture_output=True,
    )
    tmp.replace(path)


def _publish_video(
    client, content_item_id: str, local_path: str, on_progress: Callable[[str], None] | None = None,
    require_remote: bool = False, version: int | None = None,
) -> str:
    """Upload la vidéo rendue vers Supabase Storage (bucket `content-videos`,
    public) pour que `video_url` soit une vraie URL partageable plutôt qu'un
    chemin local à la machine du worker. 3 tentatives (un blip réseau ou un
    timeout sur un gros fichier est le cas courant). Ensuite :
    - `require_remote=False` (CLI locale) : retombe sur le chemin local, la
      vidéo existe bel et bien sur cette machine ;
    - `require_remote=True` (worker) : lève. Le fichier vit sur un runner
      éphémère, un chemin local n'y serait plus jamais lisible par personne —
      mieux vaut un statut `failed` explicite qu'un aperçu introuvable."""
    if on_progress:
        on_progress("Upload de la vidéo")
    local_path = _resolve_rendered_video_path(local_path)
    _shrink_to_upload_limit(local_path)
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            url = storage.upload_video(client, content_item_id, local_path, version=version)
            print(f"       vidéo uploadée : {url}")
            return url
        except Exception as exc:
            last_exc = exc
            print(f"       upload Supabase Storage échoué, tentative {attempt}/3 ({exc})")
            if attempt < 3:
                time.sleep(3 * attempt)
    if require_remote:
        raise RuntimeError(f"upload de la vidéo échoué après 3 tentatives : {last_exc}") from last_exc
    print("       video_url reste le chemin local")
    return local_path


def _resolve_rendered_video_path(local_path: str) -> str:
    """Return a stable absolute path for the rendered file.

    A queued job can be resumed from a different working directory or after a
    cache directory has been recreated. In that case the stored relative path
    may be stale even though the rendered filename is still present under the
    worker's output root. Restrict the fallback search to the local ``output``
    directory and require a non-empty regular file; never guess outside the
    worker workspace.
    """
    candidate = Path(local_path).expanduser().resolve()
    if candidate.is_file() and candidate.stat().st_size > 0:
        return str(candidate)

    output_root = candidate
    for parent in candidate.parents:
        if parent.name == "output":
            output_root = parent
            break
    else:
        return str(candidate)

    matches = [
        path for path in output_root.glob(f"*/final/{candidate.name}")
        if path.is_file() and path.stat().st_size > 0
    ]
    if len(matches) == 1:
        print(f"       chemin vidéo restauré depuis le cache : {matches[0]}")
        return str(matches[0].resolve())
    if not matches:
        raise FileNotFoundError(f"vidéo finale introuvable : {candidate}")
    raise FileNotFoundError(f"plusieurs vidéos finales correspondent à {candidate.name}")


def _publish_poster(client, content_item_id: str, final_video: str, work_dir: Path) -> str | None:
    """Miniature JPEG de la vidéo, pour les listes (voir engine/poster.py).
    Facultatif : tout échec retourne None et la vidéo reste publiable — jamais
    d'exception vers l'appelant."""
    try:
        poster_path = poster.extract_poster(final_video, str(work_dir / "poster.jpg"))
        return storage.upload_poster(client, content_item_id, poster_path)
    except Exception as exc:
        print(f"       poster non généré ({exc}) — la liste affichera une icône")
        return None


def _publish_thumbnail(client, content_item_id: str, data: dict, work_dir: Path) -> None:
    """Miniatures YouTube des quiz longs (voir engine/thumbnail.py).

    `script.thumbnail_url` = variante A, envoyée automatiquement par la
    publication YouTube du site ; `script.thumbnail_variants` = A, B, C pour le
    téléchargement et le test A/B manuel de YouTube Studio. Facultatif : tout
    échec laisse la vidéo publiable, sans miniature personnalisée, et ne lève jamais."""
    if not thumbnail.is_long_quiz(data):
        return
    try:
        built = thumbnail.build_variants_for_script(data, str(work_dir))
        variants = []
        for variant, info in built.items():
            report = info["report"]
            if report["issues"]:
                print(f"       miniature {variant} : {', '.join(report['issues'])}")
            variants.append({"id": variant, "axis": info["axis"],
                             "url": storage.upload_thumbnail(client, content_item_id, info["path"], variant)})
        data["thumbnail_variants"] = variants
        data["thumbnail_url"] = variants[0]["url"]
    except Exception as exc:
        data.pop("thumbnail_url", None)
        data.pop("thumbnail_variants", None)
        print(f"       miniature YouTube non générée ({exc})")


def _apply_originality_check(
    data: dict, metrics: dict | None, client, account_id: str | None,
    exclude_content_item_id: str | None = None,
) -> None:
    """Mute `metrics` en place : ajoute `metrics["originality"]` si la
    capacité est active (`ORIGINALITY_CHECK_ENABLED`) et qu'un compte est
    connu — sinon ne fait rien, pas même une requête Supabase (même
    philosophie opt-in que le QC image). `metrics` peut être `None` (re-run
    d'une vidéo déjà rendue, rien de neuf à juger) : dans ce cas on ne fait
    rien non plus, comme le reste des contrôles qualité."""
    if metrics is None or not account_id or not originality.originality_enabled():
        return
    history = repo.get_recent_scripts(client, account_id, exclude_content_item_id=exclude_content_item_id)
    metrics["originality"] = originality.check_originality(data, history)


def _originality_report_dict(result: "originality.OriginalityResult") -> dict:
    return {
        "model": result.model,
        "comparedCount": result.compared_count,
        "historyAvailable": result.history_available,
        "tooSimilar": result.too_similar,
        "warn": result.warn,
        "overallSimilarity": result.overall_similarity,
        "dimensions": result.dimensions,
        "matchedVideoIds": result.matched_video_ids,
        "suggestion": result.suggestion,
    }


def _quality_fields(metrics: dict | None, final_video: str) -> dict:
    """Score la génération et renvoie les champs à écrire sur le content_item
    ({} si `metrics` est None — re-run d'une vidéo déjà rendue). Un score sous
    le seuil, ou une ressemblance forte avec l'historique du compte
    (`metrics["originality"]`, voir `_apply_originality_check`), bascule le
    statut en 'quality_check' (coup d'œil humain)."""
    if metrics is None:
        return {}
    score, flags = quality.score_generation(metrics, final_video)
    fields: dict = {"quality_score": score, "quality_flags": flags}
    if any(r.get("manualReview") for r in metrics.get("motion_preflight") or []):
        fields["status"] = "quality_check"
    if score < quality.PASS_THRESHOLD:
        fields["status"] = "quality_check"

    originality_result = metrics.get("originality")
    if originality_result is not None:
        fields["originality_report"] = _originality_report_dict(originality_result)
        if not originality_result.history_available:
            flags.append(
                "Historique insuffisant pour vérifier l'originalité (compte trop récent)."
            )
        elif originality_result.too_similar:
            flags.append(
                f"Ressemblance forte avec {len(originality_result.matched_video_ids)} vidéo(s) "
                f"précédente(s) (score diagnostique {originality_result.overall_similarity}/100, "
                f"comparé à {originality_result.compared_count} vidéo(s))."
            )
            fields["status"] = "quality_check"
        elif originality_result.warn:
            flags.append(
                f"Ressemblance notable avec {len(originality_result.matched_video_ids)} vidéo(s) "
                f"précédente(s) (score diagnostique {originality_result.overall_similarity}/100) "
                "— avertissement, publication non bloquée."
            )

    if fields.get("status") == "quality_check":
        print(f"       contrôle qualité : {score}/100 — passé en 'quality_check' :")
        for flag in flags:
            print(f"         - {flag}")
    else:
        print(f"       contrôle qualité : {score}/100 — OK")
    return fields


def _image_generation_report(metrics: dict | None) -> dict | None:
    """Rapport agrégé (coût estimé, versions, détail par scène) à partir des
    rapports individuels produits par `visuals.fetch_block_images` — `None`
    si `metrics` est None (re-run, rien de neuf) ou si aucune scène n'a été
    (re)générée cette fois (tout venait du cache disque, ou style « stock
    footage »/pas de clé OpenAI). Consommé par `run()`/`run_for_content_item`
    pour alimenter `content_items.image_generation_report`."""
    if not metrics:
        return None
    reports = metrics.get("image_reports") or []
    if not reports:
        return None
    manual_review = [r for r in reports if r.get("manualReview")]
    return {
        "promptVersion": image_style_bible.IMAGE_PROMPT_VERSION,
        "styleBibleVersion": image_style_bible.STYLE_BIBLE_VERSION,
        "totalEstimatedCost": round(sum(r.get("estimatedCost") or 0 for r in reports), 4),
        "scenesGenerated": len(reports),
        "scenesNeedingManualReview": len(manual_review),
        "scenes": reports,
    }


def _voice_rate_per_1k_chars() -> float | None:
    """Tarif ElevenLabs effectif ($ / 1000 caractères), propre à ton forfait
    (ex. Creator ~0,22) — pas de défaut codé en dur, il change avec le plan."""
    raw = os.environ.get("ELEVENLABS_USD_PER_1K_CHARS", "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _script_rates() -> tuple[float, float] | None:
    """Tarifs du modèle de script ($ / million de tokens, entrée puis sortie),
    propres à OPENAI_SCRIPT_MODEL — pas de défaut codé en dur."""
    try:
        return (
            float(os.environ["SCRIPT_PRICE_IN_PER_M"]),
            float(os.environ["SCRIPT_PRICE_OUT_PER_M"]),
        )
    except (KeyError, ValueError):
        return None


def _originality_rates() -> tuple[float, float] | None:
    """Tarifs du modèle de diagnostic d'originalité ($ / million de tokens,
    entrée puis sortie), propres à ORIGINALITY_MODEL — pas de défaut codé en
    dur (même motif que `_script_rates`)."""
    try:
        return (
            float(os.environ["ORIGINALITY_PRICE_IN_PER_M"]),
            float(os.environ["ORIGINALITY_PRICE_OUT_PER_M"]),
        )
    except (KeyError, ValueError):
        return None


def _cost_alert_limit() -> float | None:
    """Seuil ($) au-delà duquel une génération est signalée `overBudget`.
    Pas de défaut : à fixer d'après le coût moyen mesuré (ex. 1,5x la moyenne)."""
    raw = os.environ.get("GENERATION_COST_ALERT_USD", "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _generation_cost_report(metrics: dict | None) -> dict | None:
    """Coût variable d'UNE génération (images OpenAI + voix ElevenLabs), en $.
    `None` si `metrics` est None (re-run d'une vidéo déjà rendue : rien de neuf
    facturé). Les parts dont le tarif n'est pas configuré valent 0 et sont
    signalées dans `missingRates` plutôt que devinées — les volumes bruts
    (tokens, caractères) sont toujours enregistrés pour recalculer après coup.
    Le script LLM est compté quand `script.script_usage` est présent (scripts générés par l'IA du front). Hors périmètre : contrôle qualité vision, extraction des personnages, Stripe, stockage."""
    if not metrics:
        return None
    reports = metrics.get("image_reports") or []
    image_cost = round(sum(r.get("estimatedCost") or 0 for r in reports), 4)
    image_tokens = {"input_text": 0, "input_image": 0, "output": 0}
    priced_images = 0
    for r in reports:
        usage = r.get("usage")
        if usage:
            for key in image_tokens:
                image_tokens[key] += usage.get(key, 0)
        if (r.get("estimatedCost") or 0) > 0:
            priced_images += 1

    chars = int(metrics.get("voice_characters") or 0)
    rate = _voice_rate_per_1k_chars()
    voice_cost = round(chars / 1000 * rate, 4) if rate is not None else 0.0

    script_usage = metrics.get("script_usage")
    script = None
    script_cost = 0.0
    if isinstance(script_usage, dict):
        tokens_in = int(script_usage.get("input") or 0)
        tokens_out = int(script_usage.get("output") or 0)
        rates = _script_rates()
        if rates:
            script_cost = round((tokens_in * rates[0] + tokens_out * rates[1]) / 1_000_000, 4)
        script = {"model": script_usage.get("model"), "tokens": {"input": tokens_in, "output": tokens_out}, "cost": script_cost}

    originality_result = metrics.get("originality")
    originality_block = None
    originality_cost = 0.0
    if originality_result is not None and originality_result.usage:
        tokens_in = int(originality_result.usage.get("input") or 0)
        tokens_out = int(originality_result.usage.get("output") or 0)
        rates = _originality_rates()
        if rates:
            originality_cost = round((tokens_in * rates[0] + tokens_out * rates[1]) / 1_000_000, 4)
        originality_block = {
            "model": originality_result.model,
            "tokens": {"input": tokens_in, "output": tokens_out},
            "cost": originality_cost,
        }

    stock_planning = ((metrics.get("stock_selection") or {}).get("planning") or {})
    stock_block = None
    if stock_planning.get("llmCalls"):
        # Tokens toujours enregistrés ; pas de tarif codé en dur pour ce modèle
        # (STOCK_PLANNER_MODEL/ORIGINALITY_MODEL) -> coût non estimé ici.
        stock_block = {"model": stock_planning.get("model"), "calls": stock_planning["llmCalls"],
                       "tokens": stock_planning.get("tokens")}

    explainer = metrics.get("explainer")
    explainer_block = None
    explainer_cost = 0.0
    if isinstance(explainer, dict):
        # Coût LLM ESTIMÉ (tarifs de engine/explainer/llm.py) ; un modèle sans tarif connu reste inconnu, pas nul.
        explainer_cost = round(float(explainer.get("llmCostUsd") or 0.0), 4)
        explainer_block = {
            "cost": explainer_cost, "costUnknown": bool(explainer.get("llmCostUnknown")), "mode": explainer.get("mode"),
            "plans": explainer.get("plans"), "fallbacks": explainer.get("fallbacks"),
            "renderSeconds": explainer.get("renderSeconds"), "totalSeconds": explainer.get("totalSeconds"),
            "timingSource": explainer.get("timingSource"), "reused": bool(explainer.get("reused")),
            "useCritic": explainer.get("useCritic"), "sfxIncluded": explainer.get("sfxIncluded"), "sfxMix": explainer.get("sfxMix"),
            "inputTokens": explainer.get("inputTokens"), "outputTokens": explainer.get("outputTokens"),
            "cacheReadTokens": explainer.get("cacheReadTokens"), "cacheWriteTokens": explainer.get("cacheWriteTokens"),
            "costByStepUsd": explainer.get("costByStepUsd"), "cacheReadRate": explainer.get("cacheReadRate"),
        }

    missing: list[str] = []
    if explainer_block and (explainer_block["costUnknown"] or explainer.get("llmCostUsd") is None):
        missing.append("explainer")
    if script and not _script_rates():
        missing.append("script")
    if reports and priced_images < len(reports):
        missing.append("images")
    if chars and rate is None:
        missing.append("voice")
    if originality_block and not _originality_rates():
        missing.append("originality")

    total = round(image_cost + voice_cost + script_cost + originality_cost + explainer_cost, 4)
    limit = _cost_alert_limit()
    return {
        "currency": "USD",
        "images": {"count": len(reports), "cost": image_cost, "tokens": image_tokens},
        "voice": {"characters": chars, "cost": voice_cost},
        **({"script": script} if script else {}),
        **({"originality": originality_block} if originality_block else {}),
        **({"stockPlanning": stock_block} if stock_block else {}),
        **({"explainer": explainer_block} if explainer_block else {}),
        "totalEstimatedCost": total,
        "missingRates": missing,
        # Vrai si cette vidéo a coûté plus que le seuil d'alerte (GENERATION_COST_ALERT_USD).
        "overBudget": bool(limit and total > limit),
    }


def _apply_cost_report(fields: dict, metrics: dict | None) -> None:
    report = _generation_cost_report(metrics)
    if not report:
        return
    fields["generation_cost_report"] = report
    line = f"       coût estimé : {report['totalEstimatedCost']:.3f} $ (images {report['images']['cost']:.3f} + voix {report['voice']['cost']:.3f}"
    if report.get("script"):
        line += f" + script {report['script']['cost']:.3f}"
    if report.get("originality"):
        line += f" + originalité {report['originality']['cost']:.3f}"
    if report.get("explainer"):
        line += f" + Explainer {report['explainer']['cost']:.3f}"
    line += ")"
    if report["missingRates"]:
        line += f" — tarifs manquants : {', '.join(report['missingRates'])}"
    if report["overBudget"]:
        line += f" — ALERTE : au-dessus du seuil de {_cost_alert_limit():.2f} $"
    print(line)


def _apply_image_report(fields: dict, metrics: dict | None) -> None:
    """Mute `fields` (dict de colonnes à écrire sur le content_item) en place :
    ajoute `image_generation_report` si des scènes ont été (re)générées, et
    bascule le statut en `quality_check` si une scène nécessite une revue
    manuelle — réutilise le même mécanisme que `_quality_fields` (coup d'œil
    humain avant publication), sans jamais rétrograder un statut déjà pire."""
    report = _image_generation_report(metrics)
    if not report:
        return
    fields["image_generation_report"] = report
    if report["scenesNeedingManualReview"] and fields.get("status", "video") == "video":
        fields["status"] = "quality_check"


def run(script_path: str, output_root: str = "output", voice_override: str | None = None) -> dict:
    """Point d'entrée CLI (main.py) : script.json -> nouveau content_item.

    Crée l'organisation/le compte au besoin (get_or_create) — adapté à un
    opérateur qui lance le pipeline à la main, pas à un item déjà en base.
    """
    data = script_module.load_script(script_path)
    final_video, work_dir, metrics = _generate(data, output_root, voice_override)

    print("[5/6] Enregistrement dans Supabase…")
    client = db.get_service_client()
    organization_id = repo.get_or_create_organization(client, data["organization"])
    account_id = repo.get_or_create_account(
        client, organization_id, data["platform"], data["account"], data.get("niche")
    )
    _apply_originality_check(data, metrics, client, account_id)
    content_item_id = repo.create_content_item(
        client, account_id, data["title"], status="video", script=data, video_url=final_video
    )
    video_url = _publish_video(client, content_item_id, final_video)
    update_fields = _quality_fields(metrics, final_video)
    poster_url = _publish_poster(client, content_item_id, final_video, work_dir)
    if poster_url:
        update_fields["poster_url"] = poster_url
    _publish_thumbnail(client, content_item_id, data, work_dir)
    if data.get("thumbnail_url"):
        update_fields["script"] = data
    _apply_image_report(update_fields, metrics)
    _apply_cost_report(update_fields, metrics)
    if video_url != final_video:
        update_fields["video_url"] = video_url
    if update_fields:
        repo.update_content_item(client, content_item_id, **update_fields)

    print("[6/6] Package de publication…")
    pack = publish_pack.write_pack(
        data, final_video, str(work_dir / "publish"), content_item_id
    )

    print(f"\nTerminé. Vidéo (fichier local) : {final_video}")
    print(f"Vidéo (URL partagée) : {video_url}")
    print(f"Caption prête : {pack['caption']}")
    print(f"Checklist : {pack['checklist']}")
    print(f"content_item : {content_item_id}")
    print(
        "Une fois posté manuellement, logge les métriques avec :\n"
        f"  python log_metrics.py {content_item_id} --mark-published --views N --leads N ..."
    )

    return {"video": final_video, "video_url": video_url, "content_item_id": content_item_id, **pack}




def _store_creative_quality_shadow(client, content_item_id: str, data: dict,
                                   metrics: dict | None, final_video: str,
                                   expected_version_id: str | None) -> None:
    """Best-effort, explicitly opt-in diagnostics; never affects publishing."""
    if (os.environ.get("CREATIVE_QUALITY_PERSIST_ENABLED") != "true"
            or metrics is None or expected_version_id is None):
        return
    try:
        from . import creative_quality, creative_quality_writer, render_preflight

        existing = client.table("content_items").select(
            "script_version, video_script_version, current_version_id"
        ).eq("id", content_item_id).single().execute().data
        if (not existing or existing.get("current_version_id") != expected_version_id
                or existing.get("video_script_version") is None):
            print("       creative quality: version not ready, report skipped")
            return
        script_report = creative_quality.analyze(
            data,
            retention_report=metrics.get("retention"),
            editorial_report=metrics.get("editorial"),
        )
        render_report = render_preflight.inspect_video(final_video)
        report = creative_quality.combine(script_report, render_report)
        saved = creative_quality_writer.store_report(
            client, content_item_id, report,
            script_version=existing["script_version"],
            video_script_version=existing["video_script_version"],
            current_version_id=existing["current_version_id"],
        )
        print("       creative quality: " + ("saved" if saved else "stale, skipped"))
    except Exception as exc:
        # Never change a successful generation into a failure due to shadow diagnostics.
        print(f"       creative quality unavailable ({type(exc).__name__}): {exc}")

_ANIMATION_HEARTBEAT_S = 60.0


def _run_animated(client, content_item_id: str, script: dict, output_root: str, t_start: float) -> dict:
    """Animated story (experimental, flag-gated, admin beta). The stages and the credit rules live in
    `story_animation.pipeline`; this function only plugs the real services into it. Imports are local so that the
    legacy path never loads this code."""
    import shlex
    from .story_animation import measure as sa_measure, packs as sa_packs, pipeline as sa_pipeline
    from .story_animation import quality as sa_quality, rig_v1 as sa_rig, voices as sa_voices

    godot_bin = os.environ.get("GODOT_BIN", "")
    pack_dir = Path(os.environ.get("STORY_PACK_DIR", "")) if os.environ.get("STORY_PACK_DIR") else None
    renderer = sa_rig.RigV1Renderer(godot_bin, launcher=tuple(shlex.split(os.environ.get("STORY_RENDER_LAUNCHER", ""))))
    work = Path(output_root) / f"animated_{content_item_id}"
    organization_id = events.organization_id_of(client, content_item_id)

    def authorize() -> None:
        try:
            explainer_access.authorize(client, content_item_id)
        except explainer_access.ExplainerAccessDenied as exc:
            raise sa_pipeline.AnimationError("Animation refusée : réservée aux administrateurs de la plateforme") from exc

    def ready() -> list:
        problems = []
        if not godot_bin or not Path(godot_bin).is_file():
            problems.append("GODOT_BIN is not set to an existing file")
        if pack_dir is None:
            problems.append("STORY_PACK_DIR is not set")
        else:
            problems += sa_packs.validate_pack(pack_dir)[:3]
        return problems

    def record_event(name: str, **props) -> None:
        events.record(client, name, content_item_id, organization_id, **props)

    def check_quality(final: Path) -> list:
        report = sa_measure.measure(final)
        return sa_quality.judge_media(report, {"width": sa_rig.WIDTH, "height": sa_rig.HEIGHT, "fps": sa_rig.FPS})

    def publish(final: Path, timeline: dict, review: list) -> dict:
        version_number = None
        try:
            version_number = versions.next_version_number(client, content_item_id)
        except Exception as exc:  # noqa: BLE001 - same fallback as the legacy path
            print(f"       (historique de versions indisponible : {exc})")
        video_url = _publish_video(client, content_item_id, str(final), require_remote=True, version=version_number)
        # review-level findings deliver the clip in the existing `quality_check` state (a human looks before publication,
        # series auto-publication stays blocked); nothing is invented for `quality_score`, which stays null
        fields = {"script": script, "video_url": video_url, "error": None, "generation_step": None,
                  "trim_start": 0, "trim_end": None, "trim_status": None, "original_video_url": None,
                  **sa_quality.review_fields(review)}
        if version_number:
            version_id = versions.record_version(client, content_item_id, version_number, "generation", video_url,
                                                 script=script, duration_seconds=timeline["total"])
            if version_id:
                fields["current_version_id"] = version_id
        repo.update_content_item(client, content_item_id, **fields)
        try:
            repo.mark_generation_completed(client, content_item_id)
        except Exception as exc:  # noqa: BLE001 - the video is delivered; this run just is not counted
            print(f"       (run non comptabilisé pour la politique de crédits : {exc})")
        return {"video_url": video_url, "video": str(final), "content_item_id": content_item_id}

    ports = sa_pipeline.Ports(
        authorize=authorize,
        moderate=moderation.check_script,
        ready=ready,
        estimate=renderer.estimate,
        reserve_credit=lambda: repo.reserve_generation_credit(client, content_item_id),
        refund_credit=lambda: repo.refund_generation_credit(client, content_item_id),
        record_event=record_event,
        synthesize=sa_voices.synthesize_line,
        render=lambda timeline, workdir: renderer.render(timeline, pack_dir, workdir, float(os.environ.get("STORY_RENDER_TIMEOUT_S", "900"))),
        mix=lambda rendered, starts, timeline, out: sa_voices.mix_and_mux(rendered.video_path, starts, timeline["total"], out),
        check_quality=check_quality,
        publish=publish,
        catalog=sa_pipeline.RIG_V1_CATALOG,
        usd_per_1k_chars=float(os.environ.get("ELEVENLABS_USD_PER_1K_CHARS", "0.3")),
    )
    def report_progress(label: str) -> None:
        repo.update_content_item(client, content_item_id, generation_step=label)

    ports.progress = report_progress
    # `repo.reclaim_stale_generating_items` re-queues any item whose `updated_at` is older than 15 minutes. A render is one
    # long subprocess that cannot report progress, so a heartbeat keeps the item alive (best effort, never fails the job).
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(_ANIMATION_HEARTBEAT_S):
            try:
                repo.update_content_item(client, content_item_id)
            except Exception as exc:  # noqa: BLE001
                print(f"       (battement de vie non enregistré : {type(exc).__name__})")

    beat = threading.Thread(target=heartbeat, name="animation-heartbeat", daemon=True)
    beat.start()
    try:
        result = sa_pipeline.run(script, ports, work)
    finally:
        stop.set()
        beat.join(timeout=5)
    print(f"       total génération animée : {time.monotonic() - t_start:.1f}s")
    return result


def run_for_content_item(content_item_id: str, output_root: str = "output") -> dict:
    """Point d'entrée worker.py : génère la vidéo d'un content_item déjà en
    base (créé par le front en status='queued', script déjà construit —
    voir growthos-web `content/actions.ts` `buildScript()`). Le compte existe
    déjà : pas de get_or_create, juste une mise à jour de la ligne existante.
    """
    t_start = time.monotonic()
    client = db.get_service_client()

    raw_script = repo.get_script(client, content_item_id)
    # Animated stories (story.version 2): refused here while STORY_ANIMATION_ENABLED is OFF (nothing is reserved or
    # sent anywhere), otherwise handled by their own pipeline. Every other script continues below, unchanged.
    if story_animation_contract.route_for(raw_script) == "animated":
        return _run_animated(client, content_item_id, raw_script, output_root, t_start)

    data = script_module.normalize_script(raw_script)
    script_module.validate_script(data)
    data.setdefault("aspect_ratio", "9:16")
    data.setdefault("hashtags", [])
    data.setdefault("platform", "tiktok")
    data.setdefault("organization", script_module.DEFAULT_ORGANIZATION)
    data.setdefault("language", "fr")
    data.setdefault("content_goal", "reach")

    # Modération avant la réservation du crédit : un contenu refusé ne coûte rien.
    moderation.check_script(data)
    moderation.check_integrity(data)

    # Explainer (bêta admin) : le worker vérifie l'auteur lui-même, le site seul ne suffit pas (écriture directe en base,
    # épisodes de série mis en file par SQL). Refus avant le crédit : rien à rembourser.
    if visuals.prefers_explainer(data):
        explainer_access.authorize(client, content_item_id)

    # Réservation atomique après validation, mais avant le premier appel
    # payant. Une simple lecture laisserait deux workers consommer le dernier
    # crédit en même temps.
    if not repo.reserve_generation_credit(client, content_item_id):
        raise RuntimeError("crédits épuisés pour ce mois-ci")

    # Événement produit (lot L5) : un essai démarre, crédit réservé.
    organization_id = events.organization_id_of(client, content_item_id)
    events.record(client, "generation_started", content_item_id, organization_id,
                  content_format=data.get("content_format", "standard"),
                  quiz_presentation=quiz_motion.presentation_info(data))

    def report_progress(step_label: str) -> None:
        # Best-effort : un blip réseau vers Supabase ici ne doit jamais faire
        # échouer une génération par ailleurs réussie — juste une ligne en
        # moins dans le suivi affiché sur /content/[id].
        try:
            repo.update_content_item(client, content_item_id, generation_step=step_label)
        except Exception as exc:
            print(f"       (suivi d'avancement non mis à jour : {exc})")

    # Cache d'actifs (lot L1) : après la réservation du crédit, avant les
    # appels payants. Best-effort : s'il est indisponible, rien ne change.
    asset_store.configure(client, content_item_id)
    try:
        final_video, work_dir, metrics = _generate(
            data, output_root, voice_override=None, on_progress=report_progress
        )
    except Exception:
        asset_store.reset()
        try:
            repo.refund_generation_credit(client, content_item_id)
        except Exception as refund_exc:
            # La réservation reste traçable et idempotente : une reprise ne
            # débitera pas une seconde fois le même item.
            print(f"       (remboursement du crédit non appliqué : {refund_exc})")
        raise
    asset_reuse = asset_store.stats()
    asset_store.finish()
    asset_store.reset()
    print(f"       total génération : {time.monotonic() - t_start:.1f}s")
    if metrics is not None and originality.originality_enabled():
        report_progress("Vérification d'originalité")
        account_id = repo.get_content_account_id(client, content_item_id)
        _apply_originality_check(data, metrics, client, account_id, exclude_content_item_id=content_item_id)
    # Version immuable (lot L2) : le fichier vit sous <id>/v<n>.mp4, jamais
    # écrasé. Un échec de lecture du numéro retombe sur l'ancien chemin.
    try:
        version_number = versions.next_version_number(client, content_item_id)
    except Exception as exc:
        print(f"       (historique de versions indisponible : {exc})")
        version_number = None
    try:
        video_url = _publish_video(
            client, content_item_id, final_video, on_progress=report_progress,
            require_remote=True, version=version_number,
        )
    except Exception:
        try:
            repo.refund_generation_credit(client, content_item_id)
        except Exception as refund_exc:
            print(f"       (remboursement du crédit non appliqué : {refund_exc})")
        raise

    final_fields = {
        "status": "video", "script": data, "video_url": video_url,
        "error": None, "generation_step": None,
        # Une régénération complète produit une nouvelle vidéo d'origine : tout
        # rognage précédent (et son archive <id>.original.mp4) est caduc.
        "trim_start": 0, "trim_end": None, "trim_status": None,
        "original_video_url": None,
    }
    final_fields.update(_quality_fields(metrics, final_video))  # peut forcer status='quality_check'
    poster_url = _publish_poster(client, content_item_id, final_video, work_dir)
    if poster_url:
        final_fields["poster_url"] = poster_url
    _publish_thumbnail(client, content_item_id, data, work_dir)  # `data` est déjà dans final_fields["script"]
    _apply_image_report(final_fields, metrics)
    _apply_cost_report(final_fields, metrics)
    quiz_profile = (data.get("generationMetadata") or {}).get("quizProfile")
    cost_report = final_fields.get("generation_cost_report")
    if isinstance(quiz_profile, dict) and isinstance(cost_report, dict):
        quiz_profile["estimatedGenerationCostUsd"] = cost_report.get("totalEstimatedCost")
        quiz_profile["generationCostMissingRates"] = cost_report.get("missingRates", [])
    if asset_reuse and isinstance(final_fields.get("generation_cost_report"), dict):
        # Ce qui a été réutilisé n'a rien coûté : le rapport de coût ne compte
        # déjà que les actifs réellement (re)générés, ceci en donne la raison.
        final_fields["generation_cost_report"]["assetReuse"] = asset_reuse
    if version_number:
        captions_url = versions.upload_captions_safe(
            client, content_item_id, version_number, Path(work_dir) / "captions.srt"
        )
        version_id = versions.record_version(
            client, content_item_id, version_number, "generation", video_url,
            poster_url=poster_url, captions_url=captions_url, script=data,
            duration_seconds=(metrics or {}).get("total_duration"),
        )
        if version_id:
            final_fields["current_version_id"] = version_id
    repo.update_content_item(client, content_item_id, **final_fields)
    _store_creative_quality_shadow(
        client, content_item_id, data, metrics, final_video,
        final_fields.get("current_version_id"),
    )
    cost_report = final_fields.get("generation_cost_report")
    events.record(
        client, "generation_completed", content_item_id, organization_id,
        cost_usd=(cost_report or {}).get("totalEstimatedCost") if isinstance(cost_report, dict) else None,
        duration_s=round(time.monotonic() - t_start, 1),
        version=version_number,
        status=final_fields.get("status"),
        assets_reused=asset_reuse or None,
        quiz_presentation=quiz_motion.presentation_info(data),
    )
    try:
        repo.mark_generation_completed(client, content_item_id)
    except Exception as exc:
        # La vidéo est livrée : ne pas la faire échouer. Conséquence : ce run
        # n'est pas compté, la prochaine régénération sera à nouveau gratuite.
        print(f"       (run non comptabilisé pour la politique de crédits : {exc})")
    pack = publish_pack.write_pack(
        data, final_video, str(work_dir / "publish"), content_item_id
    )
    return {"video": final_video, "video_url": video_url, "content_item_id": content_item_id, **pack}
