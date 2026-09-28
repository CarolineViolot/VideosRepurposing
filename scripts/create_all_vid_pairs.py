"""
This script creates all the video transcript pairs on which we want to compute distances to later evaluate if they're
coming from the same video or part of video.
Inside YouTube :
- Shorts and RV from same account in YouTube : -> name of the file
- Any pp video with nm videos that feature politicians from the same party of the pp video
Between YouTube and TikTok :
- tiktoks and pp videos from the same party
- tiktoks and nm videos that feature politicians from the same party of the tiktok
"""

import pandas as pd
import os
from src.transcript_matching import filter_small_transcripts
from scripts.project_config import get_politician2party

PAIR_COLUMNS = ["match_group", "videoId1", "videoId2"]
ORDERED_LIST_PARTIES = ['LO', 'NPA', 'PCF', 'LFI', 'EELV', 'PS', 'PRG', 'PP', 'DG', 'RE', 'MoDem', 'UDI', 'HOR', 'DD',
                        'UPR', 'LR', 'DLF', 'RN', 'LP', 'REC', 'autre']

if os.path.isdir("../data/"):
    os.chdir("../")


def build_pairs(left_df, right_df, group_value, left_id="videoId", right_id="videoId"):
    return pd.DataFrame(
        [
            [group_value, left_row[left_id], right_row[right_id]]
            for _, left_row in left_df.iterrows()
            for _, right_row in right_df.iterrows()
        ], columns=PAIR_COLUMNS,
    )

def is_polit_in_ner(ner_results, polit):
    if pd.isna(ner_results):
        return False
    surname = " ".join(polit.split(" ")[1:])
    return surname in str(ner_results)


def is_party_in_ner(parties, party):
    if pd.isna(parties):
        return False
    return party in str(parties)


def create_pairs_same_youtube_channel(transcripts):
    transcripts = filter_small_transcripts(transcripts)

    pairs_list = []
    for channel_title, channel_subset in transcripts.groupby("name_standard"):
        shorts = channel_subset.loc[channel_subset["isShort"]]
        rvs = channel_subset.loc[~channel_subset["isShort"]]
        if shorts.empty or rvs.empty:
            continue
        pairs_list.append(build_pairs(shorts, rvs, channel_title))
    try:
        pairs_df = pd.concat(pairs_list, ignore_index=True)
    except ValueError as e:
        print(len(pairs_list))
        print(pairs_list)
        raise e
    print(len(pairs_df))
    return pairs_df


def create_pairs_youtube_tiktok(yt_transcripts, tt_transcripts, channel_type, party=True):
    """
    """
    if party==True:
        assert channel_type=='pp'
    print(f"{len(tt_transcripts)} tiktok videos")
    print(f"{len(yt_transcripts)} youtube videos")

    tt_transcripts = filter_small_transcripts(tt_transcripts)
    yt_transcripts = filter_small_transcripts(yt_transcripts)

    print(f"{len(tt_transcripts)} tiktok videos, with transcripts longer than 100 characters.")
    print(f"{len(yt_transcripts)} youtube videos, with transcripts longer than 100 characters.")
    if channel_type == 'pp':
        tt_transcripts['party'] = tt_transcripts['name_standard'].apply(lambda x: get_politician2party()[x])
        yt_transcripts['party'] = yt_transcripts['name_standard'].apply(lambda x: get_politician2party()[x])

        print(f"tiktok parties: {tt_transcripts["party"].unique()}")
        print(f"youtube parties: {yt_transcripts["party"].unique()}")

    pairs_list = []
    if party: group_name = "party"
    else : group_name = "name_standard"
    for e in tt_transcripts[group_name].dropna().unique():
        tt_videos = tt_transcripts.loc[tt_transcripts[group_name] == e]
        yt_videos = yt_transcripts.loc[yt_transcripts[group_name] == e]
        print(f"{e}: {len(tt_videos)} tiktok(s), {len(yt_videos)} youtube vid(s)")
        if tt_videos.empty or yt_videos.empty:
            continue
        pairs_list.append(build_pairs(tt_videos, yt_videos, e, left_id="id"))
    pairs_df = pd.concat(pairs_list, ignore_index=True)
    print(len(pairs_df))
    return pairs_df

