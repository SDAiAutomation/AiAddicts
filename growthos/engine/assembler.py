"""Orchestrate one script.json into a finished, ready-to-publish clip."""
import os
from pathlib import Path

from . import captions, db, publish_pack, repo, script as script_module, tts, video


def run(script_path: str, output_root: str = "output") -> dict:
    data = script_module.load_script(script_path)
    slug = script_module.slug(data)
    work_dir = Path(output_root) / slug
    api_key = os.environ.get("ELEVENLABS_API_KEY")

    print(f"[1/6] Script chargé : {data['title']} ({len(data['blocks'])} blocs)")

    audio_paths, timed_blocks = [], []
    for i, block in enumerate(data["blocks"], start=1):
        audio_path = str(work_dir / "audio" / f"block-{i:02d}.mp3")
        print(f"[2/6] Voix off {i}/{len(data['blocks'])}…")
        tts.synthesize(block["text"], data["voice_id"], audio_path, api_key)
        duration = tts.get_duration_seconds(audio_path)
        audio_paths.append(audio_path)
        timed_blocks.append((block["text"], duration))

    print("[3/6] Assemblage audio + sous-titres…")
    full_audio = video.concat_audio(audio_paths, str(work_dir / "audio" / "full.mp3"))
    cues = captions.build_cues(timed_blocks)
    srt_path = captions.write_srt(cues, str(work_dir / "captions.srt"))

    print("[4/6] Rendu vidéo finale…")
    final_video = video.render_final(
        full_audio, srt_path, str(work_dir / "final" / f"{slug}.mp4"),
        aspect_ratio=data["aspect_ratio"],
    )

    print("[5/6] Package de publication…")
    pack = publish_pack.write_pack(data, final_video, str(work_dir / "publish"))

    print("[6/6] Enregistrement dans Supabase…")
    client = db.get_service_client()
    organization_id = repo.get_or_create_organization(client, data["organization"])
    account_id = repo.get_or_create_account(
        client, organization_id, data["platform"], data["account"], data.get("niche")
    )
    content_item_id = repo.create_content_item(
        client, account_id, data["title"], status="video", script=data, video_url=final_video
    )

    print(f"\nTerminé. Vidéo : {final_video}")
    print(f"Caption prête : {pack['caption']}")
    print(f"Checklist : {pack['checklist']}")
    print(f"content_item : {content_item_id}")
    print(
        "Une fois posté manuellement, logge les métriques avec :\n"
        f"  python log_metrics.py {content_item_id} --views N --leads N ..."
    )

    return {"video": final_video, "content_item_id": content_item_id, **pack}
