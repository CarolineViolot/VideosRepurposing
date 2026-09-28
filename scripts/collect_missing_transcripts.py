import os
import sys
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
            (row["id"], row["username"], row["video_duration"])
            for row in videos
            if (row["video_duration"] > 0 and row["video_duration"] < 18000) and not row.get("voice_to_text")
        ]
    if platform == "youtube":
        return [
            (row["videoId"], row["channelId"], row["duration"])
            for row in videos
            if (row["duration"] > 0 and row["duration"] < 18000) and isinstance(row["error_transcript"], str)
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
    parser.add_argument("--keep_videos", type=str, default="yes", choices=["yes", "no"])
    parser.add_argument("--video_filepath", type=str, required=True)
    parser.add_argument("--transcripts_dir", type=str, required=True)
    parser.add_argument("--downloaded_videos_dir", type=str, required=True)
    parser.add_argument("--cookies_path", type=str, default="")

    args = parser.parse_args()

    keep_videos = args.keep_videos == "yes"
    transcripts_dir = args.transcripts_dir
    downloaded_videos_dir = args.downloaded_videos_dir
    cookies_path = args.cookies_path

    tiktok_dl = TikTokDownloader(output_dir=downloaded_videos_dir, browser="firefox") if args.platform == "tiktok" else None
    youtube_dl = YouTubeDownloader(output_dir=downloaded_videos_dir) if args.platform == "youtube" else None

    pending_videos = load_pending_videos(args.video_filepath)
    done_ids = load_done_video_ids(transcripts_dir, args.platform)
    pairs = [p for p in pending_videos if p[0] not in done_ids]
    #pairs.reverse()
    print(f"Processing {len(pairs)}/{len(pending_videos)} video(s).\n")

    model = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=8)

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
            video_id, user, args.platform, tiktok_dl, youtube_dl, cookies_path
        )

        if video_path == "unavailable":
            result = {"text": "[video unavailable]", "language": None, "segments": []}
            save_transcript(video_id, result, transcripts_dir)
            results_summary.append({"id": video_id, "status": "unavailable"})
            continue

        if video_path is None:
            results_summary.append({"id": video_id, "status": "download_failed"})
            continue

        # ── Transcribe ────────────────────────────────────────────────────────
        try:
            result = transcribe_video(video_path, model, language="fr")
        except Exception as exc:
            print(f"  ⚠️   Transcription failed: {exc}\ncheck video at {video_url(video_id, user, args.platform)}")
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


if __name__ == "__main__":
    #platform = "youtube"
    #year = "2022"
    #channel_type = "news"

    #sys.argv = ["collect_missing_transcripts", "--platform", platform, "--year", year,
    #            "--channel_type", "news",
    #            "--video_filepath", f"data/{platform}/videos/{channel_type}_videos_{year}.jsonl",
    #            "--downloaded_videos_dir", f"data/{platform}/videos/downloaded",
    #            "--transcripts_dir", f"data/{platform}/videos/transcripts"]
    main()