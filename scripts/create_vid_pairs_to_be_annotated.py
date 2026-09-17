import pandas as pd
import os
import json
import random
from tqdm import tqdm
from fuzzywuzzy import fuzz
from src.file_io import create_transcripts_and_videos_by_year
from src.transcript_matching import extract_short_transcript

if os.path.isdir("../data/"):
    os.chdir("../")

PAIR_BUCKETS = ("highpair", "middlehighpair", "middlelowpair", "lowpair")


def _empty_similarity_dict(keys):
    return {
        key: {bucket: None for bucket in PAIR_BUCKETS}
        for key in keys
    }


def _load_similarity_store(filepath, keys):
    if os.path.isfile(filepath):
        with open(filepath, "r") as f:
            similarities = json.load(f)
    else:
        similarities = _empty_similarity_dict(keys)
    return similarities

def _save_similarity_store(filepath, similarities):
    with open(filepath, "w") as f:
        json.dump(similarities, f, indent=2)


def _is_complete(pair_dict):
    return all(pair_dict[bucket] is not None for bucket in PAIR_BUCKETS)


def _assign_bucket(pair_dict, id1, id2, score, thresholds):
    for bucket in PAIR_BUCKETS:
        if pair_dict[bucket] is None and thresholds[bucket](score):
            pair_dict[bucket] = [id1, id2, score]
            break


def _same_channel_thresholds(score):
    return {
        "highpair": score >= 90,
        "middlehighpair": 50 <= score < 90,
        "middlelowpair": 10 <= score < 50,
        "lowpair": score < 10,
    }


def _diff_channel_thresholds(score):
    return {
        "highpair": score >= 80,
        "middlehighpair": 50 <= score < 80,
        "middlelowpair": 10 <= score < 50,
        "lowpair": score < 10,
    }


def _pair_rows(similarities):
    rows = []
    for group_name, pairs in similarities.items():
        for pair_type, pair_data in pairs.items():
            if pair_data is None:
                continue
            rows.append(
                {
                    "group": group_name,
                    "pair_type": pair_type,
                    "id1": pair_data[0],
                    "id2": pair_data[1],
                    "url1": f"https://www.youtube.com/watch?v=/{pair_data[0]}",
                    "url2": f"https://www.youtube.com/watch?v={pair_data[1]}",
                    "value": pair_data[2],
                }
            )
    return pd.DataFrame(rows)


def create_pairs_to_label_same_channel(transcripts, channel_type, year):
    output_json = f"data/youtube/transcripts/manual_annotations/pairs_same_channel_{channel_type}_{year}_to_label.json"
    output_xlsx= f"data/youtube/transcripts/manual_annotations/pairs_same_channel_{channel_type}_{year}_to_label.xlsx"

    channels = transcripts["channel_title"].dropna().unique()
    similarities = _load_similarity_store(output_json, channels)

    random.seed(0)

    for channel_title in tqdm(channels):
        pair_dict = similarities[channel_title]
        if _is_complete(pair_dict):
            continue

        channel_subset = transcripts.loc[
            (transcripts["channelTitle"] == channel_title)
            & (~transcripts["transcript"].isna())
            ].copy()

        rvs = channel_subset.loc[~channel_subset["isShort"]]
        shorts = channel_subset.loc[channel_subset["isShort"]]

        if rvs.empty or shorts.empty:
            continue

        for i, (_, short_row) in enumerate(shorts.iterrows()):
            if _is_complete(pair_dict):
                break
            if i > 100:
                break

            for _, rv_row in rvs.iterrows():
                score = fuzz.partial_ratio(short_row["transcript"], rv_row["transcript"])
                thresholds = _same_channel_thresholds(score)
                _assign_bucket(
                    pair_dict,
                    short_row["videoId"],
                    rv_row["videoId"],
                    score,
                    {k: (lambda s, ok=v: ok) for k, v in thresholds.items()},
                )

                if _is_complete(pair_dict):
                    break

    _save_similarity_store(output_json, similarities)

    df = _pair_rows(similarities)
    df.to_excel(output_xlsx, index=False)


def create_pairs_to_label_diff_channel(year, all_transcripts, all_videos_df):
    pp_videos_df = all_videos_df[year]["pp"].copy()
    news_videos_df = all_videos_df[year]["news"].copy()

    pp_transcripts_df = all_transcripts[year]["pp"]
    news_transcripts_df = all_transcripts[year]["news"]

    output_json = f"data/youtube/transcripts/manual_annotations/pairs_diff_channel_{year}_to_label.json"
    output_xlsx = f"data/youtube/transcripts/manual_annotations/pairs_diff_channel_{year}_to_label.xlsx"

    parties = pp_videos_df["party"].dropna().unique()
    similarities = _load_similarity_store(output_json, parties)

    # necessary in this direction as we need the columns with all parties boolean in news and 'party' column in pp
    if "transcript" not in pp_videos_df.columns:
        pp_videos_df = pp_videos_df.merge(pp_transcripts_df[["videoId", "transcript"]], on='videoId')
    if "transcript" not in news_videos_df.columns:
        news_videos_df = news_videos_df.merge(news_transcripts_df[["videoId", "transcript"]], on='videoId')

    pp_videos_df['transcript_short'] = pp_videos_df['transcript'].apply(extract_short_transcript, args=(2000,))

    for party in parties:
        if not party or party not in news_videos_df.columns:
            continue
        pair_dict = similarities[party]
        if _is_complete(pair_dict):
            continue

        news_videos = news_videos_df.loc[(news_videos_df[party] == True) & (~news_videos_df["transcript"].isna())]
        pp_videos = pp_videos_df.loc[(pp_videos_df["party"] == party) & (~pp_videos_df["transcript_short"].isna())]

        if news_videos.empty or pp_videos.empty:
            continue

        for i, (_, news_row) in enumerate(news_videos.iterrows()):
            if _is_complete(pair_dict):
                break
            if i > 500:
                break

            ref_date = news_row["publishedAt"]
            start_date = ref_date - pd.Timedelta(weeks=1)
            end_date = ref_date + pd.Timedelta(weeks=1)

            pp_subset = pp_videos.loc[
                (pp_videos["publishedAt"] >= start_date)
                & (pp_videos["publishedAt"] <= end_date)
                ]

            if pp_subset.empty:
                continue

            for _, pp_row in pp_subset.iterrows():
                score = fuzz.partial_ratio(
                    news_row["transcript"],
                    pp_row["transcript_short"],
                )
                thresholds = _diff_channel_thresholds(score)
                _assign_bucket(
                    pair_dict,
                    news_row["videoId"],
                    pp_row["videoId"],
                    score,
                    {k: (lambda s, ok=v: ok) for k, v in thresholds.items()},
                )

                if _is_complete(pair_dict):
                    break

    _save_similarity_store(output_json, similarities)

    df = _pair_rows(similarities)
    df.to_excel(output_xlsx, index=False)


