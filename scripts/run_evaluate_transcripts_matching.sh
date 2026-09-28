#!/bin/bash -l
# Computes fuzzy ratios on the labeled pairs under each preprocessing/cut variant,
# writing data/youtube/transcripts/evaluate/labeled_pairs_all_<variant>.csv
# (compared in notebooks/03_matching_preprocessing_evaluation.ipynb).
# Usage: bash scripts/run_evaluate_transcripts_matching.sh

cd "$(dirname "$0")/.."

evaluate() {
  python -m scripts.compute_distances_w_preprocessing \
    --input_filename 'data/youtube/transcripts/manual_annotations/labeled_pairs_all.csv' \
    --output_filename 'data/youtube/transcripts/evaluate/labeled_pairs_all.csv' \
    --test 1 "$@"
}

# preprocessing variants (no cut)
evaluate --strip_accents 0 --lowercase 0 --remove_brackets 0 --remove_openers 0 --cut_transcripts 0
evaluate --strip_accents 1 --lowercase 0 --remove_brackets 0 --remove_openers 0 --cut_transcripts 0
evaluate --strip_accents 1 --lowercase 1 --remove_brackets 0 --remove_openers 0 --cut_transcripts 0
evaluate --strip_accents 1 --lowercase 1 --remove_brackets 1 --remove_openers 0 --cut_transcripts 0
evaluate --strip_accents 1 --lowercase 1 --remove_brackets 1 --remove_openers 1 --cut_transcripts 0

# cut variants (no preprocessing)
for cut in 2000 5000 10000 15000 20000; do
  evaluate --strip_accents 0 --lowercase 0 --remove_brackets 0 --remove_openers 0 --cut_transcripts "$cut"
done
