import datetime
import json
import numpy as np
import requests
import os
import re
from datetime import timedelta
import googleapiclient.discovery
import pickle
import html
from tqdm import tqdm
import pandas as pd
import time
from engineering_notation import EngNumber
from matplotlib.ticker import EngFormatter

def get_youtube_tiktok_equivalent_channels():
    with open("data/tiktok_youtube_equivalent_channels.json", "r") as f:
        res = json.load(f)
    return res

def get_election_periods():
    return {
        "2022": ("2022-02-11", "2022-06-26"),
        "2024": ("2024-03-01", "2024-07-14"),
    }

def create_youtube_client(APIkey):
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    api_service_name = "youtube"
    api_version = "v3"
    return googleapiclient.discovery.build(
        api_service_name, api_version, developerKey=APIkey)


def compact_sci(num, precision=1):
    sci = f"{num:.{precision}e}"
    return sci.replace('e-0', 'e-').replace('e+0', 'e+').replace('e+', 'e')


def eng_format(x):
    if x < 1000:
        return str(EngNumber(x, precision=1))
    eng_number = str(EngNumber(x, precision=1))
    if len(eng_number[:-1].replace(".", "")) < 4:
        return str(EngNumber(x, precision=1))
    return str(EngNumber(x, precision=0))


def eng_format0(x):
    return str(EngNumber(x, precision=1))


def eng_format00(x):
    return str(EngNumber(x, precision=0))


def my_format(x):
    if float(int(x)) == x and x < 1000:
        return int(x)
    if x < 10:
        return f"{x:.2f}"
    if x<100:
        return f"{x:.1f}"
    if x < 1000:
        return str(EngNumber(np.round(x), precision=0))

    eng_number = str(EngNumber(x, precision=1))
    if len(eng_number[:-1].replace(".", "")) < 4:
        return str(EngNumber(x, precision=1))
    return str(EngNumber(x, precision=0))


formatter_engineer = EngFormatter(places=0, sep="")


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

def get_tt_username2display_name():
    with open('data/dict/tt_username2display_name.json') as f:
        tt_username2display_name = json.load(f)
    return tt_username2display_name

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

def readAPIkey():
    with open("data/keys/APIkey_true", 'r') as f:
        api_keys = f.read().splitlines()
        return api_keys[0]


def read_db_pass():
    with open("data/keys/db_pass", 'r') as f:
        db_pass = f.read().splitlines()
        return db_pass[0]


def highlight_max(s):
    is_max = s == s.max()
    return [f'font-weight: bold' if v else '' for v in is_max]


def save_search_query_results(query_result, year_month="", year=None, week=None, category="noCategory"):
    now = datetime.datetime.now()
    if week is not None:
        folder = "dataset1/json/videoSearchResults/rawResults/{}_week_{}/{}/".format(year, week, category)
        if not os.path.isdir(folder):
            if not os.path.isdir("dataset1/json/videoSearchResults/rawResults/{}_week_{}/".format(year, week)):
                os.mkdir("dataset1/json/videoSearchResults/rawResults/{}_week_{}/".format(year, week))
            os.mkdir(folder)
    filename = "shorts{}_scrapped_at_{}.json".format(year_month, now)
    with open(folder + filename, "w") as f:
        json.dump(query_result, f, indent=4)


def save_comment_query_results(query_result, video_id, folder="data/comments"):
    now = datetime.datetime.now()
    filename = "comments_from_{}_scrapped_at_{}.json".format(video_id, now)
    with open(os.path.join(folder, filename), "w") as f:
        json.dump(query_result, f, indent=4)


