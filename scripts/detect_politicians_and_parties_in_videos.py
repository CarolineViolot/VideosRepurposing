from transformers import pipeline, AutoTokenizer
from transformers import AutoModelForTokenClassification

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

from src.file_io import read_video_file
from src.utils import get_politician2party


def read_video_df(filepath):
    """Read a video dataframe, handling .jsonl explicitly.

    NOTE: read_video_file (from src.file_io) may not support .jsonl —
    verify its implementation. This wrapper reads .jsonl directly with
    pandas and falls back to read_video_file for other extensions.
    """
    ext = os.path.splitext(filepath)[1]
    if ext == '.jsonl':
        return pd.read_json(filepath, lines=True)
    return read_video_file(filepath)


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


def save_video_with_NER(video_df, filepath):
    ext = os.path.splitext(filepath)[1]
    if ext == '.jsonl':
        # JSON Lines: one record per line
        video_df.to_json(filepath, orient='records', lines=True, force_ascii=False)
    elif ext == '.json':
        video_df.to_json(filepath, orient='records', indent=2, force_ascii=False)
    elif ext == '.csv':
        video_df.to_csv(filepath, index=False)
    else:
        raise ValueError(f'filepath does not contain ".jsonl", ".json" or ".csv"')


def create_news_channels_videos_df_NER(filepath, platform="youtube"):
    if platform == "youtube":
        id_col = "videoId"
        description_col = "description"
    if platform == "tiktok" :
        id_col = "id"
        description_col = "video_description"
    news_videos_df = read_video_df(filepath)
    filename, ext = os.path.splitext(filepath)
    if os.path.isfile(f"{filename}_NER{ext}"):
        news_videos_df_NER = read_video_df(f"{filename}_NER{ext}")
        missing_videos = set(news_videos_df[id_col]) - set(news_videos_df_NER[id_col])
        print("number of missing videos:", len(missing_videos))
    else:
        missing_videos = set(news_videos_df[id_col])
    missing_videos_df = news_videos_df[news_videos_df[id_col].isin(missing_videos)]

    missing_videos_df['clean_description'] = missing_videos_df[description_col].apply(clean_text_for_camembert)

    def find_bad_chars(text):
        return [(i, repr(ch), unicodedata.category(ch))
                for i, ch in enumerate(text)
                if unicodedata.category(ch) in ("Cc", "Cs", "Co")]

    # Check if cleaning actually worked
    for i, text in enumerate(missing_videos_df['clean_description']):
        bad = find_bad_chars(str(text))
        if bad:
            print(f"Row {i} still has bad chars: {bad}")
            print(f"  Raw: {repr(text[:100])}")
    # get ner results from the description
    missing_videos_df["ner_results"] = get_ner_results(list(missing_videos_df.clean_description))

    # add LOC, ORG and PER results to news videos df
    missing_videos_df["LOC"] = missing_videos_df.ner_results.apply(extract_infos, args=("LOC",))
    missing_videos_df["ORG"] = missing_videos_df.ner_results.apply(extract_infos, args=("ORG",))
    missing_videos_df["PER"] = missing_videos_df.ner_results.apply(extract_infos, args=("PER",))

    # save obtained DF as _NER.jsonl (or matching extension)
    if os.path.isfile(f"{filename}_NER{ext}"):
        # BUG FIX: original code assigned the return value of .to_csv() (None)
        # to video_df before calling save_video_df
        video_df = pd.concat([news_videos_df_NER, missing_videos_df])
        save_video_with_NER(video_df, f"{filename}_NER{ext}")
    else:
        save_video_with_NER(missing_videos_df, f"{filename}_NER{ext}")


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
    # now reads/writes any supported extension (.jsonl included)
    news_videos_NER_df = read_video_df(filepath).fillna("")
    news_videos_NER_df["ORG"] = news_videos_NER_df["ORG"].replace("/", "|", regex=True) \
                                                         .replace("-", "|", regex=True) \
                                                         .replace('LFP RN LR', "LFP|RN|LR")
    save_video_with_NER(news_videos_NER_df, filepath)


def clean_PER_column_manual(filepath):
    news_videos_NER_df = read_video_df(filepath)
    # change known PER issues
    news_videos_NER_df.loc[news_videos_NER_df.PER == 'Philippe Juvin J-L Mélenchon', "PER"] = 'Philippe Juvin|J-L Mélenchon'
    news_videos_NER_df = news_videos_NER_df.replace("Attal-", "Attal|", regex=True) \
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

    news_videos_NER_df.PER = news_videos_NER_df.PER.apply(lambda x: x.title())
    save_video_with_NER(news_videos_NER_df, filepath)


def clean_PER_column_w_dict(filepath):
    news_videos_NER_df = read_video_df(filepath)

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

    save_video_with_NER(news_videos_NER_df, filepath)


def add_PER_clean_to_origin_file(filename):
    news_videos_df = read_video_df(f"{filename}.jsonl")
    news_videos_df_PER = read_video_df(f"{filename}_NER.jsonl")
    assert len(news_videos_df_PER) == len(news_videos_df)
    news_videos_df = news_videos_df.merge(news_videos_df_PER[['id', 'PER_clean']], how='outer', on='id')
    save_video_with_NER(news_videos_df, f"{filename}.jsonl")

def add_parties(filename):
    news_videos_df = read_video_df(f"{filename}.jsonl")
    with open('data/dict/list_of_polit_from_parties.json') as f:
        polit_from_parties = json.load(f)
    polit2parties = {name: party for party, names in polit_from_parties.items() for name in names}
    print(polit2parties)
    news_videos_df['parties'] = news_videos_df['PER_clean'].apply(get_parties, args=(polit2parties,))
    save_video_with_NER(news_videos_df, f"{filename}.jsonl")

if __name__ == "__main__":
    filepath = "data/tiktok/videos/news_videos_2024.jsonl"
    filename, ext = os.path.splitext(filepath)

    get_NER = False
    clean_NER = False
    add_NER_to_origin = False
    add_parties_to_origin = True

    if get_NER:
        print("get NER")
        create_news_channels_videos_df_NER(filepath=filepath, platform='tiktok')

    if clean_NER:
        print("clean NER")
        clean_PER_column_manual(f"{filename}_NER{ext}")
        clean_PER_column_w_dict(f"{filename}_NER{ext}")

    if add_NER_to_origin:
        print("add NER to origin")
        add_PER_clean_to_origin_file(filename)

    if add_parties_to_origin:
        print("add parties to origin")
        add_parties(filename)