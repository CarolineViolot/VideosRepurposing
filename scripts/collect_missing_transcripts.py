import os
import json
import argparse
import datetime
from pathlib import Path


from faster_whisper import WhisperModel
from tqdm import tqdm

if os.path.isdir("../data/"):
    os.chdir("../")
from src.tiktok_videos_downloader import TikTokDownloader
from src.youtube_videos_downloader import YouTubeDownloader
from src.whisper_transcription import video_url, download_video, transcribe_video
from scripts.project_config import CHANNEL_TYPES, YEARS

PLATFORMS = ["youtube", "tiktok"]
DEFAULT_COOKIES = "data/yt_cookies.txt"


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

    with open(video_filepath) as f:
        videos = [json.loads(line) for line in f if line.strip()]

    if platform == "tiktok":
        return [
            (str(row["id"]), row["username"], row["video_duration"])
            for row in videos
            if (row["video_duration"] > 0 and row["video_duration"] < 18000) and not row.get("voice_to_text")
        ]
    if platform == "youtube":
        return [
            (row["videoId"], row["channelId"], row["duration"])
            for row in videos
            if (row["duration"] > 0 and row["duration"] < 18000) and isinstance(row.get("error_transcript"), str)
        ]


def load_done_video_ids(transcripts_dir: str, platform: str) -> set:
    # video ids are text on both platforms
    return {f.stem for f in Path(transcripts_dir).glob("*.json")}


def transcribe_missing(platform: str, video_filepath: str, transcripts_dir: str, downloaded_videos_dir: str,
                       keep_videos: bool, cookies_path: str, model: WhisperModel) -> None:
    """Download and transcribe (faster-whisper) the videos of one file that have no transcript yet."""
    os.makedirs(transcripts_dir, exist_ok=True)
    os.makedirs(downloaded_videos_dir, exist_ok=True)

    tiktok_dl = TikTokDownloader(output_dir=downloaded_videos_dir, browser="firefox") if platform == "tiktok" else None
    youtube_dl = YouTubeDownloader(output_dir=downloaded_videos_dir) if platform == "youtube" else None

    pending_videos = load_pending_videos(video_filepath)
    done_ids = load_done_video_ids(transcripts_dir, platform)
    pairs = [p for p in pending_videos if p[0] not in done_ids]
    print(f"{video_filepath}: processing {len(pairs)}/{len(pending_videos)} video(s).\n")
    if not pairs:
        return

    list_durations = list(map(lambda x: x[2], pairs))
    total_duration = sum(list_durations)
    print(f"TOTAL TIME : {str(datetime.timedelta(seconds=total_duration))}s or {total_duration} seconds")

    thrs_min = [5, 15, 30, 60, 120]
    print(f"{len([d for d in list_durations if d < 5*60])} videos < 5 min")
    for i in range(4):
        print(f"{len([d for d in list_durations if ((d >= thrs_min[i]) & (d < thrs_min[i+1])) ] )} videos btw {thrs_min[i]} min and {thrs_min[i+1]} min")
    print(f"{len([d for d in list_durations if d > 120*60])} videos > 120 min")

    results_summary = []
    pbar = tqdm(pairs)
    for video_id, user, duration in pbar:
        pbar.set_postfix({"id": video_id, "duration": f"{int(duration // 60)}m{int(duration % 60)}s"})

        # ── Download (or reuse an existing file) ──────────────────────────────
        matches = list(Path(downloaded_videos_dir).glob(f"{video_id}.*"))
        video_path = matches[0] if matches else download_video(
            video_id, user, platform, tiktok_dl, youtube_dl, cookies_path
        )

        if video_path == "unavailable":
            result = {"text": "[video unavailable]", "language": None, "segments": []}
            save_transcript(video_id, result, transcripts_dir)
            results_summary.append({"id": video_id, "status": "unavailable"})
            continue

        if video_path is None:
            results_summary.append({"id": video_id, "status": "download_failed"})
            continue
        video_path = Path(video_path)  # the TikTok downloader returns a str

        # ── Transcribe ────────────────────────────────────────────────────────
        try:
            result = transcribe_video(video_path, model, language="fr")
        except Exception as exc:
            print(f"  ⚠️   Transcription failed: {exc}\ncheck video at {video_url(video_id, user, platform)}")
            print(f"removing downloaded video at {video_path}")
            video_path.unlink(missing_ok=True)
            results_summary.append({"id": video_id, "status": "transcription_failed"})
            continue

        # ── Save, clean up ────────────────────────────────────────────────────
        save_transcript(video_id, result, transcripts_dir)
        if not keep_videos:
            video_path.unlink(missing_ok=True)

        results_summary.append({
            "id": video_id,
            "status": "ok",
            "text_preview": result["text"][:120].strip(),
        })

    # ── Final summary ─────────────────────────────────────────────────────────
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


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe with faster-whisper the videos still missing a transcript. Without "
                    "--video_filepath, processes every platform/channel_type/year of project_config "
                    "with the standard data/{platform}/videos/ folders.")
    parser.add_argument("--platform", type=str, choices=PLATFORMS, default=None)
    parser.add_argument("--year", type=str, choices=YEARS, default=None)
    parser.add_argument("--channel_type", type=str, choices=CHANNEL_TYPES, default=None)
    parser.add_argument("--keep_videos", type=str, default="yes", choices=["yes", "no"])
    parser.add_argument("--video_filepath", type=str, default=None,
                        help="one specific video file (then --platform, --transcripts_dir and "
                             "--downloaded_videos_dir are required)")
    parser.add_argument("--transcripts_dir", type=str, default=None)
    parser.add_argument("--downloaded_videos_dir", type=str, default=None)
    parser.add_argument("--cookies_path", type=str, default=DEFAULT_COOKIES if os.path.isfile(DEFAULT_COOKIES) else "")
    args = parser.parse_args()

    if args.video_filepath:
        if not (args.platform and args.transcripts_dir and args.downloaded_videos_dir):
            parser.error("--video_filepath needs --platform, --transcripts_dir and --downloaded_videos_dir")
        runs = [(args.platform, args.video_filepath, args.transcripts_dir, args.downloaded_videos_dir)]
    else:
        runs = [
            (platform, f"data/{platform}/videos/{channel_type}_videos_{year}.jsonl",
             args.transcripts_dir or f"data/{platform}/videos/transcripts",
             args.downloaded_videos_dir or f"data/{platform}/videos/downloaded")
            for platform in ([args.platform] if args.platform else PLATFORMS)
            for year in ([args.year] if args.year else YEARS)
            for channel_type in ([args.channel_type] if args.channel_type else CHANNEL_TYPES)
        ]

    model = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=8)
    for platform, video_filepath, transcripts_dir, downloaded_videos_dir in runs:
        transcribe_missing(platform, video_filepath, transcripts_dir, downloaded_videos_dir,
                           keep_videos=args.keep_videos == "yes", cookies_path=args.cookies_path, model=model)


if __name__ == "__main__":
    main()