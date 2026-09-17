import pandas as pd
import argparse
import os
import logging
import sys
from src.transcript_matching import add_distances
if os.path.isdir("../data/"):
    os.chdir("../")

logger = logging.getLogger(__name__)

# Remove all handlers associated with the root logger object.
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(filename='logs/transcript_matching.log', level=logging.DEBUG,
                    format='%(asctime)s:%(levelname)s:%(message)s',
                    datefmt='%m-%d-%Y %I:%M:%S')



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
    parser.add_argument('--year', type=str, required=True)
    parser.add_argument('--test', type=bool, required=False, default=False)
    return parser.parse_args()

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


def process_pairs_df(pairs_df, all_transcripts, already_done_pairs, args_dict, len_file=None, chunksize=None, i=None):
    filtered_rows = []

    if args_dict['test']:
        preprocessing_summary = "_" + "_".join([k for k, v in args_dict.items() if v == 1])
        print(preprocessing_summary)
        print(args_dict['output_filename'])
        args_dict['output_filename'] = args_dict['output_filename'].replace('.csv', f'{preprocessing_summary}.csv')
    else:
        preprocessing_summary = ''

    for _, row in pairs_df.iterrows():
        if (row['videoId1'], row['videoId2']) not in already_done_pairs:
            filtered_rows.append(row)
    pairs_df = pd.DataFrame(filtered_rows).reset_index(drop=True)
    if len_file is not None:
        print(f"{i + 1}/{int(len_file / chunksize)} - {len(pairs_df)} pairs_to_be_labeled")
        if len(pairs_df) == 0:
            return pd.DataFrame() , None, args_dict

    pairs_df = pairs_df.merge(all_transcripts, left_on='videoId1', right_on='videoId', how='left').rename(
        columns={'transcript': 'transcript1'})
    pairs_df = pairs_df.merge(all_transcripts, left_on='videoId2', right_on='videoId', how='left').rename(
        columns={'transcript': 'transcript2'})

    pairs_df, preprocessing_summary = add_distances(pairs_df, args_dict, preprocessing_summary)

    return pairs_df, preprocessing_summary, args_dict


def main():
    args = parse_args()
    args_dict = vars(args)
    chunksize = args_dict['chunksize']
    if args_dict['test'] and chunksize > 0:
        raise (ValueError, "there can't be a chunksize in test mode")
    output_filename = args_dict['output_filename']
    print(output_filename)
    print("read already done pairs...")
    already_done_pairs = load_already_done_pairs(args_dict['output_filename'])
    print("done")
    tt_transcripts = pd.concat(
        [pd.read_json(f'data/tiktok/videos/pp_videos_{year}.jsonl', lines=True, dtype={'id': str}),
         pd.read_json(f'data/tiktok/videos/news_videos_{year}.jsonl', lines=True, dtype={'id': str})]
    )[['id','voice_to_text']].rename(columns={'id': 'videoId', 'voice_to_text': 'transcript'})
    yt_transcripts = pd.concat([pd.read_json(f'data/youtube/videos/news_videos_{year}.jsonl', lines=True),
                                pd.read_json(f'data/youtube/videos/pp_videos_{year}.jsonl', lines=True)]
                               )[['videoId', 'transcript']]
    all_transcripts = pd.concat([tt_transcripts, yt_transcripts])
    all_transcripts['videoId'] = all_transcripts['videoId'].astype(str)

    del tt_transcripts, yt_transcripts
    if chunksize == 0:
        pairs_df_all = pd.read_csv(args_dict['input_filename'],dtype={'videoId1': str, 'videoId2': str})
        pairs_df, preprocessing_summary, args_dict = process_pairs_df(pairs_df_all, all_transcripts, already_done_pairs, args_dict)
        if pairs_df:
            pairs_df.to_csv(output_filename, index=False)
    else:
        len_file = len(pd.read_csv(args_dict['input_filename'], usecols=['videoId1']))
        for i, chunk_all in enumerate(pd.read_csv(args_dict['input_filename'], chunksize=chunksize,
                                                  dtype={'videoId1': str, 'videoId2': str})):
            chunk, preprocessing_summary, args_dict = process_pairs_df(
                chunk_all, all_transcripts, already_done_pairs, args_dict, len_file, chunksize, i)
            output_filename = args_dict['output_filename']
            if len(chunk) > 0:
                chunk.to_csv(output_filename, index=False,
                         header=(os.path.isfile(output_filename) == False),
                         mode='a')

if __name__ == "__main__":
    #year = '2022'
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
