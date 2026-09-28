import pandas as pd
import os
import json
import random
from tqdm import tqdm
from fuzzywuzzy import fuzz
from src.transcript_matching import extract_short_transcript, filter_small_transcripts
from scripts.project_config import get_politician2party

if os.path.isdir("../data/"):
    os.chdir("../")

PAIR_BUCKETS = ("highpair", "middlehighpair", "middlelowpair", "lowpair")

def _empty_similarity_dict(keys):
    return {
        key: {bucket: None for bucket in PAIR_BUCKETS}
        for key in keys
    }


def _load_similarity_score(filepath, keys):
    if os.path.isfile(filepath):
        with open(filepath, "r") as f:
            similarities = json.load(f)
    else:
        similarities = _empty_similarity_dict(keys)
    return similarities

def _save_similarity_score(filepath, similarities):
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


def _ensure_datetime(df, col):
    if not pd.api.types.is_datetime64_any_dtype(df[col]):
        df[col] = pd.to_datetime(df[col])
    return df


def _ensure_party_columns(pp_df, news_df):
    """Derive 'party' on pp_df and one boolean column per party on news_df, if not already present."""
    if "party" not in pp_df.columns:
        pp_df["party"] = pp_df["name_standard"].map(get_politician2party())
    for party in pp_df["party"].dropna().unique():
        if party not in news_df.columns:
            news_df[party] = news_df["parties"].fillna("").apply(lambda s, p=party: p in s.split("|"))
    return pp_df, news_df


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


