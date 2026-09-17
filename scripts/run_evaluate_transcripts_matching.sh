#!/bin/bash -l

python compute_distances_w_preprocessing.py \
 --input_filename 'data/transcripts/labeled_pairs_all.csv' \
--output_filename 'data/transcripts/evaluate/labeled_pairs_all.csv' \
 --strip_accents 0 \
 --lowercase 0 \
 --remove_brackets 0 \
 --remove_openers 0 \
 --cut_transcripts 0

python compute_distances_w_preprocessing.py \
 --input_filename 'data/transcripts/labeled_pairs_all.csv' \
 --output_filename 'data/transcripts/evaluate/labeled_pairs_all.csv' \
 --strip_accents 1 \
 --lowercase 0 \
 --remove_brackets 0 \
 --remove_openers 0 \
 --cut_transcripts 0

python compute_distances_w_preprocessing.py \
 --input_filename 'data/transcripts/labeled_pairs_all.csv' \
 --output_filename 'data/transcripts/evaluate/labeled_pairs_all.csv' \
 --strip_accents 1 \
 --lowercase 1 \
 --remove_brackets 0 \
 --remove_openers 0 \
 --cut_transcripts 0

python compute_distances_w_preprocessing.py \
 --input_filename 'data/transcripts/labeled_pairs_all.csv' \
 --output_filename 'data/transcripts/evaluate/labeled_pairs_all.csv' \
 --strip_accents 1 \
 --lowercase 1 \
 --remove_brackets 1 \
 --remove_openers 0 \
 --cut_transcripts 0

python compute_distances_w_preprocessing.py \
  --input_filename 'data/transcripts/labeled_pairs_all.csv' \
  --output_filename 'data/transcripts/evaluate/labeled_pairs_all.csv' \
  --lowercase 1 \
  --remove_brackets 1 \
  --remove_openers 1 \
  --cut_transcripts 0

python compute_distances_w_preprocessing.py \
  --input_filename 'data/transcripts/labeled_pairs_all.csv' \
  --output_filename 'data/transcripts/evaluate/labeled_pairs_all.csv' \
  --strip_accents 0 \
  --lowercase 0 \
  --remove_brackets 0 \
  --remove_openers 0 \
  --cut_transcripts 2000

python compute_distances_w_preprocessing.py \
  --input_filename 'data/transcripts/labeled_pairs_all.csv' \
  --output_filename 'data/transcripts/evaluate/labeled_pairs_all.csv' \
  --strip_accents 0 \
  --lowercase 0 \
  --remove_brackets 0 \
  --remove_openers 0 \
  --cut_transcripts 5000

python compute_distances_w_preprocessing.py \
  --input_filename 'data/transcripts/labeled_pairs_all.csv' \
  --output_filename 'data/transcripts/evaluate/labeled_pairs_all.csv' \
  --strip_accents 0 \
  --lowercase 0 \
  --remove_brackets 0 \
  --remove_openers 0 \
  --cut_transcripts 10000

python compute_distances_w_preprocessing.py \
  --input_filename 'data/transcripts/labeled_pairs_all.csv' \
  --output_filename 'data/transcripts/evaluate/labeled_pairs_all.csv' \
  --strip_accents 0 \
  --lowercase 0 \
  --remove_brackets 0 \
  --remove_openers 0 \
  --cut_transcripts 15000

python compute_distances_w_preprocessing.py \
  --input_filename 'data/transcripts/labeled_pairs_all.csv' \
  --output_filename 'data/transcripts/evaluate/labeled_pairs_all.csv' \
  --strip_accents 0 \
  --lowercase 0 \
  --remove_brackets 0 \
  --remove_openers 0 \
  --cut_transcripts 20000
