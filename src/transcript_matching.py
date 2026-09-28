import unicodedata
import re
import warnings
import pandas as pd
import numpy as np
from joblib import Parallel, delayed
from fuzzywuzzy import fuzz as fw


BRACKET_TAGS = [
    r"musique", r"music", r"applaudissements?", r"applause", r"rires?", r"rire",
    r"sifflements?", r"bruit[s]?", r"silence", r"inaudible", r"coupe", r"transition",
    r"jingle", r"bip"
]

OPENERS = {
    "bonjour", "bonsoir", "salut", "bienvenue", "merci", "au revoir", "à bientôt", "a bientôt",
    "bonne soirée", "bonne journée"
}

def strip_accents_f(s: str) -> str:
    try:
        return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    except TypeError as e:
        print(s)
        raise e


def remove_brackets_f(t: str) -> str:
    # remove bracketed tags like [musique], (applaudissements), <rire>
    tag_pattern = r"[\[\(\<]\s*(?:{})(?:\s*[:\-–]\s*\w+)?\s*[\]\)\>]".format("|".join(BRACKET_TAGS))
    t = re.sub(tag_pattern, " ", t, flags=re.IGNORECASE)
    return t


def remove_tag_openers_f(t: str) -> str:
    # tokenization (simple)
    tokens = [tok for tok in t.split() if tok]

    # remove fillers and openers (single/multiword)
    # first remove multiword phrases greedily
    joined = " ".join(tokens)
    for phrase in sorted([*OPENERS], key=len, reverse=True):
        p = re.escape(strip_accents_f(phrase))
        joined = re.sub(rf"\b{p}\b", " ", joined)
    tokens = [tok for tok in joined.split() if tok]

    # final collapse
    out = re.sub(r"\s+", " ", " ".join(tokens)).strip()
    return out


def clean_transcripts(t: str, strip_accents: bool, lowercase: bool, remove_brackets: bool, remove_openers: bool) -> str:
    if strip_accents:
        t = strip_accents_f(t)
    if lowercase:
        t = t.lower()
    if remove_brackets:
        t = remove_brackets_f(t)
    if remove_openers:
        t = remove_tag_openers_f(t)
    return t


def extract_short_transcript(transcript, length_transcript):
    if type(transcript) == float: return transcript
    if len(transcript) < 100 + length_transcript:
        return transcript
    else:
        return transcript[100:100 + length_transcript]


def create_model_feature_dict(columns_name):
    """
    return a dict of columns names so that all versions have the same names, for ex both :
     - 'fw.partialratio_strip_accents_lowercase_remove_brackets_remove_openers': 'fw.partialratio'
     - 'fw.partialratio_' : 'fw.partialratio'
    """
    model_features_dict = {}

    for col in columns_name:
        for ratio_type in ['partialratio', 'sortratio', 'setratio']:
            if ratio_type in col:
                suffix = '_cut_t1' if 'cut_t1' in col else ('_cut_t2' if 'cut_t2' in col else '')
                model_features_dict[col] = f'{ratio_type}{suffix}'
                break

    return model_features_dict


def process_pairs(pairs, video2channeldict, video2transcriptlength=dict(), verbose = False):
    if video2transcriptlength is None:
        video2transcriptlength = dict()
    model_features_dict = create_model_feature_dict(pairs.columns)
    if verbose: print('renaming columns')
    pairs.rename(columns=model_features_dict, inplace=True)
    if 'videoId1' not in pairs.columns:
        if verbose: print('creating videoId1 and videoId2')
        pairs['videoId1'] = pairs['id1,id2'].str[:11]
        pairs['videoId2'] = pairs['id1,id2'].str[11:]
    if verbose: print('creating channel1 and channel2')
    pairs['channel1'] = pairs['videoId1'].map(video2channeldict)
    pairs['channel2'] = pairs['videoId2'].map(video2channeldict)
    if len(video2transcriptlength) > 0:
        pairs['transcript1_length'] = pairs['videoId1'].apply(lambda x: video2transcriptlength.get(x, None))
        pairs['transcript2_length'] = pairs['videoId2'].apply(lambda x: video2transcriptlength.get(x, None))
    else:
        pairs['transcript1_length'] = pairs['transcript_clean1'].apply(len)
        pairs['transcript2_length'] = pairs['transcript_clean2'].apply(len)
    pairs['diffchannel'] = pairs['channel1'] != pairs['channel2']
    if 'Label' in pairs.columns:
        pairs['label_binary'] = (pairs['Label'] != "No").astype(int)
    return pairs