def save_short_query_results(query_result, year_month="", folder="dataset1/json/shortResults/", year=None, week=None,
                             category="noCategory"):
    now = datetime.datetime.now()
    if week is not None:
        folder = "dataset1/json/shortResults/rawResults/{}_week_{}/{}/".format(year, week, category)
        if not os.path.isdir(folder):
            if not os.path.isdir("dataset1/json/shortResults/rawResults/{}_week_{}/".format(year, week)):
                os.mkdir("dataset1/json/shortResults/rawResults/{}_week_{}/".format(year, week))
            os.mkdir(folder)
    filename = "shorts{}_scrapped_at_{}.json".format(year_month, now)
    with open(folder + filename, "w") as f:
        json.dump(query_result, f, indent=4)


def ISO8601_duration_to_sec(iso_duration):
    """Parses an ISO 8601 duration string into a datetime.timedelta instance.
    Args:
        iso_duration: an ISO 8601 duration string.
    Returns:
        a datetime.timedelta instance
    """
    if type(iso_duration) == float:
        print(iso_duration)
        return 0
    try:
        m = re.match(r'^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:.\d+)?)S)?$',
                 iso_duration)
    except BaseException as e:
        print(iso_duration)
        raise e
    if m is None:
        print("invalid ISO 8601 duration string:", iso_duration)
        return 0

    days = 0
    hours = 0
    minutes = 0
    seconds = 0

    if m[3]:
        days = int(m[3])
    if m[4]:
        hours = int(m[4])
    if m[5]:
        minutes = int(m[5])
    if m[6]:
        seconds = float(m[6])

    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds).total_seconds()


def is_short(ID):
    x = requests.get(
        "https://consent.youtube.com/ml?continue=https://www.youtube.com/shorts/{}?cbrd%3D1&gl=CH&hl=de&pc=yt&uxe=eomty&src=1".format(
            ID))
    if '"playabilityStatus":{"status":"ERROR",' in x.text:
        return np.nan
    if "/shorts/" in x.url:
        return True
    return False


def str_in_list(str_sub, str_list):
    return True in [str_sub in str_list_i for str_list_i in str_list]


def contains_link(comment):
    # with valid conditions for urls in string
    regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    url = re.findall(regex, comment)
    if len(url) > 0:
        return True
    return False


def get_links(comment):
    regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    url = re.findall(regex, comment)
    if len(url) > 0:
        return [u[0] for u in url]
    return False


def get_YT_category_guide(refresh=False):
    if refresh:
        youtube = googleapiclient.discovery.build(
            "youtube", "v3", developerKey=readAPIkey())

        request = youtube.videoCategories().list(
            part="snippet",
            id=",".join([str(e) for e in list(np.arange(50))])
        )
        response = request.execute()
        return {item["id"]: item["snippet"]["title"] for item in response["items"]}
    else:
        return {'1': 'Film & Animation', '2': 'Autos & Vehicles', '10': 'Music',
                '15': 'Pets & Animals', '17': 'Sports', '18': 'Short Movies',
                '19': 'Travel & Events', '20': 'Gaming', '21': 'Videoblogging',
                '22': 'People & Blogs', '23': 'Comedy', '24': 'Entertainment',
                '25': 'News & Politics', '26': 'Howto & Style', '27': 'Education',
                '28': 'Science & Technology', '29': 'Nonprofits & Activism', '30': 'Movies',
                '31': 'Anime/Animation', '32': 'Action/Adventure', '33': 'Classics',
                '34': 'Comedy', '35': 'Documentary', '36': 'Drama', '37': 'Family',
                '38': 'Foreign', '39': 'Horror', '40': 'Sci-Fi/Fantasy', '41': 'Thriller',
                '42': 'Shorts', '43': 'Shows', '44': 'Trailers'}


def get_YT_categories(categoryId):
    YT_category_guide = get_YT_category_guide()
    try:
        return YT_category_guide[str(int(categoryId))]
    except KeyError as e:
        return np.nan
    except ValueError as e:
        return np.nan


def remove_breaklines(text):
    # used to clean comments and usernames
    chars = ["\n", "\r", "<br>", "</br>", "<b>", "</b>"]
    if type(text) == float:
        return text
    try:
        for c in chars:
            text = text.replace(c, ". ")
    except AttributeError as e:
        print(text)
        raise (e)
    text = html.unescape(text)
    text = " ".join(text.split())
    return text


