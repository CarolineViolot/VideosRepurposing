"""
scripts/train_matching_model.py
----------------------------
Trains the production transcript-matching classifier (logistic regression on
fuzzy Levenshtein ratios) on all labeled pairs (YouTube-only + YouTube x TikTok),
picks the probability threshold that maximizes F1, and saves the artefacts.

Outputs:
  - data/model.pkl          the fitted LogisticRegression
  - data/best_thr.txt       the selected probability threshold
  - data/pairs_of_transcripts/training_pairs.jsonl
                            the labeled training pairs with their features,
                            read by notebooks/05_model_training.ipynb for diagnostics
"""
import os
import pickle

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve

if os.path.isdir("../data/"):
    os.chdir("../")

from src.transcript_matching import (clean_transcripts, compute_ratios,
                                     extract_short_transcript, process_pairs)

PLATFORMS = ["youtube", "tiktok"]
CHANNEL_TYPES = ["news", "pp"]
YEARS = ["2022", "2024"]

YT_ANNOTATION_FILES = [
    "data/youtube/transcripts/manual_annotations/similarities_same_channel_news_2024_labeled.xlsx",
    "data/youtube/transcripts/manual_annotations/similarities_same_channel_polit_2024_labeled.xlsx",
    "data/youtube/transcripts/manual_annotations/similarities_diff_channel_polit_2024_labeled.xlsx",
]
YT_TT_ANNOTATION_FILES = [
    "data/pairs_of_transcripts/annotation/pairs_yt_tt_nm_2022_to_annotate.xlsx",
    "data/pairs_of_transcripts/annotation/pairs_yt_tt_pp_2024_to_annotate.xlsx",
]

FEATURE_COLUMNS = [
    "partialratio_cut_t1",
    "partialratio_cut_t2",
    "sortratio_cut_t1",
    "sortratio_cut_t2",
]
CUT_LENGTH = 2000

MODEL_PATH = "data/model.pkl"
THRESHOLD_PATH = "data/best_thr.txt"
TRAINING_PAIRS_PATH = "data/pairs_of_transcripts/training_pairs.jsonl"


def load_all_transcripts() -> pd.DataFrame:
    """Load every video's transcript + standard channel name, across platforms/types/years."""
    frames = []
    for platform in PLATFORMS:
        for channel_type in CHANNEL_TYPES:
            for year in YEARS:
                df = pd.read_json(f"data/{platform}/videos/{channel_type}_videos_{year}.jsonl", lines=True,
                                  dtype={"id": str, "videoId": str})
                if platform == "tiktok":
                    df = df.rename(columns={"id": "videoId", "voice_to_text": "transcript"})
                frames.append(df[["videoId", "transcript", "name_standard"]])

    transcripts = pd.concat(frames).dropna(subset="transcript")
    transcripts["videoId"] = transcripts["videoId"].apply(str)
    transcripts["transcript_clean"] = transcripts["transcript"].apply(
        clean_transcripts,
        strip_accents=True, lowercase=True, remove_brackets=True, remove_openers=False
    )
    print(f"{len(transcripts):,} transcripts loaded")
    return transcripts


def prepare_labeled_pairs(labeled_pairs: pd.DataFrame, transcripts: pd.DataFrame) -> pd.DataFrame:
    """Merge transcript text into a labeled-pairs dataframe and add binary label."""
    initial_length = len(labeled_pairs)
    labeled_pairs = labeled_pairs.dropna(subset="Label").copy()

    valid_labels = {"No", "Yes, one whole fragment", "Yes, cut fragments", "Yes"}
    assert set(labeled_pairs.Label) - valid_labels == set(), set(labeled_pairs.Label)

    id_name = "id" if ("id1" in labeled_pairs.columns) else "videoId"

    def clean_id(x):
        return (x.replace("www.youtube.com/shorts/", "")
                 .replace("www.youtube.com/watch?v=", "")
                 .replace("www.tiktok.com/@user/video/", ""))

    labeled_pairs["videoId1"] = labeled_pairs[f"{id_name}1"].apply(clean_id)
    labeled_pairs["videoId2"] = labeled_pairs[f"{id_name}2"].apply(clean_id)
    labeled_pairs["id1,id2"] = labeled_pairs["videoId1"] + labeled_pairs["videoId2"]

    for i in ["1", "2"]:
        labeled_pairs = (
            labeled_pairs
            .merge(transcripts[["videoId", "transcript", "transcript_clean"]],
                   left_on=f"videoId{i}", right_on="videoId")
            .rename(columns={"transcript_clean": f"transcript_clean{i}", "transcript": f"transcript{i}"})
            .drop(columns=["videoId"])
        )

    if len(labeled_pairs) != initial_length:
        print(f"Length mismatch: {initial_length} -> {len(labeled_pairs)}")

    labeled_pairs = labeled_pairs[labeled_pairs.transcript1.str.len() > 50]
    labeled_pairs = labeled_pairs[labeled_pairs.transcript2.str.len() > 50]
    labeled_pairs["label_binary"] = (labeled_pairs["Label"] != "No").astype(int)
    return labeled_pairs


