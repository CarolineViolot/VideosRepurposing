"""
tests/pipeline/compare_run.py
----------------------------
Compares the pipeline test (tests/pipeline/data/) with the real data/ folder,
restricted to the test channels and collection window. Only reads.

  1. videos       same videos collected?
  2. transcripts  same transcripts for the videos in both?
  3. pairs        same candidate pairs, same classification (match or not)?
  4. graphs       same edges between the test videos?

Differences are expected in a few places, so they are reported, not failed on:
videos deleted since the real collection, and transcripts re-generated (YouTube
auto-captions change, whisper is not fully deterministic). The real classified
pairs and graphs were rebuilt on 2026-09-29 with the current data/model.pkl, the
model the test uses, so the classification itself should match.

Called by run_pipeline.sh. Usage: python compare_run.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
REAL_DATA = os.path.join(REPO, "data")
TEST_DATA = os.path.join(HERE, "data")

sys.path.append(REPO)

import networkx as nx
import pandas as pd

sys.path.insert(0, HERE)
import scripts.project_config as config  # the test copy (tests/pipeline/scripts/)

ID = {"youtube": "videoId", "tiktok": "id"}
TRANSCRIPT = {"youtube": "transcript", "tiktok": "voice_to_text"}
DATE = {"youtube": "publishedAt", "tiktok": "create_time"}
PAIRS_FILES = [
    "pairs_yt_same_channel_pp", "pairs_yt_same_channel_nm",
    "pairs_same_actor_yt_tt_pp", "pairs_same_party_yt_tt", "pairs_same_actor_yt_tt_nm",
    "pairs_diff_channels_yt_pp_all_nm", "pairs_diff_channels_yt_party_all_nm",
    "pairs_diff_channels_tt_pp_all_nm", "pairs_diff_channels_tt_party_all_nm",
]
GRAPH_TYPES = ["pp_only", "news_only", "diff", "parties"]


def in_window(dates: pd.Series, year: str) -> pd.Series:
    """Collection period [start, end), end day excluded, in UTC (same rule as the pipeline)."""
    start, end = (pd.Timestamp(d, tz="UTC") for d in config.get_collect_periods()[year])
    dates = pd.to_datetime(dates, utc=True)
    return (dates >= start) & (dates < end)


def load_videos(data_dir: str, platform: str, channel_type: str, year: str) -> pd.DataFrame:
    """Videos of the test channels in the window (the real files are big: read in chunks)."""
    path = os.path.join(data_dir, platform, "videos", f"{channel_type}_videos_{year}.jsonl")
    keep = []
    for chunk in pd.read_json(path, lines=True, chunksize=20000, dtype={ID[platform]: str}):
        chunk = chunk[chunk["name_standard"].isin(config.TEST_CHANNELS[channel_type])]
        keep.append(chunk[in_window(chunk[DATE[platform]], year)])
    videos = pd.concat(keep)
    videos[ID[platform]] = videos[ID[platform]].astype(str)
    return videos.set_index(ID[platform])


def compare_videos_and_transcripts(year: str) -> set:
    """Sections 1 and 2. Returns the ids of the test videos."""
    print("\n== 1. Videos (test channels, collection window)")
    test_ids = set()
    transcript_rows = []
    for platform in ["youtube", "tiktok"]:
        for channel_type in config.CHANNEL_TYPES:
            real = load_videos(REAL_DATA, platform, channel_type, year)
            test = load_videos(TEST_DATA, platform, channel_type, year)
            test_ids |= set(test.index)
            only_real, only_test = set(real.index) - set(test.index), set(test.index) - set(real.index)
            print(f"{platform:8} {channel_type:5} real {len(real):4} | test {len(test):4} | "
                  f"only in real {len(only_real):3} | only in test {len(only_test):3}")
            for name, ids in [("only in real", only_real), ("only in test", only_test)]:
                if ids:
                    print(f"    {name}: {sorted(ids)[:10]}{' ...' if len(ids) > 10 else ''}")

            common = sorted(set(real.index) & set(test.index))
            col = TRANSCRIPT[platform]
            r, t = real.loc[common, col].fillna(""), test.loc[common, col].fillna("")
            transcript_rows.append({
                "file": f"{platform} {channel_type}", "videos in both": len(common),
                "transcript in real": int((r != "").sum()), "transcript in test": int((t != "").sum()),
                "identical": int(((r == t) & (r != "")).sum()),
            })

    print("\n== 2. Transcripts (videos in both)")
    print(pd.DataFrame(transcript_rows).to_string(index=False))
    return test_ids


def compare_pairs(year: str, test_ids: set) -> None:
    print("\n== 3. Pairs and classification (real pairs restricted to the test videos)")
    rows = []
    for name in PAIRS_FILES:
        filename = os.path.join("pairs_of_transcripts", "classified", f"{name}_{year}_classified.csv")
        cols = ["videoId1", "videoId2", "predicted_label"]
        test_path = os.path.join(TEST_DATA, filename)
        test = pd.read_csv(test_path, usecols=cols, dtype=str) if os.path.isfile(test_path) \
            else pd.DataFrame(columns=cols)
        real = pd.read_csv(os.path.join(REAL_DATA, filename), usecols=cols, dtype=str)
        real = real[real.videoId1.isin(test_ids) & real.videoId2.isin(test_ids)]

        real_labels = dict(zip(zip(real.videoId1, real.videoId2), real.predicted_label))
        test_labels = dict(zip(zip(test.videoId1, test.videoId2), test.predicted_label))
        common = set(real_labels) & set(test_labels)
        rows.append({
            "pairs file": name, "real": len(real_labels), "test": len(test_labels),
            "only real": len(set(real_labels) - set(test_labels)),
            "only test": len(set(test_labels) - set(real_labels)),
            "matches real": sum(v == "1" for v in real_labels.values()),
            "matches test": sum(v == "1" for v in test_labels.values()),
            "same label": sum(real_labels[p] == test_labels[p] for p in common),
            "in both": len(common),
        })
    print(pd.DataFrame(rows).to_string(index=False))


def compare_graphs(year: str, test_ids: set) -> None:
    print("\n== 4. Graphs (real graphs restricted to the test videos)")
    rows = []
    for graph_type in GRAPH_TYPES:
        test_dir = os.path.join(TEST_DATA, "networks", f"{graph_type}_{year}")
        if not os.path.isdir(test_dir):
            continue
        for filename in sorted(os.listdir(test_dir)):
            test = nx.nx_agraph.read_dot(os.path.join(test_dir, filename))
            real_path = os.path.join(REAL_DATA, "networks", f"{graph_type}_{year}", filename)
            real = nx.nx_agraph.read_dot(real_path).subgraph(test_ids) if os.path.isfile(real_path) else nx.Graph()
            real_edges = {frozenset(e) for e in real.edges()}
            test_edges = {frozenset(e) for e in test.edges()}
            rows.append({
                "graph": f"{graph_type}/{filename.split('_')[0]}",
                "edges real": len(real_edges), "edges test": len(test_edges),
                "only real": len(real_edges - test_edges), "only test": len(test_edges - real_edges),
            })
    print(pd.DataFrame(rows).to_string(index=False))


def main():
    for year in config.YEARS:
        print(f"######## {year}, channels {config.TEST_CHANNELS}, window {config.get_collect_periods()[year]}")
        test_ids = compare_videos_and_transcripts(year)
        compare_pairs(year, test_ids)
        compare_graphs(year, test_ids)


if __name__ == "__main__":
    main()
