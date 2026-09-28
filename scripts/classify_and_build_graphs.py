"""
scripts/classify_and_build_graphs.py
----------------------------
Classifies the 2024 candidate video pairs (same transcript or not) with the
matching model trained by scripts/train_matching_model.py, then builds one
similarity graph per channel/party: nodes are videos, edges connect pairs
classified as matches (with the delay between the two uploads).

Inputs:
  - data/model.pkl, data/best_thr.txt
  - data/pairs_of_transcripts/*_2024_w_d.csv (pairs with distances)
  - data/{youtube,tiktok}/{videos,channels}/...
Outputs:
  - data/pairs_of_transcripts/classified/*_2024_classified.csv
  - data/networks/pp_only_2024/{name_standard}_gs_pp_only_2024.gv
      own reposts of each politician/party channel (YouTube RV<->Short, YouTube<->TikTok)
  - data/networks/news_only_2024/{name_standard}_gs_news_only_2024.gv
      own reposts of each news channel (YouTube RV<->Short, YouTube<->TikTok)
  - data/networks/diff_2024/{name_standard}_gs_diff_2024.gv
      politician/party videos matched with news videos
  - data/networks/parties_2024/{party}_gs_parties_2024.gv
      reposts among all members of a party

Read by notebooks 07 (upload patterns), 08, 09 and 10.
"""
import os
import pickle

import networkx as nx
import numpy as np
import pandas as pd

if os.path.isdir("../data/"):
    os.chdir("../")

from src.transcript_matching import add_transcript_to_video_pairs, classify_pairs, clean_transcripts
from scripts.project_config import get_politician2party

PLATFORMS = ["youtube", "tiktok"]
CHANNEL_TYPES = ["news", "pp"]
YEARS = ["2022", "2024"]
YEAR = "2024"

MODEL_PATH = "data/model.pkl"
THRESHOLD_PATH = "data/best_thr.txt"
PAIRS_DIR = "data/pairs_of_transcripts"
CLASSIFIED_DIR = f"{PAIRS_DIR}/classified"
NETWORKS_DIR = "data/networks"

PAIRS_FILES = [
    # YouTube own reposts
    "pairs_yt_same_channel_pp_2024",
    "pairs_yt_same_channel_nm_2024",
    # YouTube x TikTok
    "pairs_same_actor_yt_tt_pp_2024",
    "pairs_same_party_yt_tt_2024",
    "pairs_same_actor_yt_tt_nm_2024",
    # politicians/parties x news
    "pairs_diff_channels_yt_pp_all_nm_2024",
    "pairs_diff_channels_yt_party_all_nm_2024",
    "pairs_diff_channels_tt_pp_all_nm_2024",
    "pairs_diff_channels_tt_party_all_nm_2024",
]


# ── Load ──────────────────────────────────────────────────────────────────────

def load_videos() -> pd.DataFrame:
    """All videos (both platforms, types, years) with the columns needed downstream."""
    frames = []
    for platform in PLATFORMS:
        for channel_type in CHANNEL_TYPES:
            for year in YEARS:
                df = pd.read_json(f"data/{platform}/videos/{channel_type}_videos_{year}.jsonl", lines=True)
                if platform == "tiktok":
                    df = df.rename(columns={"id": "videoId", "voice_to_text": "transcript", "create_time": "publishedAt"})
                    df["videoId"] = df["videoId"].apply(str)
                    df["isShort"] = np.nan
                df["publishedAt"] = pd.to_datetime(df["publishedAt"]).dt.tz_localize(None)
                df["platform"] = platform
                frames.append(df[["videoId", "transcript", "name_standard", "publishedAt", "isShort", "platform"]])
    return pd.concat(frames)


def load_transcripts(videos: pd.DataFrame) -> pd.DataFrame:
    transcripts = videos[["videoId", "transcript"]].dropna(subset="transcript").copy()
    transcripts["transcript_clean"] = transcripts["transcript"].apply(
        clean_transcripts,
        strip_accents=True, lowercase=True, remove_brackets=True, remove_openers=False)
    return transcripts


