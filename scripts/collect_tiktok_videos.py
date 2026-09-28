import os
import json

from dotenv import load_dotenv

from src.tiktok_api_collection import (
    get_access_token, fetch_user, load_existing_videos, get_existing_channels, save,
)
from scripts.project_config import get_election_periods

if os.path.isdir("../data/"):
    os.chdir("../")

load_dotenv()

CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]

collection_periods = get_election_periods()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    year = "2022"
    channel_type = "news"
    output_json = f"data/tiktok/videos/{channel_type}_videos_{year}.json"
    # Load existing data first
    existing_videos = load_existing_videos(output_json=output_json)
    existing_channels = get_existing_channels(existing_videos)

    print(f"Channels already in file: {sorted(existing_channels)}")
    with open(f"data/tiktok/channels/{channel_type}_channels.json", "r") as f:
        channel_ids = list(json.load(f)['channels'].keys())
        print(channel_ids)

    # Only collect channels not already present
    channels_to_collect = [ch for ch in channel_ids if ch not in existing_channels]

    if not channels_to_collect:
        print("All channels already exist in the file. Nothing to collect.")
        return

    print(f"Channels to collect: {channels_to_collect}")

    token = get_access_token(CLIENT_KEY, CLIENT_SECRET)
    start_date, end_date = collection_periods[year]
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


if __name__ == "__main__":
    main()