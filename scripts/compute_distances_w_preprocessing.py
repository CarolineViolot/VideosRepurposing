"""
scripts/compute_distances_w_preprocessing.py
----------------------------
Computes fuzzy ratios (partial / token-sort / token-set) between the transcripts
of candidate video pairs, after the requested preprocessing.

Two modes:
  - default: input is a pairs csv (videoId1, videoId2); transcripts are looked up
    in the {year} video files, and only ids + ratio columns are appended to
    --output_filename (resumable, pairs already in the output are skipped).
  - --test 1: input is a labeled-pairs csv that already carries transcript1/2
    (e.g. data/youtube/transcripts/manual_annotations/labeled_pairs_all.csv);
    every column is kept and the output file and ratio columns are suffixed with
    the preprocessing applied (read by notebook 03 to compare preprocessings).

Without arguments, runs the 2024 production batch (see __main__); see
scripts/run_*_transcripts_matching.sh for the command-line usage.
"""
import pandas as pd
import argparse
import os
import logging
import sys

if os.path.isdir("../data/"):
    os.chdir("../")

from src.transcript_matching import add_distances

logger = logging.getLogger(__name__)

# Remove all handlers associated with the root logger object.
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(filename='logs/transcript_matching.log', level=logging.DEBUG,
                    format='%(asctime)s:%(levelname)s:%(message)s',
                    datefmt='%m-%d-%Y %I:%M:%S')

PREPROCESSING_FLAGS = ['strip_accents', 'lowercase', 'remove_brackets', 'remove_openers']


def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark various parameters on transcripts matching.")

    parser.add_argument('--strip_accents', type=int, required=False, default=1, help="remove accent")
    parser.add_argument('--lowercase', type=int, required=False, default=1, help="put text in lowercase")
    parser.add_argument('--remove_brackets', type=int, required=False, default=1, help="remove_brackets")
    parser.add_argument('--remove_openers', type=int, required=False, default=0,
                        help="remove openers (bonjour, bonsoir, etc.)")
    parser.add_argument('--cut_transcripts', type=int, required=False, default=0,
                        help="threshold for cutting transcripts, if 0 no cut")
    parser.add_argument('--input_filename', type=str, required=True,
                        help="filename from which to read transcripts pairs")
    parser.add_argument('--output_filename', type=str, required=True, help="filename to save")
    parser.add_argument('--chunksize', type=int, required=False, default=0,
                        help="chunksize for pd.read_csv if necessary")
    parser.add_argument('--year', type=str, required=False, default=None,
                        help="year of the video files to read transcripts from (not needed with --test 1)")
    parser.add_argument('--test', type=int, required=False, default=0,
                        help="1: evaluation mode on labeled pairs that already carry their transcripts")
    args = parser.parse_args()
    if not args.test and args.year is None:
        parser.error("--year is required unless --test 1")
    if args.test and args.chunksize > 0:
        parser.error("there can't be a chunksize in test mode")
    return args


def load_already_done_pairs(filename):
    try:
        done_pairs = pd.read_csv(filename, usecols=['videoId1', 'videoId2'],
                                 dtype={'videoId1': str, 'videoId2': str})
        done_pairs_ = set(zip(done_pairs['videoId1'], done_pairs['videoId2']))
        print(f"{len(done_pairs_)} already done pairs")
        done_pairs_.update(
            set(zip(done_pairs['videoId2'], done_pairs['videoId1'])))
        print(f"{len(done_pairs_)} already done pairs")
        return set(done_pairs_)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        print(f"File {filename} does not exist")
        return set()


def load_all_transcripts(year):
    tt_transcripts = pd.concat(
        [pd.read_json(f'data/tiktok/videos/pp_videos_{year}.jsonl', lines=True, dtype={'id': str}),
         pd.read_json(f'data/tiktok/videos/news_videos_{year}.jsonl', lines=True, dtype={'id': str})]
    )[['id', 'voice_to_text']].rename(columns={'id': 'videoId', 'voice_to_text': 'transcript'})
    yt_transcripts = pd.concat([pd.read_json(f'data/youtube/videos/news_videos_{year}.jsonl', lines=True),
                                pd.read_json(f'data/youtube/videos/pp_videos_{year}.jsonl', lines=True)]
                               )[['videoId', 'transcript']]
    all_transcripts = pd.concat([tt_transcripts, yt_transcripts])
    all_transcripts['videoId'] = all_transcripts['videoId'].astype(str)
    return all_transcripts


