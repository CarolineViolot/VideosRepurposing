from transformers import pipeline, AutoTokenizer
from transformers import AutoModelForTokenClassification

import argparse
import os
import sys
import json
import pandas as pd
import re
import unicodedata

from unidecode import unidecode

module_path = os.path.abspath(os.path.join(''))
if module_path not in sys.path:
    sys.path.append(module_path)

if os.path.isdir("../data/"):
    os.chdir("../")

from scripts.project_config import YEARS


def clean_text_for_camembert(text):
    if not isinstance(text, str):
        text = str(text) if text is not None else ""

    # Keep only printable + common whitespace
    cleaned = "".join(
        ch for ch in text
        if unicodedata.category(ch) not in ("Cc", "Cs", "Co", "Cn")
        or ch in ("\n", "\t", " ")
    )
    cleaned = unidecode(cleaned)
    # Encode/decode to strip anything that slipped through
    cleaned = cleaned.encode("utf-8", errors="ignore").decode("utf-8")

    return cleaned.strip() or "vide"


def get_parties(text, polit2parties):
    if type(text) != str: return float('nan')
    names = text.split("|")
    names_clean = list(filter(None, list(set([polit2parties.get(name, '') for name in names]))))
    return '|'.join(names_clean)


def get_polit_orientation(text, party2orientation):
    if type(text) != str: return float('nan')
    parties = text.split("|")
    polit_orientations = list(filter(None, list(set([party2orientation.get(party, '') for party in parties]))))
    return '|'.join(polit_orientations)


def get_ner_results(description):
    tokenizer = AutoTokenizer.from_pretrained("Jean-Baptiste/camembert-ner")
    model = AutoModelForTokenClassification.from_pretrained("Jean-Baptiste/camembert-ner")

    nlp = pipeline('ner', model=model, tokenizer=tokenizer, aggregation_strategy="simple")

    ner_results = nlp(description)
    return ner_results


def extract_infos(ner_results, entity_group, threshold=0):
    return "|".join(
        [e["word"].title() for e in ner_results if e["entity_group"] == entity_group and e["score"] > threshold])


# text the NER runs on: the title on YouTube, the description on TikTok (no title there)
NER_TEXT_COL = {"youtube": "title", "tiktok": "video_description"}
ID_DTYPES = {"id": str, "videoId": str}  # video ids are text everywhere
NER_COLUMNS = ["ner_results", "LOC", "ORG", "PER"]


def add_ner_to_videos(filepath, platform="youtube"):
    """CamemBERT NER on the title (YouTube) / description (TikTok) of the videos that have none yet (no PER value).
    Writes ner_results, LOC, ORG and PER into the video file."""
    videos_df = pd.read_json(filepath, lines=True, dtype=ID_DTYPES)
    for col in NER_COLUMNS:
        if col not in videos_df.columns:
            videos_df[col] = None
    videos_df["ner_results"] = videos_df["ner_results"].astype(object)

    missing = videos_df["PER"].isna()
    print(f"{filepath}: NER on {missing.sum()}/{len(videos_df)} video(s)")
    if not missing.any():
        return

    clean_texts = videos_df.loc[missing, NER_TEXT_COL[platform]].apply(clean_text_for_camembert)

    def find_bad_chars(text):
        return [(i, repr(ch), unicodedata.category(ch))
                for i, ch in enumerate(text)
                if unicodedata.category(ch) in ("Cc", "Cs", "Co")]

    # Check if cleaning actually worked
    for i, text in enumerate(clean_texts):
        bad = find_bad_chars(str(text))
        if bad:
            print(f"Row {i} still has bad chars: {bad}")
            print(f"  Raw: {repr(text[:100])}")

    # get ner results from the text, then the LOC, ORG and PER entities
    for idx, ner_results in zip(clean_texts.index, get_ner_results(list(clean_texts))):
        videos_df.at[idx, "ner_results"] = ner_results
        for entity_group in ["LOC", "ORG", "PER"]:
            videos_df.at[idx, entity_group] = extract_infos(ner_results, entity_group)

    videos_df.to_json(filepath, orient='records', lines=True, force_ascii=False)


def get_final_name(name, name2abbname, famname2abbname, name2finalname):
    name = re.sub("\'|\(|\)|", "", name)
    abbname = name2abbname.get(name, name)
    abbname = famname2abbname.get(abbname, abbname)
    finalname = name2finalname.get(abbname, abbname)
    if "Affaire " in name: return ""
    return (finalname)


def clean_name(text, name2abbname, famname2abbname, name2finalname):
    if type(text) != str: return float('nan')

    if len(text) < 3: return ""
    names = text.split("|")
    names = [name[1:].strip() if name.startswith('.') else name for name in names]
    return "|".join([get_final_name(name.title(), name2abbname, famname2abbname, name2finalname) for name in names])


def clean_ORG_column(filepath):
    news_videos_NER_df = pd.read_json(filepath, lines=True, dtype=ID_DTYPES).fillna("")
    news_videos_NER_df["ORG"] = news_videos_NER_df["ORG"].replace("/", "|", regex=True) \
                                                         .replace("-", "|", regex=True) \
                                                         .replace('LFP RN LR', "LFP|RN|LR")
    news_videos_NER_df.to_json(filepath, orient='records', lines=True, force_ascii=False)


