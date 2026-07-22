#!/bin/bash -l

#SBATCH --job-name transcript_collect
#SBATCH --error logs/%j.error
#SBATCH --output logs/%j.out

#SBATCH --partition cpu
#SBATCH --cpus-per-task 1
#SBATCH --mem 10G
#SBATCH --time 12:00:00
#SBATCH --export NONE
#SBATCH --mail-type END,FAIL
#SBATCH --mail-user caroline.violot@unil.ch

python collect_missing_transcripts.py \
  --platform "youtube" \
  --year "2022" \
  --channel_type "news" \
  --keep_videos False \
  --video_filepath "/scratch/cviolot/French-Politicians/news_videos_2022.jsonl" \
  --downloaded_videos_dir '/scratch/cviolot/French-Politicians/videos' \
  --transcripts_dir '/scratch/cviolot/French-Politicians/transcripts'