import os
import sys
import json
import subprocess
import argparse
import datetime
from pathlib import Path

from faster_whisper import WhisperModel
from torch.optim.optimizer import Args
from tqdm import tqdm

if os.path.isdir("../data/"):
    os.chdir("../")
from src.tiktok_downloader import TikTokDownloader
from src.file_io import read_json_or_jsonl

SKIP_IDS = {"7357731711775460640", 7357731711775460640}


def video_url(video_id: str, user: str, platform: str) -> str:
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{user}/video/{video_id}"
    return f"https://www.youtube.com/watch?v={video_id}"


def download_video(video_id: str, user: str, output_dir: str, platform: str,
                   tiktok_dl: TikTokDownloader | None = None) -> Path | None:
    """Download a video and return its local path, or None on failure."""
    url = video_url(video_id, user, platform)

    if platform == "tiktok":
        return tiktok_dl.download(url)

    # youtube: audio only, via the yt-dlp CLI
    out_template = str(Path(output_dir) / f"{video_id}.%(ext)s")
    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "--format", "bestaudio[ext=m4a]/bestaudio",
        "--output", out_template,
        "--js-runtimes", "node:/opt/homebrew/bin/node",
        "--remote-components", "ejs:github",
        "--quiet",
        url,
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"  ⚠️   Download failed: {exc}\ncheck video at {url}")
        return None
    matches = list(Path(output_dir).glob(f"{video_id}.*"))
    return matches[0] if matches else None


def transcribe_video(video_path: Path, model: WhisperModel, language: str = "fr") -> dict:
    """Run faster-whisper on an audio/video file (ffmpeg handles decoding)."""
    segments, info = model.transcribe(
        str(video_path),
        language=language,
        beam_size=1,
        task="transcribe",
    )
    segments = list(segments)  # consume the generator
    return {
        "text": " ".join(seg.text.strip() for seg in segments),
        "language": info.language,
        "segments": [
            {"id": i, "start": seg.start, "end": seg.end, "text": seg.text.strip()}
            for i, seg in enumerate(segments)
        ],
    }


def save_transcript(video_id: str, result: dict, transcripts_dir: str):
    with open(f"{transcripts_dir}/{video_id}.json", "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def load_pending_videos(video_filepath) -> list[tuple]:
    """Return (video_id, user/channel, duration) for videos missing a transcript source."""
    if "tiktok" in video_filepath:
        platform = "tiktok"
    elif "youtube" in video_filepath:
        platform = "youtube"
    else :
        raise ValueError(f"Could not determine platform from filepath: {video_filepath}")
    #video_filename = video_filepath.split("/")[-1]
    #video_filename, extension = video_filename.split(".")
    #channel_type, _, year = video_filename.split("_")
    videos = read_json_or_jsonl(video_filepath)

    if platform == "tiktok":
        return [
            (row["id"], row["username"], row["video_duration"])
            for row in videos
            if row["video_duration"] > 0 and not row.get("voice_to_text")
        ]
    if platform == "youtube":
        return [
            (row["videoId"], row["channelId"], row["duration"])
            for row in videos
            if row["duration"] > 0 and isinstance(row["error_transcript"], str)
        ]


def load_done_video_ids(transcripts_dir: str, platform: str) -> set:
    ids = (f.stem for f in Path(transcripts_dir).glob("*.json"))
    if platform == "tiktok":
        return {int(i) for i in ids}
    return set(ids)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", type=str, required=True, choices=["tiktok", "youtube"])
    parser.add_argument("--year", type=str, required=True)
    parser.add_argument("--channel_type", type=str, required=True)
    parser.add_argument("--keep_videos", action="store_true", default=True)
    parser.add_arument("--video_filepath", type=str, required=True)
    parser.add_argument("--transcripts_dir", type=str, required=True)
    parser.add_argument("--downloaded_videos_dir", type=str, required=True)
    args = parser.parse_args()

    transcripts_dir = args.transcript_dir
    downloaded_videos_dir = args.downloaded_videos_dir

    tiktok_dl = TikTokDownloader(output_dir=downloaded_videos_dir, browser="firefox") if args.platform == "tiktok" else None

    pending_videos = load_pending_videos(args.video_filepath)
    done_ids = load_done_video_ids(transcripts_dir, args.platform)
    pairs = [p for p in pending_videos if p[0] not in done_ids and p[0] not in SKIP_IDS]
    print(f"Processing {len(pairs)}/{len(pending_videos)} video(s).\n")

    model = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=8)

    list_durations = list(map(lambda x: x[2], pairs))
    total_duration = sum(list_durations)
    print(f"TOTAL TIME : {str(datetime.timedelta(seconds=total_duration))}s or {total_duration} seconds")

    thrs_min = [5, 15, 30, 60, 120]
    print(f"{len([d for d in list_durations if d < 5*60])} videos < 5 min")
    for i in range(4):
        print(f"{len([d for d in list_durations if ((d >= thrs_min[i]) & (d < thrs_min[i+1])) ] )
        } videos btw {thrs_min[i]} min and {thrs_min[i+1]} min")
    print(f"{len([d for d in list_durations if d > 120*60])} videos > 120 min")

    results_summary = []
    pbar = tqdm(pairs)
    for video_id, user, duration in pbar:
        pbar.set_postfix({"id": video_id, "duration": f"{int(duration // 60)}m{int(duration % 60)}s"})

        # ── Download (or reuse an existing file) ──────────
        matches = list(Path(downloaded_videos_dir).glob(f"{video_id}.*"))
        video_path = matches[0] if matches else download_video(
            video_id, user, downloaded_videos_dir, args.platform, tiktok_dl
        )
        if video_path is None:
            results_summary.append({"id": video_id, "status": "download_failed"})
            continue

        # ── Transcribe ────────────────────────────────────
        try:
            result = transcribe_video(video_path, model, language="fr")
        except Exception as exc:
            print(f"  ⚠️   Transcription failed: {exc}\ncheck video at {video_url(video_id, user, args.platform)}")
            print(f"removing downloaded video at {video_path}")
            video_path.unlink(missing_ok=True)
            results_summary.append({"id": video_id, "status": "transcription_failed"})
            continue

        # ── Save, clean up ────────────────────────────────
        save_transcript(video_id, result, transcripts_dir)
        if not args.keep_videos:
            video_path.unlink(missing_ok=True)

        results_summary.append({
            "id": video_id,
            "status": "ok",
            "text_preview": result["text"][:120].strip(),
        })

    # ── Final summary ─────────────────────────────────────
    ok = [r for r in results_summary if r["status"] == "ok"]
    failed = [r for r in results_summary if r["status"] != "ok"]
    print(f"✅  Success: {len(ok)} / {len(results_summary)}")
    if failed:
        print(f"❌  Failed:  {len(failed)}")
        for r in failed:
            print(f"    • {r['id']} ({r['status']})")
    print()
    if ok:
        print("Transcript previews:")
        for r in ok[-10:]:
            print(f"  [{r['id']}] {r['text_preview']} …")


if __name__ == "__main__":
    platform = "youtube"
    year = "2022"
    channel_type = "news"

    #sys.argv = ["collect_missing_transcripts", "--platform", platform, "--year", "2022",
    #            "--channel_type", "news",
    #            "--video_filepath", f"data/{platform}/videos/{channel_type}_videos_{year}.jsonl",
    #            "--downloaded_videos_dir", f"data/{platform}/videos/downloaded",
    #            "--transcripts_dir", f"data/{platform}/videos/transcripts"]
    main()