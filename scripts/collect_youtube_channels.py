import os
import pandas as pd

from src.utils import YOUTUBE_API_KEY
from src.youtube_api_collection import collect_channel_stats_df

if os.path.isdir("../data/"):
    os.chdir("../")


def main():
    channel_type = "news"
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


if __name__ == "__main__":
    main()