def clean_PER_column_manual(filepath):
    news_videos_NER_df = pd.read_json(filepath, lines=True, dtype=ID_DTYPES)
    # change known PER issues (only in PER: the other columns, e.g. transcripts, stay untouched)
    per = news_videos_NER_df["PER"]
    per = per.mask(per == 'Philippe Juvin J-L Mélenchon', 'Philippe Juvin|J-L Mélenchon')
    per = per.replace("Attal-", "Attal|", regex=True) \
        .replace("Bardella-", "Bardella|", regex=True) \
        .replace("Bompard-", "Bompard|", regex=True) \
        .replace("Macron-", "Macron|", regex=True) \
        .replace("Biden-", "Biden|", regex=True) \
        .replace("Trump-", "Trump|", regex=True) \
        .replace("Edouard Philippe-", "Edouard Philippe|", regex=True) \
        .replace("lepen|Lepen|LePen|le Pen", "Le Pen", regex=True) \
        .replace("Lula-", "Lula|", regex=True) \
        .replace("Tshisekedi-", "Tshisekedi|", regex=True) \
        .replace("Attal/Bardella", 'Attal|Bardella', regex=True) \
        .replace('Clément Beaune Rima Hassan', 'Clément Beaune|Rima Hassan', regex=True) \
        .replace('Maréchal-Zemmour', 'Maréchal|Zemmour', regex=True) \
        .replace('Dupont Aignan', 'Dupont-Aignan', regex=True) \
        .replace('Sarkozy-Fillon', 'Sarkozy|Fillon', regex=True) \
        .replace('Pécresse-Zemmour', 'Pécresse|Zemmour', regex=True) \
        .replace('Pécresse Zemmour', 'Pécresse|Zemmour', regex=True) \
        .replace('Hollande-Macron', 'Hollande|Macron', regex=True) \
        .replace('Macron-Hollande', 'Macron|Hollande', regex=True) \
        .replace('Juppé-Sarkozy', 'Juppé|Sarkozy', regex=True) \
        .replace("Mélenchon-Le Pen", "Mélenchon|Le Pen", regex=True)

    news_videos_NER_df["PER"] = per.apply(lambda x: x.title() if isinstance(x, str) else x)
    news_videos_NER_df.to_json(filepath, orient='records', lines=True, force_ascii=False)


def clean_PER_column_w_dict(filepath):
    news_videos_NER_df = pd.read_json(filepath, lines=True, dtype=ID_DTYPES)

    with open("data/dict/name2abbname.json", "r") as f:
        name2abbname = json.load(f)
        if "" in name2abbname.keys(): name2abbname.pop("")

    with open("data/dict/famname2abbname.json", "r") as f:
        famname2abbname = json.load(f)
        if "" in famname2abbname.keys(): famname2abbname.pop("")

    with open("data/dict/name2finalname.json", "r") as f:
        name2finalename = json.load(f)

    news_videos_NER_df["PER_clean"] = news_videos_NER_df["PER"].apply(
        clean_name, args=(name2abbname, famname2abbname, name2finalename))

    news_videos_NER_df.to_json(filepath, orient='records', lines=True, force_ascii=False)


def add_parties(filename):
    news_videos_df = pd.read_json(f"{filename}.jsonl", lines=True, dtype=ID_DTYPES)
    with open('data/dict/list_of_polit_from_parties.json') as f:
        polit_from_parties = json.load(f)
    polit2parties = {name: party for party, names in polit_from_parties.items() for name in names}
    news_videos_df['parties'] = news_videos_df['PER_clean'].apply(get_parties, args=(polit2parties,))
    news_videos_df.to_json(f"{filename}.jsonl", orient='records', lines=True, force_ascii=False)

STEPS = ["ner", "clean", "parties"]


def process_news_file(platform, year, steps=STEPS):
    """NER on the news videos' titles (YouTube) / descriptions (TikTok) -> cleaned politician
    names (PER_clean) -> parties,
    all written into the video file.

    ner      CamemBERT NER on the videos without a PER value yet (ner_results, LOC, ORG, PER)
    clean    normalise PER into PER_clean
    parties  derive the parties mentioned from PER_clean
    """
    filepath = f"data/{platform}/videos/news_videos_{year}.jsonl"
    print(f"== {filepath}")
    if "ner" in steps:
        add_ner_to_videos(filepath=filepath, platform=platform)
    if "clean" in steps:
        clean_PER_column_manual(filepath)
        clean_PER_column_w_dict(filepath)
    if "parties" in steps:
        add_parties(filepath.removesuffix(".jsonl"))


def main():
    parser = argparse.ArgumentParser(description="Detect politicians and parties mentioned in news videos.")
    parser.add_argument("--platform", choices=list(NER_TEXT_COL), default=None, help="default: both")
    parser.add_argument("--year", choices=YEARS, default=None, help="default: all in project_config")
    parser.add_argument("--steps", nargs="+", choices=STEPS, default=STEPS, help="default: all, in order")
    args = parser.parse_args()

    for platform in [args.platform] if args.platform else list(NER_TEXT_COL):
        for year in [args.year] if args.year else YEARS:
            process_news_file(platform, year, args.steps)


if __name__ == "__main__":
    main()