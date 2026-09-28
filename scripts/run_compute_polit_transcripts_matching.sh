#!/bin/bash -l
# Politicians/parties' own reposts (YouTube, YouTube x TikTok, same party).
# Computes the fuzzy-ratio features used by the matching model for the candidate
# pairs of the given year (default 2024), appending to <pairs>_w_d.csv (resumable).
# Usage: bash scripts/run_compute_polit_transcripts_matching.sh [year]

cd "$(dirname "$0")/.."
YEAR=${1:-2024}

for pairs in \
  pairs_yt_same_channel_pp \
  pairs_same_actor_yt_tt_pp \
  pairs_same_party_yt_tt
do
  python -m scripts.compute_distances_w_preprocessing \
    --input_filename "data/pairs_of_transcripts/${pairs}_${YEAR}.csv" \
    --output_filename "data/pairs_of_transcripts/${pairs}_${YEAR}_w_d.csv" \
    --year "$YEAR" \
    --cut_transcripts 2000 \
    --chunksize 100
done
