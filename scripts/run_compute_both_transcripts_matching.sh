#!/bin/bash -l
# Politicians/parties x news pairs (YouTube and TikTok).
# Computes the fuzzy-ratio features used by the matching model for the candidate
# pairs of the given year (default 2024), appending to <pairs>_w_d.csv (resumable).
# Usage: bash scripts/run_compute_both_transcripts_matching.sh [year]

cd "$(dirname "$0")/.."
YEAR=${1:-2024}

for pairs in \
  pairs_diff_channels_yt_pp_all_nm \
  pairs_diff_channels_yt_party_all_nm \
  pairs_diff_channels_tt_pp_all_nm \
  pairs_diff_channels_tt_party_all_nm
do
  python -m scripts.compute_distances_w_preprocessing \
    --input_filename "data/pairs_of_transcripts/${pairs}_${YEAR}.csv" \
    --output_filename "data/pairs_of_transcripts/${pairs}_${YEAR}_w_d.csv" \
    --year "$YEAR" \
    --cut_transcripts 2000 \
    --chunksize 100
done
