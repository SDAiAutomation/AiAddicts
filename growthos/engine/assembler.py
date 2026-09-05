"""Orchestrate one script.json into a finished, ready-to-publish clip.

Re-running on the same script is cheap: any per-block audio and the final
video already present under output/<slug>/ are reused. Delete that folder to
force a clean rebuild (e.g. after editing the script text).
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import captions, db, publish_pack, repo, script as script_module, storage, tts, video, visuals, voices

# Les appels ElevenLabs sont indépendants par bloc (I/O réseau) : quelques-uns
# en parallèle réduisent le temps total de "somme des blocs" à ~"bloc le plus
# long", sans risquer de se faire rate-limiter par l'API.
_MAX_TTS_WORKERS = 4

# Le programme TikTok Creator Rewards (monétisation) n'accepte que les vidéos
# d'au moins 60s — voir https://www.tiktok.com/creators/creator-rewards-program.
MIN_MONETIZABLE_DURATION_S = 60.0


def _exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _generate(data: dict, output_root: str, voice_override: str | None) -> tuple[str, Path]:
    """Étapes 1-4, communes aux deux points d'entrée : script -> voix off ->
    assemblage -> vidéo finale sous-titrée. Mute `data` (ajoute `voice_id`
    quand une voix est résolue). Retourne (chemin vidéo finale, dossier de travail)."""
    slug = script_module.slug(data)
    work_dir = Path(output_root) / slug
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    pexels_key = os.environ.get("PEXELS_API_KEY")

    n_blocks = len(data["blocks"])
    print(f"[1/5] Script chargé : {data['title']} ({n_blocks} blocs)")

    final_path = work_dir / "final" / f"{slug}.mp4"
    srt_path = work_dir / "captions.srt"

    if _exists_nonempty(final_path) and _exists_nonempty(srt_path):
        # Chemin de re-run le moins cher : la vidéo finale et ses sous-titres
        # sont déjà là, on ne retouche ni ElevenLabs ni ffmpeg. Supprime
        # output/<slug>/ pour forcer une reconstruction (script modifié).
        print("[2-5/5] Vidéo finale + sous-titres déjà présents — réutilisés")
        return str(final_path), work_dir

    voice_id = voices.resolve_voice(data, voice_override)
    data["voice_id"] = voice_id  # la ligne content_items reflète la voix réellement utilisée

    def _synthesize_block(i: int, block: dict) -> tuple[str, float]:
        audio_path = work_dir / "audio" / f"block-{i:02d}.mp3"
        if _exists_nonempty(audio_path):
            print(f"[2/5] Voix off {i}/{n_blocks} — fichier existant réutilisé")
        else:
            print(f"[2/5] Voix off {i}/{n_blocks} (voix {voice_id})…")
            tts.synthesize(block["text"], voice_id, str(audio_path), api_key)
        return str(audio_path), tts.get_duration_seconds(str(audio_path))

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(_MAX_TTS_WORKERS, n_blocks)) as pool:
        # I/O réseau (requests) libère le GIL pendant l'attente : des threads
        # suffisent, pas besoin de multiprocessing pour ce genre de parallélisme.
        results = list(pool.map(_synthesize_block, range(1, n_blocks + 1), data["blocks"]))
    print(f"       voix off terminées en {time.monotonic() - t0:.1f}s")

    audio_paths = [path for path, _duration in results]
    durations = [duration for _path, duration in results]
    timed_blocks = [(block["text"], duration) for block, duration in zip(data["blocks"], durations)]

    total_duration = sum(durations)
    if total_duration < MIN_MONETIZABLE_DURATION_S:
        print(
            f"       ATTENTION : voix off de {total_duration:.1f}s (< {MIN_MONETIZABLE_DURATION_S:.0f}s) — "
            "non éligible au programme TikTok Creator Rewards (monétisation), qui exige 60s minimum. "
            "Allonge le script si la monétisation est visée."
        )

    openai_enabled = bool(os.environ.get("OPENAI_API_KEY"))
    visuals_desc = "Pexels" if pexels_key else "fond uni — pas de PEXELS_API_KEY"
    if openai_enabled:
        visuals_desc += " + OpenAI sur le hook"
    print(f"[3/5] Visuels ({visuals_desc})…")
    t0 = time.monotonic()
    image_paths = visuals.fetch_block_images(
        data["blocks"], data.get("niche"), data["aspect_ratio"], work_dir, pexels_key
    )
    found = sum(1 for p in image_paths if p)
    suffix = f"{found}/{n_blocks} image(s) trouvée(s), le reste en fond uni" if pexels_key else ""
    print(f"       terminé en {time.monotonic() - t0:.1f}s" + (f" — {suffix}" if suffix else ""))

    print("[4/5] Assemblage audio + sous-titres…")
    full_wav = work_dir / "audio" / "full.wav"
    if _exists_nonempty(full_wav):
        print("       piste audio complète existante réutilisée")
        full_audio = str(full_wav)
    else:
        full_audio = video.concat_audio(audio_paths, str(full_wav))
    cues = captions.build_cues(timed_blocks)
    srt_file = captions.write_srt(cues, str(srt_path))

    print(f"[5/5] Rendu vidéo finale ({n_blocks} clip(s))…")
    t0 = time.monotonic()
    final_video = video.render_final(
        full_audio, srt_file, str(final_path), durations,
        image_paths=image_paths, aspect_ratio=data["aspect_ratio"],
    )
    print(f"       vidéo finale rendue en {time.monotonic() - t0:.1f}s")
    return final_video, work_dir


def _publish_video(client, content_item_id: str, local_path: str) -> str:
    """Upload la vidéo rendue vers Supabase Storage (bucket `content-videos`,
    public) pour que `video_url` soit une vraie URL partageable plutôt qu'un
    chemin local à la machine du worker. En cas d'échec (bucket absent,
    réseau…), retombe sur le chemin local plutôt que de faire échouer tout
    le run — la vidéo existe bel et bien, juste pas partageable."""
    try:
        url = storage.upload_video(client, content_item_id, local_path)
        print(f"       vidéo uploadée : {url}")
        return url
    except Exception as exc:
        print(f"       upload Supabase Storage échoué ({exc}) — video_url reste le chemin local")
        return local_path


def run(script_path: str, output_root: str = "output", voice_override: str | None = None) -> dict:
    """Point d'entrée CLI (main.py) : script.json -> nouveau content_item.

    Crée l'organisation/le compte au besoin (get_or_create) — adapté à un
    opérateur qui lance le pipeline à la main, pas à un item déjà en base.
    """
    data = script_module.load_script(script_path)
    final_video, work_dir = _generate(data, output_root, voice_override)

    print("[5/6] Enregistrement dans Supabase…")
    client = db.get_service_client()
    organization_id = repo.get_or_create_organization(client, data["organization"])
    account_id = repo.get_or_create_account(
        client, organization_id, data["platform"], data["account"], data.get("niche")
    )
    content_item_id = repo.create_content_item(
        client, account_id, data["title"], status="video", script=data, video_url=final_video
    )
    video_url = _publish_video(client, content_item_id, final_video)
    if video_url != final_video:
        repo.update_content_item(client, content_item_id, video_url=video_url)

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


def run_for_content_item(content_item_id: str, output_root: str = "output") -> dict:
    """Point d'entrée worker.py : génère la vidéo d'un content_item déjà en
    base (créé par le front en status='queued', script déjà construit —
    voir growthos-web `content/actions.ts` `buildScript()`). Le compte existe
    déjà : pas de get_or_create, juste une mise à jour de la ligne existante.
    """
    t_start = time.monotonic()
    client = db.get_service_client()
    data = repo.get_script(client, content_item_id)
    script_module.validate_script(data)
    data.setdefault("aspect_ratio", "9:16")
    data.setdefault("hashtags", [])
    data.setdefault("platform", "tiktok")
    data.setdefault("organization", script_module.DEFAULT_ORGANIZATION)

    final_video, work_dir = _generate(data, output_root, voice_override=None)
    print(f"       total génération : {time.monotonic() - t_start:.1f}s")
    video_url = _publish_video(client, content_item_id, final_video)

    repo.update_content_item(
        client, content_item_id, status="video", script=data, video_url=video_url, error=None
    )

    pack = publish_pack.write_pack(
        data, final_video, str(work_dir / "publish"), content_item_id
    )
    return {"video": final_video, "video_url": video_url, "content_item_id": content_item_id, **pack}