def create_pairs_pp_with_nm(pp_transcripts, nm_transcripts,
                            pp_id="videoId", nm_id="videoId",
                            by_party=False, party_channels=False):
    """
    party_channels=False: pp side is individual-politician videos (multi-word
        name_standard). by_party toggles NER matching on politician vs party.
    party_channels=True: pp side is PARTY-channel videos (single-word
        name_standard); each is paired with nm videos mentioning any member of
        that party. Forces party-level NER matching. Mutually exclusive with the
        individual paths.
    """
    pp_transcripts = filter_small_transcripts(pp_transcripts).copy()
    nm_transcripts = filter_small_transcripts(nm_transcripts).copy()

    pairs_list = []

    if party_channels:
        # party channels: name_standard IS the party code, no politician2party mapping
        party_pp = pp_transcripts.loc[
            pp_transcripts["name_standard"].apply(
                lambda x: pd.notna(x) and len(str(x).split()) == 1
            )
        ]
        for party in party_pp["name_standard"].dropna().unique():
            nm_videos = nm_transcripts.loc[
                nm_transcripts["parties"].apply(is_party_in_ner, party=party)
            ]
            pp_videos = party_pp.loc[party_pp["name_standard"] == party]
            if nm_videos.empty or pp_videos.empty:
                continue
            pairs_list.append(
                build_pairs(pp_videos, nm_videos, party, left_id=pp_id, right_id=nm_id)
            )

    elif by_party:
        pp_transcripts["party"] = pp_transcripts["name_standard"].apply(
            lambda x: get_politician2party()[x]
        )
        for party in pp_transcripts["party"].dropna().unique():
            if party not in ORDERED_LIST_PARTIES:
                continue
            nm_videos = nm_transcripts.loc[
                nm_transcripts["parties"].apply(is_party_in_ner, party=party)
            ]
            pp_videos = pp_transcripts.loc[pp_transcripts["party"] == party]
            if nm_videos.empty or pp_videos.empty:
                continue
            pairs_list.append(
                build_pairs(pp_videos, nm_videos, party, left_id=pp_id, right_id=nm_id)
            )
    else:
        politicians = [
            name for name in pp_transcripts["name_standard"].dropna().unique()
            if len(name.split()) > 1
        ]
        for polit in politicians:
            nm_videos = nm_transcripts.loc[
                nm_transcripts["PER_clean"].apply(is_polit_in_ner, polit=polit)
            ]
            pp_videos = pp_transcripts.loc[pp_transcripts["name_standard"] == polit]
            if nm_videos.empty or pp_videos.empty:
                continue
            pairs_list.append(
                build_pairs(pp_videos, nm_videos, polit, left_id=pp_id, right_id=nm_id)
            )

    if not pairs_list:
        return pd.DataFrame(columns=PAIR_COLUMNS)
    pairs_df = pd.concat(pairs_list, ignore_index=True)
    print(len(pairs_df))
    return pairs_df