def create_pairs_to_label_same_channel(video_df, channel_type, year):
    output_json = f"data/youtube/transcripts/manual_annotations/pairs_same_channel_{channel_type}_{year}_to_label.json"
    output_xlsx= f"data/youtube/transcripts/manual_annotations/pairs_same_channel_{channel_type}_{year}_to_label.xlsx"

    channels = video_df["channelTitle"].dropna().unique()
    similarities = _load_similarity_score(output_json, channels)

    random.seed(0)

    for channel_title in tqdm(channels):
        pair_dict = similarities[channel_title]
        if _is_complete(pair_dict):
            continue

        channel_subset = video_df.loc[
            (video_df["channelTitle"] == channel_title)
            & (~video_df["transcript"].isna())
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

    _save_similarity_score(output_json, similarities)

    df = _pair_rows(similarities)
    df.to_excel(output_xlsx, index=False)


def create_pairs_to_label_diff_channel(year, all_yt_videos_dfs):
    pp_videos_df = all_yt_videos_dfs[year]['pp']
    news_videos_df = all_yt_videos_dfs[year]['nm']
    output_json = f"data/youtube/transcripts/manual_annotations/pairs_diff_channel_{year}_to_label.json"
    output_xlsx = f"data/youtube/transcripts/manual_annotations/pairs_diff_channel_{year}_to_label.xlsx"

    pp_videos_df, news_videos_df = _ensure_party_columns(pp_videos_df, news_videos_df)
    pp_videos_df = _ensure_datetime(pp_videos_df, "publishedAt")
    news_videos_df = _ensure_datetime(news_videos_df, "publishedAt")

    parties = pp_videos_df["party"].dropna().unique()
    similarities = _load_similarity_score(output_json, parties)

    pp_videos_df = pp_videos_df.dropna(subset=["transcript"])
    news_videos_df = news_videos_df.dropna(subset=["transcript"])
    pp_videos_df = filter_small_transcripts(pp_videos_df)
    news_videos_df = filter_small_transcripts(news_videos_df)

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

    _save_similarity_score(output_json, similarities)

    df = _pair_rows(similarities)
    df.to_excel(output_xlsx, index=False)


def _match_platform_pairs(tt_df, yt_df, group_col, tt_id_col, yt_id_col, output_json, output_xlsx):
    """Fuzzy-match TikTok vs YouTube videos sharing the same group_col value
    (party for pp, channel name_standard for nm), within a 1-week window."""
    groups = sorted(set(tt_df[group_col].dropna().unique()) & set(yt_df[group_col].dropna().unique()))
    similarities = _load_similarity_score(output_json, groups)

    tt_df = filter_small_transcripts(tt_df)
    yt_df = filter_small_transcripts(yt_df)
    yt_df['transcript_short'] = yt_df['transcript'].apply(extract_short_transcript, args=(2000,))
    yt_df = _ensure_datetime(yt_df, "publishedAt")

    for group in groups:
        pair_dict = similarities[group]
        if _is_complete(pair_dict):
            continue

        tt_subset = tt_df.loc[tt_df[group_col] == group]
        yt_subset = yt_df.loc[yt_df[group_col] == group]

        if tt_subset.empty or yt_subset.empty:
            continue

        for i, (_, tt_row) in enumerate(tt_subset.iterrows()):
            if _is_complete(pair_dict):
                break
            if i > 500:
                break

            ref_date = tt_row["create_time"]
            start_date = ref_date - pd.Timedelta(weeks=1)
            end_date = ref_date + pd.Timedelta(weeks=1)

            yt_window = yt_subset.loc[
                (yt_subset["publishedAt"] >= start_date) & (yt_subset["publishedAt"] <= end_date)
                ]

            if yt_window.empty:
                continue

            for _, yt_row in yt_window.iterrows():
                score = fuzz.partial_ratio(tt_row["voice_to_text"], yt_row["transcript_short"])
                thresholds = _diff_channel_thresholds(score)
                _assign_bucket(
                    pair_dict,
                    tt_row[tt_id_col],
                    yt_row[yt_id_col],
                    score,
                    {k: (lambda s, ok=v: ok) for k, v in thresholds.items()},
                )

                if _is_complete(pair_dict):
                    break

    _save_similarity_score(output_json, similarities)

    rows = []
    for group, pairs in similarities.items():
        for pair_type, pair_data in pairs.items():
            if pair_data is None:
                continue
            tt_id, yt_id, score = pair_data
            username_match = tt_df.loc[tt_df[tt_id_col] == tt_id, "username"]
            username = username_match.iloc[0] if not username_match.empty else "user"
            rows.append({
                "group": group,
                "pair_type": pair_type,
                "tiktok_url": f"https://www.tiktok.com/@{username}/video/{tt_id}",
                "youtube_url": f"https://www.youtube.com/watch?v={yt_id}",
                "value": score,
            })
    pd.DataFrame(rows).to_excel(output_xlsx, index=False)


def create_pairs_to_label_diff_platform(year, all_tt_videos_df, all_yt_videos_dfs):
    output_dir = "data/pairs_of_transcripts/manual_annotations"
    os.makedirs(output_dir, exist_ok=True)

    # pp: same party, cross platform
    tt_pp_df = all_tt_videos_df[year]['pp'].copy()
    yt_pp_df = all_yt_videos_dfs[year]['pp'].copy()
    tt_pp_df["party"] = tt_pp_df["name_standard"].map(get_politician2party())
    yt_pp_df["party"] = yt_pp_df["name_standard"].map(get_politician2party())
    _match_platform_pairs(
        tt_pp_df, yt_pp_df, group_col="party", tt_id_col="id", yt_id_col="videoId",
        output_json=f"{output_dir}/pairs_pp_{year}_to_label.json",
        output_xlsx=f"{output_dir}/pairs_pp_{year}_to_annotate.xlsx",
    )

    # nm: same channel, cross platform (output kept as "np" to match the existing filename)
    tt_nm_df = all_tt_videos_df[year]['nm'].copy()
    yt_nm_df = all_yt_videos_dfs[year]['nm'].copy()
    _match_platform_pairs(
        tt_nm_df, yt_nm_df, group_col="name_standard", tt_id_col="id", yt_id_col="videoId",
        output_json=f"{output_dir}/pairs_np_{year}_to_label.json",
        output_xlsx=f"{output_dir}/pairs_np_{year}_to_annotate.xlsx",
    )


if __name__ == "__main__":
    youtube_only = False
    youtube_tiktok = True

    yt_nm_2022 = pd.read_json("data/youtube/videos/news_videos_2022.jsonl", lines=True)
    yt_nm_2024 = pd.read_json("data/youtube/videos/news_videos_2024.jsonl", lines=True)
    yt_pp_2022 = pd.read_json("data/youtube/videos/pp_videos_2022.jsonl", lines=True)
    yt_pp_2024 = pd.read_json("data/youtube/videos/pp_videos_2024.jsonl", lines=True)
    YT_DFS = [yt_nm_2022, yt_nm_2024, yt_pp_2022, yt_pp_2024]
    all_yt_videos_dfs = {
        '2022':{'nm': yt_nm_2022, 'pp':yt_pp_2022},
        '2024': {'nm': yt_nm_2024, 'pp': yt_pp_2024 }
    }
    if youtube_only:
        for year in ['2022', '2024']:
            for channel_type in ['nm', 'pp']:
                video_df = all_yt_videos_dfs[year][channel_type]
                create_pairs_to_label_same_channel(video_df, channel_type=channel_type, year=year)

        # DIFF CHANNELS TO BE PUT IN FUNCTION
        for year in ['2022', '2024']:
            create_pairs_to_label_diff_channel(year, all_yt_videos_dfs)

    if youtube_tiktok:
        # ── TikTok ────────────────────────────────────────────────────────────
        tt_nm_2022 = pd.read_json("data/tiktok/videos/news_videos_2022.jsonl", lines=True)
        tt_nm_2024 = pd.read_json("data/tiktok/videos/news_videos_2024.jsonl", lines=True)
        tt_pp_2022 = pd.read_json("data/tiktok/videos/pp_videos_2022.jsonl", lines=True)
        tt_pp_2024 = pd.read_json("data/tiktok/videos/pp_videos_2024.jsonl", lines=True)
        TT_DFS = [tt_nm_2022, tt_nm_2024, tt_pp_2022, tt_pp_2024]
        all_tt_videos_df = {
            '2022': {'nm': tt_nm_2022, 'pp': tt_pp_2022},
            '2024': {'nm': tt_nm_2024, 'pp': tt_pp_2024},
        }

        for year in ['2022', '2024']:
            create_pairs_to_label_diff_platform(year, all_tt_videos_df, all_yt_videos_dfs)