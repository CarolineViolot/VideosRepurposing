#!/bin/bash -l

#SBATCH --job-name transcript_collect
#SBATCH --error logs/%j.error
#SBATCH --output logs/%j.out

#SBATCH --partition cpu
#SBATCH --cpus-per-task 8
#SBATCH --mem 10G
#SBATCH --time 12:00:00
#SBATCH --export NONE
#SBATCH --mail-type END,FAIL
#SBATCH --mail-user caroline.violot@unil.ch

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
dcsrsoft use 20241118
module load python/3.11.7
module load ffmpeg/6.1.1

WORK_PATH=/work/FAC/HEC/DESI/mhumber6/youtubeshorts/
source $WORK_PATH/pythonenv_new/bin/activate

cd /work/FAC/HEC/DESI/mhumber6/youtubeshorts/VideosRepurposing
export PYTHONPATH="$PWD"

export PATH=/scratch/cviolot/French-Politicians/deno-bin:$PATH

python scripts/collect_missing_transcripts.py \
  --platform "youtube" \
  --year "2022" \
  --channel_type "news" \
  --keep_videos "no" \
  --video_filepath "/scratch/cviolot/French-Politicians/youtube/news_videos_2022.jsonl" \
  --downloaded_videos_dir '/scratch/cviolot/French-Politicians/videos' \
  --transcripts_dir '/scratch/cviolot/French-Politicians/transcripts'