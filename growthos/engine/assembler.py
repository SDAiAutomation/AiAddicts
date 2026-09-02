"""Orchestrate one script.json into a finished, ready-to-publish clip."""
import os
from pathlib import Path

from . import captions, publish_pack, script as script_module, tts, video


def run(script_path: str, output_root: str = "output") -> dict:
    data = script_module.load_script(script_path)
    slug = script_module.slug(data)
    work_dir = Path(output_root) / slug
    api_key = os.environ.get("ELEVENLABS_API_KEY")

    print(f"[1/5] Script chargé : {data['title']} ({len(data['blocks'])} blocs)")

    audio_paths, timed_blocks = [], []
    for i, block in enumerate(data["blocks"], start=1):
        audio_path = str(work_dir / "audio" / f"block-{i:02d}.mp3")
        print(f"[2/5] Voix off {i}/{len(data['blocks'])}…")
        tts.synthesize(block["text"], data["voice_id"], audio_path, api_key)
        duration = tts.get_duration_seconds(audio_path)
        audio_paths.append(audio_path)
        timed_blocks.append((block["text"], duration))

    print("[3/5] Assemblage audio + sous-titres…")
    full_audio = video.concat_audio(audio_paths, str(work_dir / "audio" / "full.mp3"))
    cues = captions.build_cues(timed_blocks)
    srt_path = captions.write_srt(cues, str(work_dir / "captions.srt"))

    print("[4/5] Rendu vidéo finale…")
    final_video = video.render_final(
        full_audio, srt_path, str(work_dir / "final" / f"{slug}.mp4"),
        aspect_ratio=data["aspect_ratio"],
    )

    print("[5/5] Package de publication…")
    pack = publish_pack.write_pack(data, final_video, str(work_dir / "publish"))

    print(f"\nTerminé. Vidéo : {final_video}")
    print(f"Caption prête : {pack['caption']}")
    print(f"Checklist : {pack['checklist']}")
    print("Pense à logger la publication dans metrics/suivi-hebdo.csv une fois postée.")

    return {"video": final_video, **pack}