def process_pairs_df(pairs_df, all_transcripts, already_done_pairs, args_dict, len_file=None, chunksize=None, i=None):
    filtered_rows = []
    for _, row in pairs_df.iterrows():
        if (row['videoId1'], row['videoId2']) not in already_done_pairs:
            filtered_rows.append(row)
    pairs_df = pd.DataFrame(filtered_rows).reset_index(drop=True)
    if len_file is not None:
        print(f"{i + 1}/{int(len_file / chunksize)} - {len(pairs_df)} pairs_to_be_labeled")
    if len(pairs_df) == 0:
        return pd.DataFrame()

    pairs_df = pairs_df.merge(all_transcripts, left_on='videoId1', right_on='videoId', how='left').rename(
        columns={'transcript': 'transcript1'})
    pairs_df = pairs_df.merge(all_transcripts, left_on='videoId2', right_on='videoId', how='left').rename(
        columns={'transcript': 'transcript2'})

    pairs_df, _ = add_distances(pairs_df, args_dict, preprocessing_summary='')
    return pairs_df


def run_test_mode(args_dict):
    """Evaluation mode: keep all columns, name the output after the preprocessing applied."""
    pairs_df = pd.read_csv(args_dict['input_filename'], dtype={'videoId1': str, 'videoId2': str})
    preprocessing_summary = "_" + "_".join(f for f in PREPROCESSING_FLAGS if args_dict[f] == 1)
    pairs_df, preprocessing_summary = add_distances(pairs_df, args_dict, preprocessing_summary,
                                                    keep_all_columns=True)
    output_filename = args_dict['output_filename'].replace('.csv', f'{preprocessing_summary}.csv')
    os.makedirs(os.path.dirname(output_filename) or '.', exist_ok=True)
    pairs_df.to_csv(output_filename, index=False)
    print(f"Saved -> {output_filename}")


def main():
    args = parse_args()
    args_dict = vars(args)
    if args_dict['test']:
        run_test_mode(args_dict)
        return

    chunksize = args_dict['chunksize']
    output_filename = args_dict['output_filename']
    print(output_filename)
    print("read already done pairs...")
    already_done_pairs = load_already_done_pairs(output_filename)
    print("done")
    all_transcripts = load_all_transcripts(args_dict['year'])

    if chunksize == 0:
        pairs_df_all = pd.read_csv(args_dict['input_filename'], dtype={'videoId1': str, 'videoId2': str})
        pairs_df = process_pairs_df(pairs_df_all, all_transcripts, already_done_pairs, args_dict)
        if len(pairs_df) > 0:
            pairs_df.to_csv(output_filename, index=False,
                            header=(os.path.isfile(output_filename) == False),
                            mode='a')
    else:
        len_file = len(pd.read_csv(args_dict['input_filename'], usecols=['videoId1']))
        for i, chunk_all in enumerate(pd.read_csv(args_dict['input_filename'], chunksize=chunksize,
                                                  dtype={'videoId1': str, 'videoId2': str})):
            chunk = process_pairs_df(chunk_all, all_transcripts, already_done_pairs, args_dict,
                                     len_file, chunksize, i)
            if len(chunk) > 0:
                chunk.to_csv(output_filename, index=False,
                             header=(os.path.isfile(output_filename) == False),
                             mode='a')


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
        sys.exit()

    # no arguments: 2024 production batch
    year = '2024'
    for input_filename in [
        f'data/pairs_of_transcripts/pairs_diff_channels_tt_pp_all_nm_{year}.csv',
        f'data/pairs_of_transcripts/pairs_diff_channels_yt_pp_all_nm_{year}.csv',
        f"data/pairs_of_transcripts/pairs_diff_channels_tt_party_all_nm_{year}.csv",
        f"data/pairs_of_transcripts/pairs_diff_channels_yt_party_all_nm_{year}.csv",
        f'data/pairs_of_transcripts/pairs_same_actor_yt_tt_nm_{year}.csv',
        #f'data/pairs_of_transcripts/pairs_same_actor_yt_tt_pp_{year}.csv',
        f'data/pairs_of_transcripts/pairs_same_party_yt_tt_{year}.csv',
        f'data/pairs_of_transcripts/pairs_yt_same_channel_nm_{year}.csv',
        #f'data/pairs_of_transcripts/pairs_yt_same_channel_pp_{year}.csv'
    ]:
        output_filename = input_filename.replace('.csv', '_w_d.csv')
        sys.argv = ['compute_distances_w_preprocessing.py',
                    '--input_filename', input_filename,
                    '--output_filename', output_filename,
                    '--cut_transcripts', '2000',
                    '--chunksize', '100',
                    '--year', year]
        main()