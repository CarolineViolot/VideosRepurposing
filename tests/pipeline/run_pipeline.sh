#!/bin/bash -l
# Pipeline test: runs the whole pipeline on a small subset
# (Jean-Luc Mélenchon + BFMTV, 5-7 July 2024) and writes everything
# into tests/pipeline/data/ instead of data/.
#
# Usage (from anywhere): bash tests/pipeline/run_pipeline.sh
# To re-run only some steps, put a # in front of the steps already done.
#
# Needs the .env file at the repo root (YOUTUBE_API_KEY, TIKTOK_CLIENT_KEY,
# TIKTOK_CLIENT_SECRET) and ffmpeg.

# stop at the first step that fails
set -e

# go to tests/pipeline/: the scripts' "data/..." paths then point to tests/pipeline/data/
cd "$(dirname "$0")"

# let Python find src/ and scripts/ of the repo (two folders up)
export PYTHONPATH="../.."

# Python then finds two scripts/ folders: tests/pipeline/scripts/ (only project_config.py,
# with the test channels and dates) and the repo's scripts/ (all the other scripts).
# It uses tests/pipeline/scripts/project_config.py because it looks in the current folder first.

# 0. create tests/pipeline/data/ (from scratch) with the test channels
python init_run.py --reset

# 1. channels
python -m scripts.collect_youtube_channels
python -m scripts.collect_tiktok_channels

# 2. videos in the time window
python -m scripts.collect_youtube_videos
python -m scripts.collect_tiktok_videos

# 3. clean the video and channel files
python -m scripts.prepare_videos
python -m scripts.prepare_channels

# 4. transcripts: YouTube auto-generated ones, then faster-whisper for the videos
#    still missing one (YouTube and TikTok), then merge them into the video files
python -m scripts.run_transcripts_collection
python -m scripts.collect_missing_transcripts --keep_videos no
python -m scripts.add_missing_transcripts

# 4b. move the videos the APIs no longer return to unavailable_videos.jsonl
python -m scripts.check_video_availability

# 5. politicians and parties mentioned in the news videos (NER)
python -m scripts.detect_politicians_and_parties_in_videos

# 6. candidate pairs of videos, then their distances
python -m scripts.create_all_vid_pairs
python -m scripts.compute_distances_w_preprocessing

# 7. classify the pairs with data/model.pkl and build the graphs
python -m scripts.classify_and_build_graphs

# 8. compare the results with the real data/ folder
python compare_run.py
