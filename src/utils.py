import numpy as np
import requests
import os
import re
from datetime import timedelta
import googleapiclient.discovery
import html
from tqdm import tqdm
import pandas as pd
import time
from dotenv import load_dotenv
from engineering_notation import EngNumber
from matplotlib.ticker import EngFormatter

load_dotenv()

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]

formatter_engineer = EngFormatter(places=0, sep="")

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


def highlight_max(s):
    is_max = s == s.max()
    return [f'font-weight: bold' if v else '' for v in is_max]


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


def is_short(ID, timeout=30):
    """True if the video is a Short, False if not, NaN if YouTube reports it unavailable.
    Raises a requests.RequestException (e.g. Timeout) if YouTube can't be reached."""
    x = requests.get(
        "https://consent.youtube.com/ml?continue=https://www.youtube.com/shorts/{}?cbrd%3D1&gl=CH&hl=de&pc=yt&uxe=eomty&src=1".format(
            ID), timeout=timeout)
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
            "youtube", "v3", developerKey=YOUTUBE_API_KEY)

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
