#!/bin/bash -l
# Example SLURM job: faster-whisper transcripts for the YouTube news videos of 2024
# still missing one. Replace the <...> placeholders before submitting (sbatch).

#SBATCH --job-name transcript_collect
#SBATCH --error logs/%j.error
#SBATCH --output logs/%j.out

#SBATCH --partition cpu
#SBATCH --cpus-per-task 8
#SBATCH --mem 32G
#SBATCH --time 48:00:00
#SBATCH --export NONE
#SBATCH --mail-type END,FAIL
#SBATCH --mail-user <your-email>

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
dcsrsoft use 20241118
module load python/3.11.7
module load ffmpeg/6.1.1

WORK_PATH=<work-dir>        # contains the Python environment and the repository
SCRATCH_PATH=<scratch-dir>  # large files: video lists, downloads, transcripts, cookies
source $WORK_PATH/pythonenv_new/bin/activate

cd $WORK_PATH/VideosRepurposing
export PYTHONPATH="$PWD"

export PATH=$SCRATCH_PATH/deno/bin:$PATH

python scripts/collect_missing_transcripts.py \
  --platform "youtube" \
  --year "2024" \
  --channel_type "news" \
  --keep_videos "no" \
  --video_filepath "$SCRATCH_PATH/youtube/news_videos_2024.jsonl" \
  --downloaded_videos_dir "$SCRATCH_PATH/videos" \
  --transcripts_dir "$SCRATCH_PATH/transcripts" \
  --cookies_path "$SCRATCH_PATH/youtube/yt_cookies.txt"