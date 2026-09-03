"""Orchestrate one script.json into a finished, ready-to-publish clip.

Re-running on the same script is cheap: any per-block audio and the final
video already present under output/<slug>/ are reused. Delete that folder to
force a clean rebuild (e.g. after editing the script text).
"""
import os
from pathlib import Path

from . import captions, db, publish_pack, repo, script as script_module, tts, video, voices


def _exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def run(script_path: str, output_root: str = "output", voice_override: str | None = None) -> dict:
    data = script_module.load_script(script_path)
    slug = script_module.slug(data)
    work_dir = Path(output_root) / slug
    api_key = os.environ.get("ELEVENLABS_API_KEY")

    n_blocks = len(data["blocks"])
    print(f"[1/6] Script chargé : {data['title']} ({n_blocks} blocs)")

    final_path = work_dir / "final" / f"{slug}.mp4"
    srt_path = work_dir / "captions.srt"

    if _exists_nonempty(final_path) and _exists_nonempty(srt_path):
        # Chemin de re-run le moins cher : la vidéo finale et ses sous-titres
        # sont déjà là, on ne retouche ni ElevenLabs ni ffmpeg. Supprime
        # output/<slug>/ pour forcer une reconstruction (script modifié).
        print("[2-4/6] Vidéo finale + sous-titres déjà présents — réutilisés")
        final_video = str(final_path)
    else:
        voice_id = voices.resolve_voice(data, voice_override)
        data["voice_id"] = voice_id  # la ligne content_items reflète la voix réellement utilisée
        audio_paths, timed_blocks = [], []
        for i, block in enumerate(data["blocks"], start=1):
            audio_path = work_dir / "audio" / f"block-{i:02d}.mp3"
            if _exists_nonempty(audio_path):
                print(f"[2/6] Voix off {i}/{n_blocks} — fichier existant réutilisé")
            else:
                print(f"[2/6] Voix off {i}/{n_blocks} (voix {voice_id})…")
                tts.synthesize(block["text"], voice_id, str(audio_path), api_key)
            duration = tts.get_duration_seconds(str(audio_path))
            audio_paths.append(str(audio_path))
            timed_blocks.append((block["text"], duration))

        print("[3/6] Assemblage audio + sous-titres…")
        full_wav = work_dir / "audio" / "full.wav"
        if _exists_nonempty(full_wav):
            print("       piste audio complète existante réutilisée")
            full_audio = str(full_wav)
        else:
            full_audio = video.concat_audio(audio_paths, str(full_wav))
        cues = captions.build_cues(timed_blocks)
        srt_file = captions.write_srt(cues, str(srt_path))

        print("[4/6] Rendu vidéo finale…")
        final_video = video.render_final(
            full_audio, srt_file, str(final_path), aspect_ratio=data["aspect_ratio"],
        )

    print("[5/6] Enregistrement dans Supabase…")
    client = db.get_service_client()
    organization_id = repo.get_or_create_organization(client, data["organization"])
    account_id = repo.get_or_create_account(
        client, organization_id, data["platform"], data["account"], data.get("niche")
    )
    content_item_id = repo.create_content_item(
        client, account_id, data["title"], status="video", script=data, video_url=final_video
    )

    print("[6/6] Package de publication…")
    pack = publish_pack.write_pack(
        data, final_video, str(work_dir / "publish"), content_item_id
    )

    print(f"\nTerminé. Vidéo : {final_video}")
    print(f"Caption prête : {pack['caption']}")
    print(f"Checklist : {pack['checklist']}")
    print(f"content_item : {content_item_id}")
    print(
        "Une fois posté manuellement, logge les métriques avec :\n"
        f"  python log_metrics.py {content_item_id} --mark-published --views N --leads N ..."
    )

    return {"video": final_video, "content_item_id": content_item_id, **pack}