def video_deletion_status(availability_status, videoId):
    if availability_status == "Available":
        return "Available"
    x = requests.get("https://www.youtube.com/watch?v={}".format(videoId))
    if "Dieses Video ist nicht mehr verfügbar, weil das mit diesem Video verknüpfte YouTube-Konto gekündigt wurde" in x.text:
        return "deleted channel"
    elif "Dieses Video wurde vom Uploader entfernt" in x.text:
        return "video removed by Creator"
    elif "Dieses Video ist nicht mehr verfügbar" in x.text:
        return "deleted video"
    elif "Dieses Video ist aufgrund eine Beschwerde wegen Urheberrechtsverletzung von" in x.text:
        return "deleted copyright issues"
    elif "Dieses Video ist privat. Melde dich bitte an, um zu prüfen, ob du es ansehen kannst" in x.text:
        return "private video"
    elif "Dieses Video wurde entfernt, weil es gegen die Community-Richtlinien von YouTube verstößt" in x.text:
        return "deleted community guideline issue"
    elif "Dieses Video wurde entfernt, weil es gegen die YouTube-Richtlinien zu Nacktheit und sexuellen Inhalt" in x.text:
        return "deleted nudity"
    else:
        return "Available"


def merge_and_save(folder, files):
    """
    input : list of csv files in the folder, the list has to be provided as not all
    .csv files should be used
    """
    header = True

    # Define the chunk size
    chunk_size = 100000

    for file in tqdm(files):
        for chunk in pd.read_csv(folder + file + ".csv", chunksize=chunk_size):
            chunk.to_csv(folder + "merged_data.csv", mode='a', header=header, index=False)
            header = False


def plot_election_days(ax, start_zero=True, Short_tick_index="2021-W11"):
    if start_zero:
        ax.plot([Short_tick_index, Short_tick_index], [0, 0.9 * ax.get_ylim()[1]], color="black", alpha=0.3)
    else:
        ax.plot([Short_tick_index, Short_tick_index], [1.01 * ax.get_ylim()[0], 0.99 * ax.get_ylim()[1]], color="black",
                alpha=0.3)


def add_election_days(ax, start_zero=True, add_bar=True, step_week=17):
    if add_bar:
        plot_election_days(ax, start_zero)
    short_week = "2021-W11"
    short_tickindex = [text_object.get_text() for text_object in ax.get_xticklabels()].index(short_week)

    ax.set_xticks([xtick.get_position()[0] for xtick in ax.get_xticklabels()][0::step_week] + [short_tickindex],
                  [week_to_month_dict[xtick.get_text()] for xtick in ax.get_xticklabels()][0::step_week] +
                  ["Shorts Int."], rotation=45, ha='right', rotation_mode='anchor')


def custom_ticks(ax, step=3):
    ax.set_xticks([xtick.get_position()[0] for xtick in ax.get_xticklabels()][0::step],
                  [week_to_month_dict[xtick.get_text()] for xtick in ax.get_xticklabels()][0::step], rotation=45,
                  ha='right', rotation_mode='anchor')


def short_intro_box(x, y, ax, t="Shorts \n intro"):
    ax.text(x, y, t, horizontalalignment='center',
            bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))


def time_usage(func):
    def wrapper(*args, **kwargs):
        beg_ts = time.time()
        retval = func(*args, **kwargs)
        end_ts = time.time()
        print("elapsed time: %f" % (end_ts - beg_ts))
        return retval

    return wrapper


def append_if_exists_save_otherwise(df, df_filename, logger):
    if os.path.isfile(df_filename):
        logger.warning(f"File {df_filename} already exists, appending...")
        df.to_csv(df_filename, index=False, header=False, mode='a')
    else:
        df.to_csv(df_filename, index=False)
