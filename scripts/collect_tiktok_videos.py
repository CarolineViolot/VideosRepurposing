import argparse
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from src.tiktok_api_collection import (
    get_access_token, fetch_user, load_existing_videos, get_existing_channels, save, read_channels_file,
)
from scripts.project_config import CHANNEL_TYPES, YEARS, get_collect_periods

if os.path.isdir("../data/"):
    os.chdir("../")

load_dotenv()

CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]

collection_periods = get_collect_periods()


# ── Main ──────────────────────────────────────────────────────────────────────

def collect_videos(channel_type: str, year: str, token: str) -> None:
    output_json = f"data/tiktok/videos/{channel_type}_videos_{year}.json"
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    # Load existing data first
    existing_videos = load_existing_videos(output_json=output_json)
    existing_channels = get_existing_channels(existing_videos)

    print(f"Channels already in file: {sorted(existing_channels)}")
    channel_ids = list(read_channels_file(f"data/tiktok/channels/{channel_type}_channels.json"))
    print(channel_ids)

    # Only collect channels not already present
    channels_to_collect = [ch for ch in channel_ids if ch not in existing_channels]

    if not channels_to_collect:
        print("All channels already exist in the file. Nothing to collect.")
        return

    print(f"Channels to collect: {channels_to_collect}")

    start_date, end_date = collection_periods[year]
    # the TikTok API includes end_date; the collection period excludes it
    end_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    new_videos = []

    all_videos = existing_videos

    for username in channels_to_collect:
        try:
            vids = fetch_user(token, username, start_date, end_date)
            print(f"@{username}: {len(vids)} videos collected")
            new_videos.extend(vids)
            all_videos = all_videos + new_videos
            save(all_videos, output_json=output_json)
            new_videos = []
        except Exception as e:
            all_videos = all_videos + new_videos
            save(all_videos, output_json=output_json)
            print(f"@{username} failed: {e}")

    # Merge old + new
    all_videos = all_videos + new_videos
    save(all_videos, output_json=output_json)


def main():
    parser = argparse.ArgumentParser(description="Collect the TikTok accounts' videos in the election window.")
    parser.add_argument("--year", choices=YEARS, default=None, help="restrict to one year (default: all)")
    parser.add_argument("--channel_type", choices=CHANNEL_TYPES, default=None,
                        help="restrict to one channel type (default: all)")
    args = parser.parse_args()

    token = get_access_token(CLIENT_KEY, CLIENT_SECRET)
    for year in [args.year] if args.year else YEARS:
        for channel_type in [args.channel_type] if args.channel_type else CHANNEL_TYPES:
            collect_videos(channel_type, year, token)


if __name__ == "__main__":
    main()