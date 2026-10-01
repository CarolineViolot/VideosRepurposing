"""
tests/pipeline/init_run.py
----------------------------
Creates tests/pipeline/data/, the data folder of the pipeline test:
  - links (read-only use) to the hand-curated inputs of the real data/ folder:
    dict/, model.pkl, best_thr.txt, yt_cookies.txt
  - the channel files the collectors start from (both platforms): the real files'
    rows of the test channels (TEST_CHANNELS in tests/pipeline/scripts/project_config.py),
    with their curated columns (party, channel_type, ...).

Called by run_pipeline.sh. Usage: python init_run.py [--reset]
  --reset  delete tests/pipeline/data/ first (fresh run)
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
REAL_DATA = os.path.join(REPO, "data")
TEST_DATA = os.path.join(HERE, "data")

os.chdir(HERE)
sys.path.append(REPO)

import pandas as pd

import scripts.project_config as config

REFERENCE_LINKS = ["dict", "model.pkl", "best_thr.txt", "yt_cookies.txt"]


def seed_channels(platform: str, channel_type: str) -> None:
    """Copy the real channel file's rows of the test channels (the collectors refresh the API columns)."""
    filename = os.path.join(platform, "channels", f"{channel_type}_channels.json")
    reference = pd.read_json(os.path.join(REAL_DATA, filename))
    seed = reference[reference["name_standard"].isin(config.TEST_CHANNELS[channel_type])]
    seed.to_json(os.path.join(TEST_DATA, filename), orient="records", indent=2, force_ascii=False)
    print(f"{platform} {channel_type}: {seed['name_standard'].tolist()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete tests/pipeline/data/ first")
    args = parser.parse_args()

    # the test copy of project_config must be the one in use, never the real one
    if os.path.dirname(os.path.abspath(config.__file__)) != os.path.join(HERE, "scripts"):
        raise SystemExit(f"scripts.project_config resolves to {config.__file__}, not the test copy")

    if args.reset and os.path.isdir(TEST_DATA):
        shutil.rmtree(TEST_DATA)
        print(f"Deleted {TEST_DATA}")

    for platform in ["youtube", "tiktok"]:
        os.makedirs(os.path.join(TEST_DATA, platform, "channels"), exist_ok=True)
        os.makedirs(os.path.join(TEST_DATA, platform, "videos"), exist_ok=True)
    os.makedirs(os.path.join(TEST_DATA, "pairs_of_transcripts", "classified"), exist_ok=True)

    for name in REFERENCE_LINKS:
        target, link = os.path.join(REAL_DATA, name), os.path.join(TEST_DATA, name)
        if os.path.exists(target) and not os.path.lexists(link):
            os.symlink(target, link)

    for platform in ["youtube", "tiktok"]:
        for channel_type in config.CHANNEL_TYPES:
            seed_channels(platform, channel_type)
    print(f"Initialised {TEST_DATA}")


if __name__ == "__main__":
    main()