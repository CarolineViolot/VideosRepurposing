"""
scripts/validate_whisper_transcripts.py
----------------------------
Collects faster-whisper transcripts for the test samples used to check that
whisper transcripts agree with the platform-provided ones (TikTok API
voice_to_text, youtube_transcript_api). The comparison itself is done in
notebooks/06_compare that whisper results are ok.ipynb.

Inputs (samples of 2 videos per channel with a platform transcript, created once):
  - data/test_transcript_collection_accuracy/tiktok_test.jsonl
  - data/test_transcript_collection_accuracy/youtube_test.jsonl
Outputs:
  - data/test_transcript_collection_accuracy/downloaded/{video_id}.*
  - data/test_transcript_collection_accuracy/transcripts/{video_id}.json

Videos that already have a downloaded file or a transcript are skipped.
"""
import os
from pathlib import Path

import pandas as pd
from faster_whisper import WhisperModel
from tqdm import tqdm

if os.path.isdir("../data/"):
    os.chdir("../")

from src.tiktok_videos_downloader import TikTokDownloader
from src.youtube_videos_downloader import YouTubeDownloader
from src.whisper_transcription import download_video, transcribe_video
from scripts.collect_missing_transcripts import save_transcript

PLATFORMS = ["tiktok", "youtube"]
TEST_DIR = "data/test_transcript_collection_accuracy"
VIDEOS_DIR = f"{TEST_DIR}/downloaded"
TRANSCRIPTS_DIR = f"{TEST_DIR}/transcripts"
SKIP_IDS = {"7373950727191924001"}


def load_pending(platform: str) -> pd.DataFrame:
    """Sampled videos that don't have a whisper transcript yet."""
    sample = pd.read_json(f"{TEST_DIR}/{platform}_test.jsonl", lines=True, dtype={"video_id": str})
    done_ids = {f.stem for f in Path(TRANSCRIPTS_DIR).glob("*.json")}
    pending = sample[~sample["video_id"].isin(done_ids | SKIP_IDS)]
    print(f"{platform}: {len(pending)}/{len(sample)} video(s) to transcribe")
    return pending


def collect_platform(platform: str, pending: pd.DataFrame, model: WhisperModel) -> None:
    tiktok_dl = TikTokDownloader(output_dir=VIDEOS_DIR, browser="firefox") if platform == "tiktok" else None
    youtube_dl = YouTubeDownloader(output_dir=VIDEOS_DIR) if platform == "youtube" else None

    for _, row in tqdm(pending.iterrows(), total=len(pending)):
        video_id, user = row["video_id"], row["channel"]
        matches = list(Path(VIDEOS_DIR).glob(f"{video_id}.*"))
        video_path = matches[0] if matches else download_video(video_id, user, platform, tiktok_dl, youtube_dl)
        if video_path is None or video_path == "unavailable":
            print(f"  could not download {video_id} ({video_path})")
            continue
        result = transcribe_video(Path(video_path), model, language="fr")
        save_transcript(video_id, result, TRANSCRIPTS_DIR)


def main():
    pending = {platform: load_pending(platform) for platform in PLATFORMS}
    if all(df.empty for df in pending.values()):
        return

    model = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=8)
    for platform, df in pending.items():
        if not df.empty:
            collect_platform(platform, df, model)


if __name__ == "__main__":
    main()