def load_standard_names(platform: str, channel_type: str) -> list:
    return list(pd.read_json(f"data/{platform}/channels/{channel_type}_channels.json").name_standard)


# ── Classify ──────────────────────────────────────────────────────────────────

def get_classified_pairs(filename, transcripts, model, best_thr):
    video_pairs = pd.read_csv(filename, dtype={"videoId1": str, "videoId2": str})
    video_pairs = add_transcript_to_video_pairs(video_pairs, transcripts, filename)
    return classify_pairs(video_pairs, model, best_thr)


def classify_all_pairs(transcripts, model, best_thr, classified_dir) -> dict:
    pairs = {}
    for name in PAIRS_FILES:
        pairs[name] = get_classified_pairs(f"{PAIRS_DIR}/{name}_w_d.csv", transcripts, model, best_thr)
        pairs[name].to_csv(f"{classified_dir}/{name}_classified.csv", index=False)
        print(f"{name}: {int(pairs[name].predicted_label.sum())}/{len(pairs[name])} pairs classified as matches")
    return pairs


def add_name_standard_to_transcript_pairs(pairs_df, videoid2standard_name, politician2party,
                                          same_channel=True, w_tt=False):
    init_length = len(pairs_df)
    if same_channel:
        assert not w_tt, "same_channel and w_tt (with tiktok) can't be true at the same time"
        pairs_df["name_standard"] = pairs_df["videoId1"].map(videoid2standard_name)
        pairs_df["party"] = pairs_df["name_standard"].apply(lambda x: politician2party.get(x, None))
        if pairs_df["party"].isna().all():
            pairs_df = pairs_df.drop(columns=["party"])
    elif w_tt:
        pairs_df["tt_name_standard"] = pairs_df["videoId1"].map(videoid2standard_name)
        pairs_df["yt_name_standard"] = pairs_df["videoId2"].map(videoid2standard_name)
        pairs_df["party"] = pairs_df["tt_name_standard"].apply(lambda x: politician2party.get(x, None))
        # all party NA means these are news pairs
        if pairs_df["party"].isna().all():
            pairs_df = pairs_df.drop(columns=["party"])
    else:
        pairs_df["name_standard1"] = pairs_df["videoId1"].map(videoid2standard_name)
        pairs_df["name_standard2"] = pairs_df["videoId2"].map(videoid2standard_name)
    assert len(pairs_df) == init_length
    return pairs_df


# ── Graphs ────────────────────────────────────────────────────────────────────

def add_match_edges(g, pairs_df, videoId2publishedAt):
    """Add an edge for every pair classified as a match, with the delay between both uploads."""
    matches = pairs_df[pairs_df.predicted_label == 1]
    for v1, v2 in zip(matches.videoId1, matches.videoId2):
        publishedAt1 = videoId2publishedAt[v1]
        publishedAt2 = videoId2publishedAt[v2]
        elapsed_time = np.absolute(publishedAt2 - publishedAt1)
        first_node = v1 if publishedAt1 < publishedAt2 else v2
        g.add_edge(v1, v2, elapsed_time=elapsed_time, elapsed_time_sec=elapsed_time.total_seconds(),
                   first_node=first_node)