def get_model_coeffs(model):
    model_weights = {}
    for feature_name, weight in zip(model.feature_names_in_, model.coef_[0]):
        model_weights[feature_name] = float(weight)
    model_weights['bias'] = float(model.intercept_[0])
    return model_weights


def compute_ratios(pairs_df: pd.DataFrame, preprocessing_summary: str, transcript_col_1: str,
                   transcript_col_2: str):
    # Calculate lengths
    data = list(zip(pairs_df[transcript_col_1], pairs_df[transcript_col_2]))
    lengths = [len(t1) + len(t2) for t1, t2 in data]

    # Sort by length (longest first) - helps balance load
    sorted_indices = np.argsort(lengths)[::-1]  # Descending order
    sorted_data = [data[i] for i in sorted_indices]

    # Process
    results_partialratio = Parallel(n_jobs=8, batch_size=1)(
        delayed(fw.partial_ratio)(t1, t2) for t1, t2 in sorted_data
    )
    results_sort_ratio = Parallel(n_jobs=8, batch_size=1)(
        delayed(fw.token_sort_ratio)(t1, t2) for t1, t2 in sorted_data
    )
    results_set_ratio = Parallel(n_jobs=8, batch_size=1)(
        delayed(fw.token_set_ratio)(t1, t2) for t1, t2 in sorted_data
    )

    # Unsort results back to original order
    results = [None] * len(data)
    for i, result in zip(sorted_indices, results_partialratio):
        results[i] = result
    pairs_df[f"fw.partialratio{preprocessing_summary}"] = results

    results = [None] * len(data)
    for i, result in zip(sorted_indices, results_sort_ratio):
        results[i] = result
    pairs_df[f"fw.sortratio{preprocessing_summary}"] = results

    results = [None] * len(data)
    for i, result in zip(sorted_indices, results_set_ratio):
        results[i] = result
    pairs_df[f"fw.setratio{preprocessing_summary}"] = results

    return pairs_df


def add_distances(pairs_df, args_dict, preprocessing_summary, keep_all_columns=False):
    """
    Fuzzy ratios between transcript1 and transcript2 after the preprocessing in args_dict.
    Returns (pairs_df, preprocessing_summary). Unless keep_all_columns, pairs_df is reduced
    to the video ids and the ratio columns.
    """

    pairs_df['transcript_clean1'] = pairs_df['transcript1'].apply(
        clean_transcripts,
        strip_accents=bool(args_dict['strip_accents']),
        lowercase=bool(args_dict['lowercase']),
        remove_brackets=bool(args_dict['remove_brackets']),
        remove_openers=bool(args_dict['remove_openers'])
    )
    pairs_df['transcript_clean2'] = pairs_df['transcript2'].apply(
        clean_transcripts,
        strip_accents=bool(args_dict['strip_accents']),
        lowercase=bool(args_dict['lowercase']),
        remove_brackets=bool(args_dict['remove_brackets']),
        remove_openers=bool(args_dict['remove_openers'])
    )

    if args_dict['cut_transcripts'] > 0:

        pairs_df["transcript_cut1"] = pairs_df["transcript_clean1"].apply(extract_short_transcript,
                                                                          length_transcript=args_dict[
                                                                              'cut_transcripts'])
        pairs_df["transcript_cut2"] = pairs_df["transcript_clean2"].apply(extract_short_transcript,
                                                                          length_transcript=args_dict[
                                                                              'cut_transcripts'])
        preprocessing_summary_1 = preprocessing_summary + "_cut_t1"
        pairs_df = compute_ratios(pairs_df, preprocessing_summary_1, "transcript_cut1",
                                  "transcript_clean2")
        preprocessing_summary_2 = preprocessing_summary + "_cut_t2"
        pairs_df = compute_ratios(pairs_df, preprocessing_summary_2, "transcript_clean1",
                                  "transcript_cut2")
        preprocessing_summary = preprocessing_summary + f"cut_{args_dict['cut_transcripts']}"
        if keep_all_columns:
            return pairs_df, preprocessing_summary
        return pairs_df[['videoId1', 'videoId2', 'fw.partialratio_cut_t1', 'fw.sortratio_cut_t1',
                         'fw.setratio_cut_t1', 'fw.partialratio_cut_t2', 'fw.sortratio_cut_t2',
                         'fw.setratio_cut_t2']], preprocessing_summary
    else:
        pairs_df = compute_ratios(
            pairs_df, preprocessing_summary, "transcript_clean1", "transcript_clean2")
        if keep_all_columns:
            return pairs_df, preprocessing_summary
        return pairs_df[['videoId1', 'videoId2', 'fw.partialratio',
                         'fw.sortratio', 'fw.setratio']], preprocessing_summary