def add_ratio_features(pairs: pd.DataFrame) -> pd.DataFrame:
    """Fuzzy ratios between the cut transcript of one video and the full transcript of the other."""
    pairs = pairs.reset_index(drop=True)
    pairs["transcript_cut1"] = pairs["transcript_clean1"].apply(extract_short_transcript, length_transcript=CUT_LENGTH)
    pairs["transcript_cut2"] = pairs["transcript_clean2"].apply(extract_short_transcript, length_transcript=CUT_LENGTH)
    pairs = compute_ratios(pairs, "_cut_t1", "transcript_cut1", "transcript_clean2")
    pairs = compute_ratios(pairs, "_cut_t2", "transcript_clean1", "transcript_cut2")
    return pairs


def build_training_set(transcripts: pd.DataFrame) -> pd.DataFrame:
    labeled_pairs_youtube_only = add_ratio_features(pd.concat([
        prepare_labeled_pairs(pd.read_excel(f, index_col=0), transcripts) for f in YT_ANNOTATION_FILES
    ]))
    labeled_pairs_youtube_tiktok = add_ratio_features(pd.concat([
        prepare_labeled_pairs(pd.read_excel(f, index_col=0), transcripts) for f in YT_TT_ANNOTATION_FILES
    ]))
    print(f"YouTube-only pairs: {len(labeled_pairs_youtube_only):,}")
    print(f"YouTube x TikTok pairs: {len(labeled_pairs_youtube_tiktok):,}")

    all_labeled_pairs = pd.concat([labeled_pairs_youtube_only, labeled_pairs_youtube_tiktok]).reset_index(drop=True)
    all_labeled_pairs.columns = [c.replace("fw.", "") for c in all_labeled_pairs.columns]

    video2channel = dict(zip(transcripts["videoId"], transcripts["name_standard"]))
    labeled_pairs = process_pairs(all_labeled_pairs, video2channel)
    labeled_pairs = labeled_pairs.drop(columns=["party", "id1", "id2", "partialratio", "Unnamed: 6"], errors="ignore")

    n_pos = int(labeled_pairs["label_binary"].sum())
    print(f"Total labeled pairs: {len(labeled_pairs):,} ({n_pos} positive, {len(labeled_pairs) - n_pos} negative)")
    return labeled_pairs


def train_model(labeled_pairs: pd.DataFrame) -> LogisticRegression:
    model = LogisticRegression()
    model.fit(labeled_pairs[FEATURE_COLUMNS], labeled_pairs["label_binary"])

    print("Model coefficients:")
    for feat, coef in zip(model.feature_names_in_, model.coef_[0]):
        print(f"  {feat:30s} {coef:+.4f}")
    print(f"  {'intercept':30s} {model.intercept_[0]:+.4f}")
    return model


def select_threshold(model: LogisticRegression, labeled_pairs: pd.DataFrame) -> float:
    """Midpoint between the F1-maximizing threshold and the one just below it."""
    predicted_probas = model.predict_proba(labeled_pairs[FEATURE_COLUMNS])[:, 1]
    prec, rec, thr = precision_recall_curve(labeled_pairs["label_binary"], predicted_probas)
    f1 = 2 * prec * rec / (prec + rec)
    best_thr = float(np.mean([thr[np.argmax(f1)], thr[np.argmax(f1) - 1]]))
    print(f"Best threshold: {best_thr:.4f}")
    return best_thr


def main():
    transcripts = load_all_transcripts()
    labeled_pairs = build_training_set(transcripts)
    model = train_model(labeled_pairs)
    best_thr = select_threshold(model, labeled_pairs)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(THRESHOLD_PATH, "w") as f:
        f.write(str(best_thr))
    labeled_pairs.to_json(TRAINING_PAIRS_PATH, lines=True, orient="records", force_ascii=False)

    print(f"Saved model -> {MODEL_PATH}")
    print(f"Saved threshold ({best_thr:.4f}) -> {THRESHOLD_PATH}")
    print(f"Saved training pairs -> {TRAINING_PAIRS_PATH}")


if __name__ == "__main__":
    main()