def build_own_reposts_graphs(yt_standard_names, tt_standard_names, pairs_yt, pairs_yt_tt,
                             videoId2yt_type, videoId2publishedAt) -> dict:
    """Per channel: its YouTube videos (Short/RV) and TikToks, linked by matches within the same actor."""
    gs = dict()
    for name_standard in yt_standard_names:
        pairs_df_curr = pairs_yt[pairs_yt.name_standard == name_standard]
        gs[name_standard] = nx.Graph()
        yt_nodes = set(pairs_df_curr.videoId1).union(set(pairs_df_curr.videoId2))
        gs[name_standard].add_nodes_from([v for v in yt_nodes if videoId2yt_type[v] == "Short"], type="Short")
        gs[name_standard].add_nodes_from([v for v in yt_nodes if videoId2yt_type[v] == "RV"], type="RV")
        add_match_edges(gs[name_standard], pairs_df_curr, videoId2publishedAt)

        if name_standard in tt_standard_names:
            pairs_yt_tt_curr = pairs_yt_tt[(pairs_yt_tt.yt_name_standard == name_standard) &
                                           (pairs_yt_tt.tt_name_standard == name_standard)]
            gs[name_standard].add_nodes_from(set(pairs_yt_tt_curr.videoId1), type="tiktok")
            add_match_edges(gs[name_standard], pairs_yt_tt_curr, videoId2publishedAt)
    return gs


def build_diff_graphs(yt_pp_standard_names, tt_pp_standard_names, pairs_diff_yt, pairs_diff_tt,
                      videoId2publishedAt) -> dict:
    """Per politician/party channel: its videos linked to the news videos they match."""
    gs_diff = dict()
    for name_standard in yt_pp_standard_names:
        pairs_df_curr = pairs_diff_yt[pairs_diff_yt.name_standard1 == name_standard]
        gs_diff[name_standard] = nx.Graph()
        gs_diff[name_standard].add_nodes_from(set(pairs_df_curr.videoId1), type="youtube_pp")
        gs_diff[name_standard].add_nodes_from(set(pairs_df_curr.videoId2), type="nm")
        add_match_edges(gs_diff[name_standard], pairs_df_curr, videoId2publishedAt)

        if name_standard in tt_pp_standard_names:
            pairs_df_tt_curr = pairs_diff_tt[pairs_diff_tt.name_standard1 == name_standard]
            gs_diff[name_standard].add_nodes_from(set(pairs_df_tt_curr.videoId1), type="tiktok_pp")
            gs_diff[name_standard].add_nodes_from(set(pairs_df_tt_curr.videoId2), type="nm")
            add_match_edges(gs_diff[name_standard], pairs_df_tt_curr, videoId2publishedAt)
    return gs_diff


def build_parties_graphs(pairs_yt_pp, pairs_same_party_yt_tt) -> dict:
    """Per party: videos of all its members, linked by matches (no edge attributes)."""
    gs_parties = dict()
    for party in pairs_same_party_yt_tt.party.unique():
        pairs_yt_curr = pairs_yt_pp[pairs_yt_pp.party == party]
        pairs_yt_tt_curr = pairs_same_party_yt_tt[pairs_same_party_yt_tt.party == party]

        g = nx.Graph()
        g.add_nodes_from(set(pairs_yt_curr.videoId1), type="Short")
        g.add_nodes_from(set(pairs_yt_curr.videoId2), type="RV")
        matches = pairs_yt_curr[pairs_yt_curr.predicted_label == 1]
        g.add_edges_from(zip(matches.videoId1, matches.videoId2))

        g.add_nodes_from(set(pairs_yt_tt_curr.videoId1), type="tiktok")
        matches = pairs_yt_tt_curr[pairs_yt_tt_curr.predicted_label == 1]
        g.add_edges_from(zip(matches.videoId1, matches.videoId2))
        gs_parties[party] = g

        # RVs: if a member has no Short there is no pair in pairs_yt_curr, so count
        # RVs from yt pairs ⋃ YouTube videos from yt_tt pairs, minus Shorts from yt pairs
        n_rvs = len(set(pairs_yt_curr.videoId2).union(set(pairs_yt_tt_curr.videoId2))
                    .difference(set(pairs_yt_curr.videoId1)))
        print(f"{party} - {len(set(pairs_yt_curr.videoId1))} Shorts - {n_rvs} RVs - "
              f"{len(set(pairs_yt_tt_curr.videoId1))} tiktoks")
        print(f"\t {len(g.nodes)} nodes and {len(g.edges)} edges")
    return gs_parties


