import argparse
import os
import pandas as pd

from src.utils import YOUTUBE_API_KEY
from src.youtube_api_collection import ChannelBatchCollector, ShortsLabeller
from scripts.project_config import CHANNEL_TYPES, YEARS, get_collect_periods

if os.path.isdir("../data/"):
    os.chdir("../")

VIDEOS_FOLDER = "data/youtube/videos/"
CHECKPOINT_DIR = "data/youtube/videos/shorts_label_checkpoints/"
N_LABELLING_THREADS = 50


def collect_step(channel_type: str, year: str, strategy: str = "playlist") -> str:
    channels_path = f"data/youtube/channels/{channel_type}_channels.json"
    output_filepath = f"{VIDEOS_FOLDER}{channel_type}_videos_{year}.jsonl"

    channel_ids = pd.read_json(channels_path)["channelId"].dropna().unique().tolist()
    start_date, end_date = get_collect_periods()[year]

    print(f"Collecting {len(channel_ids)} {channel_type} channels for {year} "
          f"({start_date} -> {end_date}), strategy='{strategy}'…")

    collector = ChannelBatchCollector(output_folder=VIDEOS_FOLDER, api_key=YOUTUBE_API_KEY)
    collector.collect(
        channel_ids=channel_ids,
        strategy=strategy,
        published_after=f"{start_date}T00:00:00Z",
        published_before=f"{end_date}T00:00:00Z",
        output_filepath=output_filepath,
    )
    return output_filepath


def labelling_step(raw_path: str) -> None:
    raw_df = pd.read_json(raw_path, lines=True)

    if "isShort" in raw_df.columns and raw_df["isShort"].isin([True, False]).all():
        print(f"Skipping '{raw_path}' — already fully labelled.")
        return

    labeller = ShortsLabeller(checkpoint_dir=CHECKPOINT_DIR, n_threads=N_LABELLING_THREADS)
    print(f"Labelling '{raw_path}'…")
    labeller.label_file(filepath=raw_path)

    labelled_df = labeller.merge_checkpoints(expected_length=len(raw_df))
    labelled_df.to_json(raw_path, lines=True, orient="records", force_ascii=False)
    print(f"Saved labelled output: {raw_path}")


def main():
    parser = argparse.ArgumentParser(description="Collect the channels' videos in the election window and label Shorts.")
    parser.add_argument("--year", choices=YEARS, default=None, help="restrict to one year (default: all)")
    parser.add_argument("--channel_type", choices=CHANNEL_TYPES, default=None,
                        help="restrict to one channel type (default: all)")
    args = parser.parse_args()

    os.makedirs(VIDEOS_FOLDER, exist_ok=True)

    for year in [args.year] if args.year else YEARS:
        for channel_type in [args.channel_type] if args.channel_type else CHANNEL_TYPES:
            raw_path = collect_step(channel_type, year)
            labelling_step(raw_path)


if __name__ == "__main__":
    main()