if __name__ == "__main__":
    youtube_only=True
    across_platforms=True
    across_channels = True
    #for year in ["2022", "2024"]:
    for year in ["2024"]:
        print(f"\t year : {year}")
        yt_nm_transcripts = pd.read_json(f'data/youtube/videos/news_videos_{year}.jsonl', lines=True)[
            ['name_standard', 'videoId', 'transcript', "isShort", "PER_clean", "parties"]]
        yt_pp_transcripts = pd.read_json(f'data/youtube/videos/pp_videos_{year}.jsonl', lines=True)[
            ['name_standard', 'videoId', 'transcript', "isShort"]]
        yt_nm_transcripts = yt_nm_transcripts.dropna(subset=["transcript"]).copy()
        yt_pp_transcripts = yt_pp_transcripts.dropna(subset=["transcript"]).copy()
        if youtube_only:
            print("YouTube only")

            print("same channel")
            for transcripts, channel_type in zip([yt_nm_transcripts, yt_pp_transcripts], ["nm", "pp"]):
                pairs_df = create_pairs_same_youtube_channel(transcripts)
                pairs_df.to_csv(
                    f"data/pairs_of_transcripts/pairs_yt_same_channel_{channel_type}_{year}.csv",
                    index=False)

        if across_platforms:
            print("TikTok + YouTube")
            # in __main__, replace the tt_nm load with (only if the columns exist in the file):
            tt_nm_transcripts = pd.read_json(f'data/tiktok/videos/news_videos_{year}.jsonl', lines=True)[
                ['name_standard', 'id', 'voice_to_text', 'PER_clean', 'parties']]
            tt_pp_transcripts = pd.read_json(f'data/tiktok/videos/pp_videos_{year}.jsonl', lines=True)[
                ['name_standard', 'id', 'voice_to_text']]


            print("same channel (TikTok pp vs YouTube pp)")
            tiktok_same_channel_pp_df = create_pairs_youtube_tiktok(yt_pp_transcripts, tt_pp_transcripts,
                                                                    channel_type='pp', party=False)
            tiktok_same_channel_pp_df.to_csv(
                f"data/pairs_of_transcripts/pairs_same_actor_yt_tt_pp_{year}.csv",
                index=False)

            print("same party (TikTok pp vs YouTube pp)")
            tiktok_same_party_df = create_pairs_youtube_tiktok(yt_pp_transcripts, tt_pp_transcripts,
                                                               channel_type='pp', party=True)
            tiktok_same_party_df.to_csv(
                f"data/pairs_of_transcripts/pairs_same_party_yt_tt_{year}.csv",
                index=False)

            print("same channel (TikTok nm vs YouTube nm)")
            tiktok_same_channel_nm_df = create_pairs_youtube_tiktok(yt_nm_transcripts, tt_nm_transcripts,
                                                                    channel_type='nm', party=False)
            tiktok_same_channel_nm_df.to_csv(
                f"data/pairs_of_transcripts/pairs_same_actor_yt_tt_nm_{year}.csv",
                index=False)

        if across_channels:
            # Load tt transcripts
            tt_nm_transcripts = pd.read_json(f'data/tiktok/videos/news_videos_{year}.jsonl', lines=True)[
                ['name_standard', 'id', 'voice_to_text', 'PER_clean', 'parties']]
            tt_pp_transcripts = pd.read_json(f'data/tiktok/videos/pp_videos_{year}.jsonl', lines=True)[
                ['name_standard', 'id', 'voice_to_text']]

            print("across channels")

            # pp YouTube vs nm all
            pairs_pp_yt_nm_yt = create_pairs_pp_with_nm(
                yt_pp_transcripts, yt_nm_transcripts, pp_id="videoId", nm_id="videoId")
            pairs_pp_yt_nm_tt = create_pairs_pp_with_nm(
                yt_pp_transcripts, tt_nm_transcripts, pp_id="videoId", nm_id="id")
            pd.concat([pairs_pp_yt_nm_yt, pairs_pp_yt_nm_tt]).to_csv(
                f"data/pairs_of_transcripts/pairs_diff_channels_yt_pp_all_nm_{year}.csv", index=False)

            # pp TikTok vs nm all
            pairs_pp_tt_nm_yt = create_pairs_pp_with_nm(
                tt_pp_transcripts, yt_nm_transcripts, pp_id="id", nm_id="videoId")
            pairs_pp_tt_nm_tt = create_pairs_pp_with_nm(
                tt_pp_transcripts, tt_nm_transcripts, pp_id="id", nm_id="id")
            pd.concat([pairs_pp_tt_nm_yt, pairs_pp_tt_nm_tt]).to_csv(
                f"data/pairs_of_transcripts/pairs_diff_channels_tt_pp_all_nm_{year}.csv", index=False)

            # party YouTube channels vs nm all
            pairs_party_yt_nm_yt = create_pairs_pp_with_nm(
                yt_pp_transcripts, yt_nm_transcripts, pp_id="videoId", nm_id="videoId", party_channels=True)
            pairs_party_yt_nm_tt = create_pairs_pp_with_nm(
                yt_pp_transcripts, tt_nm_transcripts, pp_id="videoId", nm_id="id", party_channels=True)
            pd.concat([pairs_party_yt_nm_yt, pairs_party_yt_nm_tt]).to_csv(
                f"data/pairs_of_transcripts/pairs_diff_channels_yt_party_all_nm_{year}.csv", index=False)

            # party TikTok channels vs nm all
            pairs_party_tt_nm_yt = create_pairs_pp_with_nm(
                tt_pp_transcripts, yt_nm_transcripts, pp_id="id", nm_id="videoId", party_channels=True)
            pairs_party_tt_nm_tt = create_pairs_pp_with_nm(
                tt_pp_transcripts, tt_nm_transcripts, pp_id="id", nm_id="id", party_channels=True)
            pd.concat([pairs_party_tt_nm_yt, pairs_party_tt_nm_tt]).to_csv(
                f"data/pairs_of_transcripts/pairs_diff_channels_tt_party_all_nm_{year}.csv", index=False)
