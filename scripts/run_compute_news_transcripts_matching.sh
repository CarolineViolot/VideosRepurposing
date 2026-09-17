#!/bin/bash -l

python compute_distances_w_preprocessing.py \
  --input_filename 'data/transcripts/pairs_same_channel_news.csv' \
  --output_filename 'data/transcripts/pairs_same_channel_news_labeled.csv' \
  --strip_accents 0 \
  --lowercase 0 \
  --remove_brackets 0 \
  --remove_openers 0 \
  --cut_transcripts 2000 \
  --chunksize 100