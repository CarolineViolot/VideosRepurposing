import json


def get_youtube_tiktok_equivalent_channels():
    with open("data/tiktok_youtube_equivalent_channels.json", "r") as f:
        res = json.load(f)
    return res


# ── Pipeline test ─────────────────────────────────────────────────────────────
# runs the scripts from tests/pipeline/ so that `scripts.project_config` resolves
# to this file (and data/ to tests/pipeline/data/). Only the values below differ:
# 2024 only, 5-7 July (2nd round of the legislative elections), one politician
# (Jean-Luc Mélenchon) and one news channel (BFMTV). The channels to collect come
# from tests/pipeline/data/{youtube,tiktok}/channels/, written by init_run.py.

YEARS = ["2024"]
CHANNEL_TYPES = ["news", "pp"]


def get_collect_periods():
    # (start, end) of the collection, end day excluded (on both platforms): 5, 6 and 7 July
    return {
        "2024": ("2024-07-05", "2024-07-08"),
    }


# Test channels by name_standard, used by init_run.py (channel files of both platforms) and compare_run.py
TEST_CHANNELS = {"pp": ["Jean-Luc Mélenchon"], "news": ["BFMTV"]}


def get_news_channel_type():
    return {
        # LEFT
        "L'Humanité": 'Press',
        'Le Média': 'Pure Player',
        'Mediapart': 'Pure Player',
        'Blast': 'Pure Player',

        # CENTER
        '28 minutes': 'TV',
        'AFP': 'Paper + TV',
        "C dans l'air": 'TV',
        'C à vous': 'TV',
        'FRANCE 24': 'TV',
        'France Inter': 'Radio',
        'LCP': 'TV',
        'Le Monde': 'Press',
        'Le Nouvel Obs': 'Press',
        'LeHuffPost': 'Press',
        'Marianne': 'Press',
        'Public Sénat': 'TV',
        'RFI': 'Radio',
        'RTL': 'Radio',
        'TV5MONDE Info': 'TV',
        'Euronews': 'TV',
        'franceinfo': 'Radio',
        'Libération': 'Press',

        # RIGHT
        'BFMTV': 'TV',
        'CNEWS': 'TV',
        'Europe 1': 'TV',
        "L'Express": 'Press',
        'LCI': 'TV',
        'Le Figaro': 'Press',
        'Le Parisien': 'Press',
        'Le Point': 'Press',
        'Les Echos': 'Press',
        'RMC': 'Radio',
        'Sud Radio': 'Radio',
        'TF1 INFO': 'TV',
        'VA Plus': 'Press',
    }


def get_channel_names_dict():
    with open('data/dict/channel_name2standard_name.json') as f:
        channel_name2standard_name = json.load(f)
    return channel_name2standard_name


def get_news_channel_orientation():
    return {
        # LEFT
        "L'Humanité": 'Left (news)',
        'Le Média': 'Left (news)',
        'Mediapart': 'Left (news)',
        'Blast': 'Left (news)',

        # CENTER
        '28 minutes': 'Center (news)',
        'AFP': 'Center (news)',
        "C dans l'air": 'Center (news)',
        'C à vous': 'Center (news)',
        'FRANCE 24': 'Center (news)',
        'France Inter': 'Center (news)',
        'LCP': 'Center (news)',
        'Le Monde': 'Center (news)',
        'Le Nouvel Obs': 'Center (news)',
        'LeHuffPost': 'Center (news)',
        'Marianne': 'Center (news)',
        'Public Sénat': 'Center (news)',
        'RFI': 'Center (news)',
        'RTL': 'Center (news)',
        'TV5MONDE Info': 'Center (news)',
        'Euronews': 'Center (news)',
        'franceinfo': 'Center (news)',
        'Libération': 'Center (news)',

        # RIGHT
        'BFMTV': 'Right (news)',
        'CNEWS': 'Right (news)',
        'Europe 1': 'Right (news)',
        "L'Express": 'Right (news)',
        'LCI': 'Right (news)',
        'Le Figaro': 'Right (news)',
        'Le Parisien': 'Right (news)',
        'Le Point': 'Right (news)',
        'Les Echos': 'Right (news)',
        'RMC': 'Right (news)',
        'Sud Radio': 'Right (news)',
        'TF1 INFO': 'Right (news)',
        'VA Plus': 'Right (news)',
          }


def get_party_orientation():
    return {'LO': 'Far Left', 'NPA':'Far Left',
            'LFI': 'Left', 'PCF': 'Left', 'PS': 'Left', 'EcoS': 'Left', 'EELV': 'Left', 'PP':'Left', 'DG':'Left',
            'RE': 'Center', 'MoDem': 'Center', 'UDI': 'Center', 'HOR': 'Center',
            'UPR': 'Right', 'LR': 'Right', 'DD':'Right',
            'DLF': 'Right', 'RN': 'Far Right', 'LP': 'Far Right', 'REC': 'Far Right',
            'autre':'Other'}


def get_politician2party():
    with open('data/dict/polit_account2party.json') as f:
        politician2party = json.load(f)
    return politician2party


def get_politician_abbr_name():
    return {'Emmanuel Macron': 'E. Macron', 'Florian Philippot': 'F. Philippot', 'François Ruffin': 'F. Ruffin',
            'François Asselineau': 'F. Asselineau', 'Jean-Luc Mélenchon': 'JL. Mélenchon',
            'Jordan Bardella': 'J. Bardella', 'Manon Aubry': 'M. Aubry', 'Manuel Bompard': 'M. Bompard',
            'Marine Le Pen': 'M. Le Pen', 'Marion Maréchal': 'M. Maréchal', 'Mathilde Panot': 'M. Panot',
            'Nicolas Dupont-Aignan': 'N. Dupont-Aignan', 'Rima Hassan': 'R. Hassan', 'Éric Zemmour': 'E. Zemmour',
            'Eric Ciotti': 'E. Ciotti', 'Gabriel Attal': 'G. Attal'}


def get_youtube2tiktok_channels():
    with open('data/dict/youtube2tiktok_channels.json') as f:
        youtube2tiktok_channels = json.load(f)
    return youtube2tiktok_channels

