#!/bin/bash -l

python collect_missing_transcripts.py \
  --platform "youtube" \
  --year "2022" \
  --channel_type "news" \
  --keep_videos False \
  --video_filepath "/work/FAC/HEC/mhumbert6/youtubeshorts/VideosRepurposing/data/news_videos_2022.jsonl" \
  --downloaded_videos_dir '/scratch/cviolot/French-Politicians/videos' \
  --transcripts_dir '/scratch/cviolot/French-Politicians/transcripts'