def create_pairs_to_label_diff_platform(year):
    labeled_pairs_pp = pd.read_csv(
        f'data/tiktok/transcripts/pairs_of_transcripts/pairs_same_party_{year}_w_d.csv')
    pairs_to_annotate = []
    pairs_to_annotate.append(labeled_pairs_pp[labeled_pairs_pp['fw.partialratio_cut_t1'] < 20].sample(10))
    pairs_to_annotate.append(labeled_pairs_pp[(labeled_pairs_pp['fw.partialratio_cut_t1'] >= 20) &
                                              (labeled_pairs_pp['fw.partialratio_cut_t1'] < 50)].sample(10))
    pairs_to_annotate.append(labeled_pairs_pp[(labeled_pairs_pp['fw.partialratio_cut_t1'] >= 50) &
                                              (labeled_pairs_pp['fw.partialratio_cut_t1'] < 80)].sample(10))
    pairs_to_annotate.append(labeled_pairs_pp[(labeled_pairs_pp['fw.partialratio_cut_t1'] >= 80)].sample(10))
    pairs_to_annotate = pd.concat(pairs_to_annotate)
    pairs_to_annotate['videoId1'] = pairs_to_annotate['videoId1'].apply(lambda x: f"www.tiktok.com/@user/video/{x}")
    pairs_to_annotate['videoId2'] = pairs_to_annotate['videoId2'].apply(lambda x: f"www.youtube.com/watch?v={x}")
    pairs_to_annotate[['videoId1', 'videoId2']].to_excel(
        f'data/tiktok/transcripts/pairs_of_transcripts/pairs_pp_{year}_to_annotate.xlsx')

    labeled_pairs_nm = pd.read_csv(
        f'data/tiktok/transcripts/pairs_of_transcripts/pairs_same_party_{year}_w_d.csv')
    pairs_to_annotate = []
    pairs_to_annotate.append(
        labeled_pairs_nm[labeled_pairs_nm['fw.partialratio_cut_t1'] < 20].sample(10))
    pairs_to_annotate.append(labeled_pairs_nm[(labeled_pairs_nm['fw.partialratio_cut_t1'] >= 20) &
                                              (labeled_pairs_nm['fw.partialratio_cut_t1'] < 50)].sample(
        10))
    pairs_to_annotate.append(labeled_pairs_nm[(labeled_pairs_nm['fw.partialratio_cut_t1'] >= 50) &
                                              (labeled_pairs_nm['fw.partialratio_cut_t1'] < 80)].sample(
        10))
    pairs_to_annotate.append(
        labeled_pairs_nm[(labeled_pairs_nm['fw.partialratio_cut_t1'] >= 80)].sample(10))
    pairs_to_annotate = pd.concat(pairs_to_annotate)
    pairs_to_annotate['videoId1'] = pairs_to_annotate['videoId1'].apply(lambda x: f"www.tiktok.com/@user/video/{x}")
    pairs_to_annotate['videoId2'] = pairs_to_annotate['videoId2'].apply(lambda x: f"www.youtube.com/watch?v={x}")
    pairs_to_annotate[['videoId1', 'videoId2']].to_excel(
        f'data/tiktok/transcripts/pairs_of_transcripts/pairs_np_{year}_to_annotate.xlsx')


if __name__ == "__main__":
    youtube_only = False
    youtube_tiktok = True
    if youtube_only:
        all_transcripts, all_videos_df = create_transcripts_and_videos_by_year()

        for channel_type in ["news", 'pp']:
            for year in ['2022', '2024']:
                create_pairs_to_label_same_channel(
                    all_transcripts[year][channel_type],
                    channel_type=channel_type,
                    year=year,
                )

        # DIFF CHANNELS TO BE PUT IN FUNCTION
        for year in ['2022', '2024']:
            create_pairs_to_label_diff_channel(year, all_transcripts, all_videos_df)

    if youtube_tiktok:
        yt_transcripts, yt_videos_df = create_transcripts_and_videos_by_year(platform="youtube")
        tiktok_transcripts, tiktok_videos_df = create_transcripts_and_videos_by_year(platform='tiktok')
        for year in ['2022', '2024']:
            create_pairs_to_label_diff_platform(year, yt_transcripts, all_videos_df)