def write_graphs(gs: dict, graph_type: str, networks_dir: str) -> None:
    out_dir = f"{networks_dir}/{graph_type}_{YEAR}"
    os.makedirs(out_dir, exist_ok=True)
    for name, g in gs.items():
        nx.nx_agraph.write_dot(g, f"{out_dir}/{name}_gs_{graph_type}_{YEAR}.gv")


# ── Main ──────────────────────────────────────────────────────────────────────

def run(model_path=MODEL_PATH, threshold_path=THRESHOLD_PATH,
        classified_dir=CLASSIFIED_DIR, networks_dir=NETWORKS_DIR):
    with open(model_path, "rb") as f:
        model = pickle.load(f)
    with open(threshold_path) as f:
        best_thr = float(f.read())

    politician2party = get_politician2party()
    videos = load_videos()
    transcripts = load_transcripts(videos)
    yt_videos = videos[videos.platform == "youtube"]
    videoId2yt_type = dict(zip(yt_videos.videoId, np.where(yt_videos.isShort == True, "Short", "RV")))
    videoId2publishedAt = dict(zip(videos.videoId, videos.publishedAt))
    videoid2standard_name = dict(zip(videos.videoId, videos.name_standard))

    yt_nm_standard_names = load_standard_names("youtube", "news")
    yt_pp_standard_names = load_standard_names("youtube", "pp")
    tt_nm_standard_names = load_standard_names("tiktok", "news")
    tt_pp_standard_names = load_standard_names("tiktok", "pp")

    os.makedirs(classified_dir, exist_ok=True)
    pairs = classify_all_pairs(transcripts, model, best_thr, classified_dir)

    def with_names(df, **kwargs):
        return add_name_standard_to_transcript_pairs(df, videoid2standard_name, politician2party, **kwargs)

    pairs_yt_same_channel_pp = with_names(pairs["pairs_yt_same_channel_pp_2024"])
    pairs_yt_same_channel_nm = with_names(pairs["pairs_yt_same_channel_nm_2024"])
    pairs_same_party_yt_tt = with_names(pairs["pairs_same_party_yt_tt_2024"], same_channel=False, w_tt=True)
    pairs_same_actor_yt_tt_nm = with_names(pairs["pairs_same_actor_yt_tt_nm_2024"], same_channel=False, w_tt=True)
    pairs_diff_channels_yt = with_names(pd.concat([pairs["pairs_diff_channels_yt_pp_all_nm_2024"],
                                                   pairs["pairs_diff_channels_yt_party_all_nm_2024"]]),
                                        same_channel=False)
    pairs_diff_channels_tt = with_names(pd.concat([pairs["pairs_diff_channels_tt_pp_all_nm_2024"],
                                                   pairs["pairs_diff_channels_tt_party_all_nm_2024"]]),
                                        same_channel=False)

    write_graphs(build_own_reposts_graphs(yt_pp_standard_names, tt_pp_standard_names,
                                          pairs_yt_same_channel_pp, pairs_same_party_yt_tt,
                                          videoId2yt_type, videoId2publishedAt),
                 "pp_only", networks_dir)
    write_graphs(build_own_reposts_graphs(yt_nm_standard_names, tt_nm_standard_names,
                                          pairs_yt_same_channel_nm, pairs_same_actor_yt_tt_nm,
                                          videoId2yt_type, videoId2publishedAt),
                 "news_only", networks_dir)
    write_graphs(build_diff_graphs(yt_pp_standard_names, tt_pp_standard_names,
                                   pairs_diff_channels_yt, pairs_diff_channels_tt, videoId2publishedAt),
                 "diff", networks_dir)
    write_graphs(build_parties_graphs(pairs_yt_same_channel_pp, pairs_same_party_yt_tt),
                 "parties", networks_dir)
    print(f"Saved classified pairs -> {classified_dir}/, graphs -> {networks_dir}/")


def main():
    run()


if __name__ == "__main__":
    main()