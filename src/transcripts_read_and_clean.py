import json
import pandas as pd
import re
import unicodedata


def read_transcript_json(filepath):
    with open(filepath, 'r') as f:
        transcripts = json.load(f)
    transcripts = pd.DataFrame.from_dict(transcripts, 'index').reset_index().rename(
        columns={'index': 'videoId', 0: 'transcript'})
    # remove breaklines
    for col in transcripts.columns:
        if transcripts[col].dtype == 'object':
            transcripts[col] = transcripts[col].str.replace(r'[\n\r\x0b\x0c]+', ' ', regex=True)
    return transcripts


def clean_transcripts(transcript):
    BRACKET_TAGS = [
        r"musique", r"music", r"applaudissements?", r"applause", r"rires?", r"rire",
        r"sifflements?", r"bruit[s]?", r"silence", r"inaudible", r"coupe", r"transition",
        r"jingle", r"bip"
    ]

    OPENERS = {
        "bonjour", "bonsoir", "salut", "bienvenue", "merci", "au revoir", "à bientôt", "a bientôt",
        "bonne soirée", "bonne journée"
    }

    # If you use spaCy for French lemmatization, uncomment:
    # import spacy
    # nlp = spacy.load("fr_core_news_md")

    def strip_accents(s: str) -> str:
        return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


    # unify whitespace + lowercase
    t = transcript.replace("\u200b", " ").lower()
    t = strip_accents(t)

    # remove timestamps
    t = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", t)

    # remove bracketed tags like [musique], (applaudissements), <rire>
    tag_pattern = r"[\[\(\<]\s*(?:{})(?:\s*[:\-–]\s*\w+)?\s*[\]\)\>]".format("|".join(BRACKET_TAGS))
    t = re.sub(tag_pattern, " ", t, flags=re.IGNORECASE)

    # tokenization (simple)
    tokens = [tok for tok in t.split() if tok]

    # remove fillers and openers (single/multiword)
    # first remove multiword phrases greedily
    joined = " ".join(tokens)
    for phrase in sorted([*OPENERS], key=len, reverse=True):
        p = re.escape(strip_accents(phrase))
        joined = re.sub(rf"\b{p}\b", " ", joined)
    tokens = [tok for tok in joined.split() if tok]

    # final collapse
    out = re.sub(r"\s+", " ", " ".join(tokens)).strip()
    return out
