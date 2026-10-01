"""
Add Missing Transcripts
------------------------
Fills in missing transcripts in the main video jsonl files from the
per-video transcript files produced by scripts/collect_missing_transcripts.py
(data/{platform}/videos/transcripts/{video_id}.json), then splits off videos
that turned out to be unavailable into a separate jsonl file.

For each platform/channel_type/year combination it:
  1. loads data/{platform}/videos/{channel_type}_videos_{year}.jsonl
  2. fills rows with a missing transcript from the per-video transcript file,
     tagging those rows' 'generated_by' field as 'fastwhisper' (NA otherwise)
  3. moves rows with transcript == '[video unavailable]' to
     data/{platform}/videos/{channel_type}_videos_not_available_{year}.jsonl
  4. writes the remaining rows back to the original jsonl file
  5. prints an availability summary
"""
import argparse
import json
import os

import pandas as pd

if os.path.isdir("../data/"):
    os.chdir("../")

from scripts.project_config import CHANNEL_TYPES, YEARS

PLATFORMS = ["youtube", "tiktok"]

TRANSCRIPT_LOC = {"youtube": "transcript", "tiktok": "voice_to_text"}
ID_LOC = {"youtube": "videoId", "tiktok": "id"}


def load_transcript(video_id, platform):
    try:
        with open(f"data/{platform}/videos/transcripts/{video_id}.json") as f:
            transcript = json.load(f)
        return transcript["text"]
    except FileNotFoundError:
        return None


def fill_missing_transcripts(platform, channel_type, year):
    path = f"data/{platform}/videos/{channel_type}_videos_{year}.jsonl"
    df = pd.read_json(path, lines=True, dtype={ID_LOC[platform]: str})
    len_df = len(df)

    transcript_loc = TRANSCRIPT_LOC[platform]
    id_loc = ID_LOC[platform]

    if "generated_by" not in df.columns:
        df["generated_by"] = pd.NA

    mask = (df[transcript_loc].isna()) | (df[transcript_loc] == "")
    print(f"{channel_type}_videos_{year}, {len(df[mask])} missing transcripts")

    df.loc[mask, transcript_loc] = df.loc[mask, id_loc].apply(load_transcript, args=(platform,))

    filled_mask = mask & (~df[transcript_loc].isna()) & (df[transcript_loc] != "")
    df.loc[filled_mask, "generated_by"] = "fastwhisper"

    assert len(df) == len_df

    # split off unavailable videos
    unavailable_mask = df[transcript_loc] == "[video unavailable]"
    df_unavailable = df[unavailable_mask]
    df = df[~unavailable_mask]

    print(f"{channel_type}_videos_{year}, {len(df_unavailable)} unavailable videos set aside")

    still_missing = (df[transcript_loc].isna()) | (df[transcript_loc] == "")
    print(f"{channel_type}_videos_{year}, {len(df[still_missing])} missing transcripts")

    df.to_json(path, lines=True, orient="records")
    if len(df_unavailable) > 0:
        df_unavailable.to_json(
            f"data/{platform}/videos/{channel_type}_videos_not_available_{year}.jsonl",
            lines=True, orient="records",
        )


def print_availability_summary(platforms, channel_types, years):
    for platform in platforms:
        print(platform)
        for channel_type in channel_types:
            for year in years:
                path_df = f"data/{platform}/videos/{channel_type}_videos_{year}.jsonl"
                path_unavailable_df = f"data/{platform}/videos/{channel_type}_videos_not_available_{year}.jsonl"
                df = pd.read_json(path_df, lines=True)
                try:
                    df_unavailable = pd.read_json(path_unavailable_df, lines=True)
                    len_unavailable = len(df_unavailable)
                except FileNotFoundError:
                    len_unavailable = 0

                print(f"{channel_type}_videos_{year} : {len(df)}/{len(df) + len_unavailable} available videos")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", type=str, choices=PLATFORMS, default=None,
                         help="restrict to one platform (default: youtube and tiktok)")
    parser.add_argument("--channel_type", type=str, choices=CHANNEL_TYPES, default=None,
                         help="restrict to one channel type (default: all in project_config)")
    parser.add_argument("--year", type=str, choices=YEARS, default=None,
                         help="restrict to one year (default: all in project_config)")
    args = parser.parse_args()

    platforms = [args.platform] if args.platform else PLATFORMS
    channel_types = [args.channel_type] if args.channel_type else CHANNEL_TYPES
    years = [args.year] if args.year else YEARS

    for platform in platforms:
        for channel_type in channel_types:
            for year in years:
                fill_missing_transcripts(platform, channel_type, year)

    print_availability_summary(platforms, channel_types, years)


if __name__ == "__main__":
    main()