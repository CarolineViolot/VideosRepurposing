"""
scripts/check_video_availability.py
----------------------------
Checks which collected videos are still available, using the platforms' APIs
only (YouTube Data API, TikTok Research API): a video the API no longer returns
(deleted, made private, ...) is unavailable. Unavailable videos are moved out of
the video files into data/{platform}/videos/unavailable_videos.jsonl (one file
per platform, all channel types and years), with the extra columns channel_type,
year, unavailable_reason and checked_at. They are not part of the shared data.

API errors stop the script (they are never taken as "unavailable"). As a safety
stop, a file is left unchanged if more than --max_unavailable_share of its
videos come back unavailable, which points to an API problem rather than to
deleted videos.

Usage: python -m scripts.check_video_availability [--platform P] [--year Y] [--channel_type T]
"""
import argparse
import os
from datetime import date, datetime, timedelta

import pandas as pd
from dotenv import load_dotenv

if os.path.isdir("../data/"):
    os.chdir("../")

load_dotenv()

from src.utils import YOUTUBE_API_KEY
from src.youtube_api_collection import get_available_video_ids
from src.tiktok_api_collection import date_windows, fetch_existing_video_ids, get_access_token
from scripts.project_config import CHANNEL_TYPES, YEARS, get_collect_periods

PLATFORMS = ["youtube", "tiktok"]
ID_COL = {"youtube": "videoId", "tiktok": "id"}
REASON = {
    "youtube": "not returned by the YouTube Data API",
    "tiktok": "not returned by the TikTok Research API",
}


def unavailable_youtube_ids(df: pd.DataFrame, year: str) -> set:
    ids = df["videoId"].tolist()
    return set(ids) - get_available_video_ids(ids, api_key=YOUTUBE_API_KEY)


def unavailable_tiktok_ids(df: pd.DataFrame, year: str) -> set:
    """Query each 30-day window of the collection period with the ids created in it."""
    token = get_access_token(os.environ["TIKTOK_CLIENT_KEY"], os.environ["TIKTOK_CLIENT_SECRET"])
    start, end = get_collect_periods()[year]
    last_day = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    created = pd.to_datetime(df["create_time"], utc=True).dt.strftime("%Y%m%d")

    unavailable, checked = set(), set()
    for window_start, window_end in date_windows(start, last_day):
        in_window = df.loc[(created >= window_start) & (created <= window_end), "id"].tolist()
        if in_window:
            checked |= set(in_window)
            unavailable |= set(in_window) - fetch_existing_video_ids(token, in_window, window_start, window_end)
    not_checked = set(df["id"]) - checked
    if not_checked:
        print(f"  {len(not_checked)} video(s) created outside the collection period, not checked: {sorted(not_checked)[:5]}")
    return unavailable


UNAVAILABLE_IDS = {"youtube": unavailable_youtube_ids, "tiktok": unavailable_tiktok_ids}


def check_file(platform: str, channel_type: str, year: str, max_unavailable_share: float) -> None:
    path = f"data/{platform}/videos/{channel_type}_videos_{year}.jsonl"
    id_col = ID_COL[platform]
    df = pd.read_json(path, lines=True, dtype={id_col: str})

    unavailable_ids = UNAVAILABLE_IDS[platform](df, year)
    unavailable = df[df[id_col].isin(unavailable_ids)].copy()
    print(f"{path}: {len(unavailable)}/{len(df)} video(s) unavailable")
    if unavailable.empty:
        return
    if len(unavailable) > max_unavailable_share * len(df):
        print(f"  more than {max_unavailable_share:.0%} unavailable: probably an API problem, file left unchanged")
        return

    unavailable["channel_type"] = channel_type
    unavailable["year"] = year
    unavailable["unavailable_reason"] = REASON[platform]
    unavailable["checked_at"] = date.today().isoformat()

    out_path = f"data/{platform}/videos/unavailable_videos.jsonl"
    if os.path.isfile(out_path):
        unavailable = pd.concat([pd.read_json(out_path, lines=True, dtype={id_col: str}), unavailable])
    unavailable.drop_duplicates(id_col, keep="last").to_json(
        out_path, lines=True, orient="records", force_ascii=False)
    df[~df[id_col].isin(unavailable_ids)].to_json(path, lines=True, orient="records", force_ascii=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", choices=PLATFORMS, default=None, help="default: both")
    parser.add_argument("--year", choices=YEARS, default=None, help="default: all in project_config")
    parser.add_argument("--channel_type", choices=CHANNEL_TYPES, default=None, help="default: all in project_config")
    parser.add_argument("--max_unavailable_share", type=float, default=0.5,
                        help="leave a file unchanged above this share of unavailable videos (default 0.5)")
    args = parser.parse_args()

    for platform in [args.platform] if args.platform else PLATFORMS:
        for year in [args.year] if args.year else YEARS:
            for channel_type in [args.channel_type] if args.channel_type else CHANNEL_TYPES:
                check_file(platform, channel_type, year, args.max_unavailable_share)


if __name__ == "__main__":
    main()