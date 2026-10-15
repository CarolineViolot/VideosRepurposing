"""
scripts/evaluate_matching_methods.py
----------------------------
Compares fuzzy-ratio feature sets and transcript preprocessings for the matching
classifier, on the same labeled pairs as scripts/train_matching_model.py
(YouTube-only + YouTube x TikTok annotation files).

For each preprocessing variant of the full grid (every combination of the 4
preprocessing flags x every cut length: 16 x 6 = 96 variants), computes the
partial / token-sort / token-set ratios of every labeled pair, then runs a 5-fold
cross-validation of a logistic regression for each feature set (FEATURE_SETS):
accuracy on the test fold, with the threshold maximizing F1 on the training folds
(as for the final model). All variants use the same pairs and the same folds.

Outputs (data/pairs_of_transcripts/evaluation/):
  - features_{variant}.csv     ratios per labeled pair; reused on later runs
                               (the no-cut variants take long), --recompute to redo them
  - matching_evaluation.csv    mean and std accuracy per variant x feature set
                               (is_production marks the pipeline's configuration),
                               shown by notebooks/02_matching_preprocessing_evaluation.ipynb

Usage: python -m scripts.evaluate_matching_methods [--recompute]
"""
import argparse
import itertools
import os
import random

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve

if os.path.isdir("../data/"):
    os.chdir("../")

from src.transcript_matching import add_distances
from scripts.train_matching_model import (YT_ANNOTATION_FILES, YT_TT_ANNOTATION_FILES,
                                          load_all_transcripts, prepare_labeled_pairs)

OUTPUT_DIR = "data/pairs_of_transcripts/evaluation"
N_FOLDS = 5
MIN_TRANSCRIPT_LENGTH = 100

PREPROCESSING_FLAGS = ["strip_accents", "lowercase", "remove_brackets", "remove_openers"]
CUTS = [0, 2000, 5000, 10000, 15000, 20000]  # 0 = full transcripts


def variant_name(flags: tuple, cut: int) -> str:
    return f"{'-'.join(flags) or 'none'}_cut{cut}"


# full grid: every combination of preprocessing flags x every cut length (16 x 6 = 96 variants)
VARIANTS = {
    variant_name(flags, cut): {**{f: int(f in flags) for f in PREPROCESSING_FLAGS}, "cut_transcripts": cut}
    for n in range(len(PREPROCESSING_FLAGS) + 1)
    for flags in itertools.combinations(PREPROCESSING_FLAGS, n)
    for cut in CUTS
}

# setting used by the pipeline (train_matching_model, compute_distances_w_preprocessing)
PRODUCTION_VARIANT = variant_name(("strip_accents", "lowercase", "remove_brackets"), 2000)
PRODUCTION_FEATURE_SET = "partial sort set"

FEATURE_SETS = {
    "partial": ["partial"],
    "sort": ["sort"],
    "set": ["set"],
    "partial sort": ["partial", "sort"],
    "partial set": ["partial", "set"],
    "sort set": ["sort", "set"],
    "partial sort set": ["partial", "sort", "set"],
}


def feature_columns(ratios: list, cut: int) -> list:
    """With a cut, each ratio comes twice: cut transcript 1 vs full 2, and full 1 vs cut 2."""
    suffixes = ["_cut_t1", "_cut_t2"] if cut else [""]
    return [f"{r}ratio{s}" for r in ratios for s in suffixes]


def load_labeled_pairs() -> pd.DataFrame:
    transcripts = load_all_transcripts()
    pairs = pd.concat([prepare_labeled_pairs(pd.read_excel(f, index_col=0), transcripts)
                       for f in YT_ANNOTATION_FILES + YT_TT_ANNOTATION_FILES]).reset_index(drop=True)
    long_enough = ((pairs.transcript1.str.len() > MIN_TRANSCRIPT_LENGTH)
                   & (pairs.transcript2.str.len() > MIN_TRANSCRIPT_LENGTH))
    pairs = pairs[long_enough].reset_index(drop=True)
    print(f"{len(pairs)} labeled pairs ({pairs.label_binary.sum()} matching)")
    return pairs[["videoId1", "videoId2", "transcript1", "transcript2", "label_binary"]]


def compute_features(pairs: pd.DataFrame, name: str, recompute: bool) -> pd.DataFrame:
    path = f"{OUTPUT_DIR}/features_{name}.csv"
    if os.path.isfile(path) and not recompute:
        return pd.read_csv(path, dtype={"videoId1": str, "videoId2": str})
    print(f"computing ratios for variant '{name}'")
    features, _ = add_distances(pairs.copy(), VARIANTS[name], preprocessing_summary="", keep_all_columns=True)
    features.columns = [c.replace("fw.", "") for c in features.columns]
    ratio_cols = [c for c in features.columns if "ratio" in c]
    features = features[["videoId1", "videoId2", "label_binary"] + ratio_cols]
    features.to_csv(path, index=False)
    return features


def cross_validate(features: pd.DataFrame, columns: list, folds: list) -> list:
    """Accuracy on each test fold, threshold maximizing F1 on the training folds."""
    accuracies = []
    for i, test_idx in enumerate(folds):
        train_idx = [idx for j, fold in enumerate(folds) if j != i for idx in fold]
        X_train, y_train = features.loc[train_idx, columns], features.loc[train_idx, "label_binary"]
        X_test, y_test = features.loc[test_idx, columns], features.loc[test_idx, "label_binary"]

        model = LogisticRegression().fit(X_train, y_train)
        prec, rec, thr = precision_recall_curve(y_train, model.predict_proba(X_train)[:, 1])
        f1 = 2 * prec * rec / (prec + rec)
        best_thr = np.mean([thr[np.argmax(f1)], thr[np.argmax(f1) - 1]])

        y_pred = (model.predict_proba(X_test)[:, 1] >= best_thr).astype(int)
        accuracies.append((y_pred == y_test).mean())
    return accuracies


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recompute", action="store_true", help="recompute the ratios of every variant")
    args = parser.parse_args()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    pairs = load_labeled_pairs()
    indices = list(pairs.index)
    random.seed(0)
    random.shuffle(indices)
    k, m = divmod(len(indices), N_FOLDS)
    folds = [indices[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(N_FOLDS)]

    rows = []
    for name, preprocessing in VARIANTS.items():
        features = compute_features(pairs, name, args.recompute)
        for feature_set, ratios in FEATURE_SETS.items():
            accuracies = cross_validate(features, feature_columns(ratios, preprocessing["cut_transcripts"]), folds)
            rows.append({"variant": name, "feature_set": feature_set, **preprocessing,
                         "is_production": name == PRODUCTION_VARIANT and feature_set == PRODUCTION_FEATURE_SET,
                         "mean_accuracy": np.mean(accuracies), "std_accuracy": np.std(accuracies),
                         "n_pairs": len(features)})
        print(f"{name}: done")

    results = pd.DataFrame(rows)
    results.to_csv(f"{OUTPUT_DIR}/matching_evaluation.csv", index=False)
    show = ["variant", "feature_set", "mean_accuracy", "std_accuracy"]
    print("\n10 best configurations:")
    print(results.sort_values("mean_accuracy", ascending=False)[show].head(10).round(3).to_string(index=False))
    print("\npipeline configuration:")
    print(results[results.is_production][show].round(3).to_string(index=False))


if __name__ == "__main__":
    main()