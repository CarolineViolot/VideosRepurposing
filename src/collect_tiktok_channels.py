import json
import time
import requests
import os
from datetime import datetime
from src.collect_tiktok_videos import date_windows, fetch_window

if os.path.isdir("../data/"):
    os.chdir("../")

CLIENT_KEY = "***REMOVED***"
CLIENT_SECRET = "***REMOVED***"

# Fields to request for each user (Research API v2)
USER_FIELDS = [
    "display_name",
    "bio_description",
    "is_verified",
    "follower_count",
    "following_count",
    "likes_count",
    "video_count",
]

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
BASE_URL = "https://open.tiktokapis.com/v2"


def get_access_token() -> str:
    """Obtain a client credentials access token from TikTok."""
    payload = {
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    resp = requests.post(TOKEN_URL, data=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    token = data.get("access_token")
    if not token:
        raise ValueError(f"No access_token in response: {data}")

    print(f"[Auth] Access token obtained (expires in {data.get('expires_in')}s)")
    return token


# ─────────────────────────────────────────────
#  USER / CHANNEL INFO
# ─────────────────────────────────────────────
def fetch_oldest_video(username: str, token: str) -> dict | None:
    """
    Fetch the oldest available video for a TikTok channel.
    Walks forward in 30-day windows from TikTok's launch until a video is found.
    """
    fields = ",".join(["id", "create_time"])
    start_date = "2018-04-01"
    end_date = "2024-01-01"
    year = start_date[0:4]
    for start, end in date_windows(start=start_date, end=end_date):
        if start[0:4] != year:
            print(year)
            year = start[0:4]
        res = fetch_window(token, username, start, end, fields=fields)
        if res:
            return min([e["create_time"] for e in res])
    return None


def fetch_user_info(username: str, token: str) -> dict:
    """
    Fetch profile information for a single TikTok username.
    Uses the Research API /user/info/ endpoint.
    """
    url = f"{BASE_URL}/research/user/info/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    params = {
        "fields": ",".join(USER_FIELDS),
    }
    body = {"username": username}

    resp = requests.post(url, headers=headers, params=params, json=body, timeout=30)

    if resp.status_code == 429:
        print(f"  [Rate limit] Sleeping 60s before retrying {username}…")
        time.sleep(60)
        return fetch_user_info(username, token)

    resp.raise_for_status()
    result = resp.json()
    return result.get("data", {})


def collect_info(username: str, token: str) -> dict:
    """
    Collect data for every channel in the list.
    Returns a dict keyed by username.
    """
    # 1. User profile
    user_info = {}
    try:
        user_info = fetch_user_info(username, token)
        print(f"  ✓ User info fetched")
    except Exception as exc:
        print(f"  ✗ User info failed: {exc}")
    # 2. Oldest video
    #try:
    #    user_info['oldest_video'] = fetch_oldest_video(username, token)
    #except Exception as exc:
    #    print(f"  ✗ User info failed: {exc}")
    #    raise exc
    return user_info

def load_existing_channels(output_file):
    required_columns = ["display_name", "follower_count", "following_count", "is_verified",
      "likes_count", "video_count", "bio_description", "collected_at"]
    with open(output_file) as f:
        data = json.load(f)
    for channel in data['channels']:
        if set(required_columns) != set(data['channels'][channel].keys()):
            data['channels'].pop(channel)
    return data


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

def main():
    channel_type = "pp"
    if channel_type == "pp":
        channel_ids = [
            "reconqueteofficiel", "zemmour_eric", "sarah_knafo", "marion_marechal",
            "rnational_off", "jordanbardella", "mlp.officiel", "sebchenu", "julienodoul", "louis_aliot", "jphtanguy",
            "david.rachline", "edwige_diaz", "laurelavalette", "jsanchez_rn", "franckallisio", "laurentjacobelli",
            "matthieu_valet", "fabriceleggeri", "philippe_ballard",
            "eciotti",
            "lesrepublicains", "laurentwauquiez_", "brunoretailleauoff", "fxbellamy", "rachida_dati",
            "horizonsleparti", "parti_renaissance", "emmanuelmacron", "gabriel_attal", "edouardphillippe_2027",
            "gdarmanin.officiel", "olivierveran", "karl.olive", "marleneschiappa", "prisca_thevenot", "aurore_berge",
            "yaelbraunpivet",
            "ppjeunes", "partisocialiste", "fhollandeofficiel", "faure_olivier", "jerome_guedj", "borisvallaud",
            "lesecologistes", "marinetondelier", "sandrousseau", "yjadot", "marie.touss1",
            "franceinsoumisean", "jlmelenchon", "manonaubryfr", "rima.has", "mathildepanot", "manuelbompard",
            "guetteclemence", "francois_ruffin", "clementine_autain", "louisboyard", "sebastiendelogu", "alma_dufour",
            "alexis_corbiere", "deputee_obono", "eric.coquerel", "bastien.lachaud", "garrido.raquel", "thomas_portes",
            "david_guiraud", "rachel.keke.officiel", "raphael_arnault",
            "particommuniste", "fabien_roussel", "ianbrossatsenateur", "leondeffontaines",
            "npa.anticapitaliste", "lutteouvriereofficiel", "olivier.besancenot", "philippe.poutou", "nathaliearthaud",
            "dominiquedevillepin", "dupontaignannicolas", "florianphilippot", "fasselineau", "uprtvfa", "aymeric.caron"
        ]
    elif channel_type == "news":
        channel_ids = [
            "artefr", "afpfr", "bfmtv", "blast_officiel", "cdanslairofficiel.365", "c_a_vous", "cnews", "europe1",
            "france24", "france.inter", "lhumanitefr", "lexpress", "lcp_an", "lefigaro", "lemondefr", "lemediatv",
            "nouvelobs", "leparisien", "lepointfr", "lehuffpostfr", "lesechos.fr", "mariannelemag", "mediapartfr",
            "publicsenat", "rfi", "rmc_off", "rtl.officiel", "sudradio", "tf1info", "tv5monde", "va.plus",
            "franceinfo", "liberation.fr"
        ]
    output_file = f"data/tiktok/channels/{channel_type}_channels.json"
    # Authenticate
    token = get_access_token()

    # Load previously collected channels data
    if os.path.exists(output_file):
        results = load_existing_channels(output_file)
    else:
        results = {}

    # Collect data
    for idx, username in enumerate(channel_ids, start=1):
        print(f"\n[{idx}/{len(channel_ids)}] Collecting data for: @{username}")
        user_info = collect_info(username, token)
        results[username] = user_info
        results[username]["collected_at"] = datetime.date(datetime.now()).strftime(format="%y-%m-%d")
        output = {
            "total_channels": len(results),
            "channels": results,
        }
        # Save to JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
