"""
scripts/prepare_videos.py
----------------------------
Post-collection cleanup for video files: converts TikTok's raw collection
output (a JSON array) into jsonl, splits out zero-duration TikTok posts
(photo carousels, not videos), and drops zero-duration YouTube videos
(e.g. unaired premieres).

Run after scripts/prepare_channels.py, since that's what populates
name_standard on these video files.
"""
import json
import pandas as pd

YEARS = ["2022", "2024"]
CHANNEL_TYPES = ["news", "pp"]


def tiktok_json_to_jsonl() -> None:
    """Convert the raw TikTok collection output (a JSON array) into jsonl."""
    for channel_type in CHANNEL_TYPES:
        for year in YEARS:
            raw_path = f"data/tiktok/videos/{channel_type}_videos_{year}.json"
            jsonl_path = f"data/tiktok/videos/{channel_type}_videos_{year}.jsonl"
            try:
                with open(raw_path) as f:
                    videos = json.load(f)
            except FileNotFoundError:
                continue
            pd.DataFrame.from_records(videos).to_json(
                jsonl_path, lines=True, orient="records", force_ascii=False
            )


def remove_tiktok_photos() -> None:
    """Split out zero-duration TikTok posts (photo carousels, not videos)."""
    for channel_type in CHANNEL_TYPES:
        for year in YEARS:
            path = f"data/tiktok/videos/{channel_type}_videos_{year}.jsonl"
            df = pd.read_json(path, lines=True)
            duration_col = "video_duration" if "video_duration" in df.columns else "duration"

            videos = df[df[duration_col] > 0]
            photos = df[df[duration_col] == 0]

            print(f"{path}: {len(photos)} photo(s) set aside, {len(videos)} video(s) kept")
            photos.to_json(path.replace("videos_", "photos_"), lines=True, orient="records", force_ascii=False)
            videos.to_json(path, lines=True, orient="records", force_ascii=False)


def remove_zero_duration_youtube_videos() -> None:
    """Drop YouTube videos with zero/unresolved duration (e.g. unaired premieres)."""
    for channel_type in CHANNEL_TYPES:
        for year in YEARS:
            path = f"data/youtube/videos/{channel_type}_videos_{year}.jsonl"
            df = pd.read_json(path, lines=True)
            before = len(df)
            df = df[df["duration"] > 0]
            if len(df) != before:
                print(f"{path}: dropped {before - len(df)} zero-duration video(s)")
            df.to_json(path, lines=True, orient="records", force_ascii=False)


def main():
    tiktok_json_to_jsonl()
    remove_tiktok_photos()
    remove_zero_duration_youtube_videos()


if __name__ == "__main__":
    main()