def add_transcript_to_video_pairs(video_pairs, transcripts, filename):
    import warnings
    initial_length = len(video_pairs)
    transcripts['videoId'] = transcripts['videoId'].apply(str)
    if ('id1' in video_pairs.columns) & ('id2' in video_pairs.columns):
        id_name = 'id'
    elif ('videoId1' in video_pairs.columns) & ('videoId2' in video_pairs.columns):
        id_name = 'videoId'
    video_pairs["videoId1"] = video_pairs[f"{id_name}1"].apply(lambda x: str(x).replace('www.youtube.com/shorts/', '').\
                                                                                replace('www.youtube.com/watch?v=', '').\
                                                                                replace('www.tiktok.com/@user/video/', ''))
    video_pairs["videoId2"] = video_pairs[f"{id_name}2"].apply(lambda x: str(x).replace('www.youtube.com/shorts/', '').\
                                                                                replace('www.youtube.com/watch?v=', '').\
                                                                                replace('www.tiktok.com/@user/video/', ''))
    video_pairs["id1,id2"] = video_pairs["videoId1"] + video_pairs["videoId2"]
    video_pairs = video_pairs.merge(
        transcripts[["videoId", "transcript", "transcript_clean"]], left_on = "videoId1", right_on="videoId").rename(
        columns={'transcript_clean':'transcript_clean1',
                'transcript':'transcript1'}).drop(columns=['videoId'])
    video_pairs = video_pairs.merge(
        transcripts[["videoId",  "transcript", "transcript_clean"]], left_on = "videoId2", right_on="videoId").rename(
        columns={'transcript_clean':'transcript_clean2',
                'transcript':'transcript2',
                'value':'fw.partialratio'}).drop(columns=['videoId'])
    if len(video_pairs) != initial_length:
        warnings.warn(f"for {filename}, initial lenght: {initial_length}, curr lenght: {len(video_pairs)}")
    video_pairs = video_pairs[video_pairs.transcript_clean1.str.len() > 50]
    video_pairs = video_pairs[video_pairs.transcript_clean2.str.len() > 50]
    return video_pairs


def classify_pairs(pairs_df, model, best_thr):
    pairs_df.columns = [c.replace('fw.', '') for c in pairs_df.columns]
    all_probas = model.predict_proba(pairs_df[model.feature_names_in_]
                                     )[:, 1]

    pairs_df['predicted_proba'] = all_probas
    pairs_df['predicted_label'] = pairs_df['predicted_proba'].apply(
        lambda x: 1 if x > best_thr else 0)
    return pairs_df[['videoId1', 'videoId2', 'predicted_proba', 'predicted_label'] +
                    list(model.feature_names_in_)]


def filter_small_transcripts(df, min_length=100):
    try:
        df = df.dropna(subset=["transcript"]).copy()
        df["len_transcript"] = df["transcript"].str.len()
    except KeyError:
        df = df.dropna(subset=["voice_to_text"]).copy()
        df["len_transcript"] = df["voice_to_text"].str.len()
    return df.loc[df["len_transcript"] > min_length]
