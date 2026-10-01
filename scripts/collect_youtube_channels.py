import argparse
import os
import pandas as pd

from src.utils import YOUTUBE_API_KEY
from src.youtube_api_collection import collect_channel_stats_df
from scripts.project_config import CHANNEL_TYPES

if os.path.isdir("../data/"):
    os.chdir("../")


def collect_channels(channel_type: str) -> None:
    channels_path = f"data/youtube/channels/{channel_type}_channels.json"

    existing = pd.read_json(channels_path)
    channel_ids = existing["channelId"].dropna().unique().tolist()

    print(f"Refreshing stats for {len(channel_ids)} {channel_type} channels...")
    stats_df = collect_channel_stats_df(channel_ids, api_key=YOUTUBE_API_KEY)

    # keep project-specific columns (orientation, name_standard, channel_type, ...)
    # that aren't part of the raw API response
    extra_cols = [c for c in existing.columns if c not in stats_df.columns and c != "channelId"]
    merged = stats_df.merge(existing[["channelId"] + extra_cols], on="channelId", how="left")

    merged.to_json(channels_path, orient="records", indent=2, force_ascii=False)
    print(f"Saved {len(merged)} channels to {channels_path}")


def main():
    parser = argparse.ArgumentParser(description="Refresh stats of the channels already in the channel files.")
    parser.add_argument("--channel_type", choices=CHANNEL_TYPES, default=None,
                        help="restrict to one channel type (default: all in project_config)")
    args = parser.parse_args()

    for channel_type in [args.channel_type] if args.channel_type else CHANNEL_TYPES:
        collect_channels(channel_type)


if __name__ == "__main__":
    main()
