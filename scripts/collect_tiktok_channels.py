import argparse
import os
import json
from datetime import datetime

from dotenv import load_dotenv

from src.tiktok_api_collection import get_access_token, fetch_user_info, read_channels_file
from scripts.project_config import CHANNEL_TYPES

if os.path.isdir("../data/"):
    os.chdir("../")

load_dotenv()

CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]


# ── Entry point ───────────────────────────────────────────────────────────────

def collect_channels(channel_type: str, token: str) -> None:
    """Refresh the API info of the accounts already in the channel file, keeping their
    curated fields (party, name_standard, ...). To add an account, add it to the file."""
    output_file = f"data/tiktok/channels/{channel_type}_channels.json"
    results = read_channels_file(output_file)
    usernames = list(results)

    for idx, username in enumerate(usernames, start=1):
        print(f"\n[{idx}/{len(usernames)}] Collecting data for: @{username}")
        user_info = fetch_user_info(username, token)
        user_info["collected_at"] = datetime.date(datetime.now()).strftime(format="%y-%m-%d")
        results[username] = {**results.get(username, {}), **user_info}
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({"total_channels": len(results), "channels": results}, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Refresh the info of the TikTok accounts listed in data/tiktok/channels/{type}_channels.json.")
    parser.add_argument("--channel_type", choices=CHANNEL_TYPES, default=None,
                        help="restrict to one channel type (default: all)")
    args = parser.parse_args()

    token = get_access_token(CLIENT_KEY, CLIENT_SECRET)
    for channel_type in [args.channel_type] if args.channel_type else CHANNEL_TYPES:
        collect_channels(channel_type, token)


if __name__ == "__main__":
    main()