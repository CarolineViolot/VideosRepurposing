"""
scripts/prepare_videos.py
----------------------------
Post-collection cleanup for video files: converts TikTok's raw collection
output (a JSON array) into jsonl, splits out zero-duration TikTok posts
(photo carousels, not videos), and drops zero-duration YouTube videos
(e.g. unaired premieres).

Run before scripts/prepare_channels.py, which needs the jsonl video files.
Safe to re-run: the TikTok jsonl is only rebuilt when the raw JSON is newer
(a rebuild would drop what later steps added: transcripts, name_standard, NER),
and photos set aside earlier are kept.
"""
import argparse
import json
import os

import pandas as pd

from scripts.project_config import CHANNEL_TYPES, YEARS


def tiktok_json_to_jsonl() -> None:
    """Convert the raw TikTok collection output (a JSON array) into jsonl."""
    for channel_type in CHANNEL_TYPES:
        for year in YEARS:
            raw_path = f"data/tiktok/videos/{channel_type}_videos_{year}.json"
            jsonl_path = f"data/tiktok/videos/{channel_type}_videos_{year}.jsonl"
            if not os.path.isfile(raw_path):
                continue
            if os.path.isfile(jsonl_path) and os.path.getmtime(jsonl_path) >= os.path.getmtime(raw_path):
                print(f"{jsonl_path}: up to date with {raw_path}, not rebuilt")
                continue
            with open(raw_path) as f:
                videos = json.load(f)
            videos_df = pd.DataFrame.from_records(videos)
            videos_df["id"] = videos_df["id"].astype(str)  # ids are text everywhere
            videos_df.to_json(
                jsonl_path, lines=True, orient="records", force_ascii=False
            )


def remove_tiktok_photos() -> None:
    """Split out zero-duration TikTok posts (photo carousels, not videos)."""
    for channel_type in CHANNEL_TYPES:
        for year in YEARS:
            path = f"data/tiktok/videos/{channel_type}_videos_{year}.jsonl"
            df = pd.read_json(path, lines=True, dtype={"id": str})
            duration_col = "video_duration" if "video_duration" in df.columns else "duration"

            videos = df[df[duration_col] > 0]
            photos = df[df[duration_col] == 0]

            print(f"{path}: {len(photos)} photo(s) set aside, {len(videos)} video(s) kept")
            if len(photos):
                photos_path = path.replace("videos_", "photos_")
                if os.path.isfile(photos_path):
                    photos = pd.concat([pd.read_json(photos_path, lines=True, dtype={"id": str}), photos]
                                       ).drop_duplicates("id")
                photos.to_json(photos_path, lines=True, orient="records", force_ascii=False)
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
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    tiktok_json_to_jsonl()
    remove_tiktok_photos()
    remove_zero_duration_youtube_videos()


if __name__ == "__main__":
    main()