"""
scripts/prepare_channels.py
-----------------------------
Standardizes channel info for both platforms (mapping raw channel
names/usernames to standardized names/orientation), and propagates each
channel's standardized name onto its already-collected video files.
"""
import argparse

import pandas as pd

from src.tiktok_api_collection import read_channels_file
from scripts.project_config import (
    YEARS, get_channel_names_dict, get_news_channel_orientation, get_party_orientation,
)


def read_tiktok_channels_df(path: str) -> pd.DataFrame:
    """TikTok channel file (raw collector format or records) as a DataFrame with a username column."""
    return pd.DataFrame.from_dict(read_channels_file(path), orient="index").reset_index().rename(
        columns={"index": "username"})


def standardize_youtube_news_channels() -> pd.DataFrame:
    path = "data/youtube/channels/news_channels.json"
    df = pd.read_json(path)

    df["name_standard"] = df["channelTitle"].apply(lambda x: get_channel_names_dict().get(x, x))
    df["orientation"] = df["name_standard"].map(get_news_channel_orientation())

    df.to_json(path, orient="records", indent=2, force_ascii=False)
    return df


def standardize_youtube_pp_channels() -> pd.DataFrame:
    path = "data/youtube/channels/pp_channels.json"
    df = pd.read_json(path)

    df["name_standard"] = df["channelTitle"].apply(lambda x: get_channel_names_dict().get(x, x))
    df["orientation"] = df["party"].apply(lambda x: get_party_orientation()[x])

    df.to_json(path, orient="records", indent=2, force_ascii=False)
    return df


def standardize_tiktok_news_channels() -> pd.DataFrame:
    path = "data/tiktok/channels/news_channels.json"
    df = read_tiktok_channels_df(path)
    df["name_standard"] = df["username"].map(get_channel_names_dict())
    df["orientation"] = df["name_standard"].map(get_news_channel_orientation())

    df.to_json(path, orient="records", indent=2, force_ascii=False)
    return df


def standardize_tiktok_pp_channels() -> pd.DataFrame:
    path = "data/tiktok/channels/pp_channels.json"
    df = read_tiktok_channels_df(path)
    df["name_standard"] = df["username"].apply(lambda x: get_channel_names_dict().get(x, x))
    df["orientation"] = df["party"].apply(lambda x: get_party_orientation()[x])

    mask = ~df["username"].isin(get_channel_names_dict().keys())
    df.loc[mask, "name_standard"] = df.loc[mask, "display_name"]

    df.to_json(path, orient="records", indent=2, force_ascii=False)
    return df


def _merge_name_standard(video_path: str, channels_df: pd.DataFrame, on: str) -> None:
    videos_df = pd.read_json(video_path, lines=True, dtype={"id": str, "videoId": str})
    if "name_standard" in videos_df.columns:
        videos_df = videos_df.drop(columns=["name_standard"])

    merged = videos_df.merge(channels_df[[on, "name_standard"]], on=on, how="left")
    assert len(merged) == len(videos_df), f"row count changed while merging name_standard for {video_path}"

    missing = merged["name_standard"].isna().sum()
    if missing:
        print(f"{video_path}: {missing} videos have no matching channel for name_standard")

    merged.to_json(video_path, lines=True, orient="records", force_ascii=False)


def propagate_name_standard_to_videos() -> None:
    """Merge each channel's standardized name onto its already-collected video files."""
    yt_news = pd.read_json("data/youtube/channels/news_channels.json")
    yt_pp = pd.read_json("data/youtube/channels/pp_channels.json")
    tt_news = pd.read_json("data/tiktok/channels/news_channels.json")
    tt_pp = pd.read_json("data/tiktok/channels/pp_channels.json")

    for year in YEARS:
        _merge_name_standard(f"data/youtube/videos/news_videos_{year}.jsonl", yt_news, on="channelId")
        _merge_name_standard(f"data/youtube/videos/pp_videos_{year}.jsonl", yt_pp, on="channelId")
        _merge_name_standard(f"data/tiktok/videos/news_videos_{year}.jsonl", tt_news, on="username")
        _merge_name_standard(f"data/tiktok/videos/pp_videos_{year}.jsonl", tt_pp, on="username")


def main():
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    standardize_youtube_news_channels()
    standardize_youtube_pp_channels()
    standardize_tiktok_news_channels()
    standardize_tiktok_pp_channels()
    propagate_name_standard_to_videos()


if __name__ == "__main__":
    main()
