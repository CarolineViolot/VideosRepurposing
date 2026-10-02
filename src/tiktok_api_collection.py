"""
Generic TikTok Research API helpers: auth, channel/user info, and video fetching.
Reusable across any TikTok Research API project -- no project-specific values.
"""
import json
import os
import time
from datetime import datetime, timedelta

import requests

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
BASE_URL = "https://open.tiktokapis.com/v2"
VIDEO_QUERY_URL = "https://open.tiktokapis.com/v2/research/video/query/"
MAX_COUNT = 100

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

VIDEO_FIELDS = ",".join([
    "id", "create_time", "username", "region_code",
    "video_description", "music_id", "like_count",
    "comment_count", "share_count", "view_count", "favorites_count",
    "effect_info_list", "hashtag_names",
    "video_duration", "voice_to_text"
])


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_access_token(client_key: str, client_secret: str) -> str:
    """Obtain a client credentials access token from TikTok."""
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
        },
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    token = data.get("access_token")
    if not token:
        raise ValueError(f"No access_token in response: {data}")

    print(f"[Auth] Access token obtained (expires in {data.get('expires_in')}s)")
    return token


# ── User / channel info ───────────────────────────────────────────────────────

def fetch_user_info(username: str, token: str) -> dict:
    """Fetch profile information for a single TikTok username via /research/user/info/."""
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
    return resp.json().get("data", {})


def read_channels_file(path) -> dict:
    """{username: info} from a channel file, either as written by the collector
    ({"channels": {username: {...}}}) or as a list of records with a 'username' key."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data["channels"]
    return {row["username"]: {k: v for k, v in row.items() if k != "username"} for row in data}


def load_existing_channels(output_file) -> dict:
    """Load previously collected channel info, dropping entries missing API fields."""
    required_columns = ["display_name", "follower_count", "following_count", "is_verified",
                         "likes_count", "video_count", "bio_description", "collected_at"]
    channels = read_channels_file(output_file)
    return {username: info for username, info in channels.items()
            if set(required_columns) <= set(info.keys())}


# ── Date windowing ────────────────────────────────────────────────────────────

def date_windows(start: str, end: str, window_days: int = 30):
    """Split a date range into chunks of at most window_days (API limit)."""
    fmt = "%Y-%m-%d"
    cur = datetime.strptime(start, fmt)
    fin = datetime.strptime(end, fmt)
    while cur < fin:
        nxt = min(cur + timedelta(days=window_days - 1), fin)
        yield cur.strftime("%Y%m%d"), nxt.strftime("%Y%m%d")
        cur = nxt + timedelta(days=1)


# ── Videos ────────────────────────────────────────────────────────────────────

def fetch_window(token: str, username: str, start: str, end: str, fields=VIDEO_FIELDS) -> list[dict]:
    """Fetch all videos for a user within a single 30-day window, handling pagination."""
    url = f"{VIDEO_QUERY_URL}?fields={fields}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    videos = []
    cursor = 0
    has_more = True
    search_id = ""

    while has_more:
        body = {
            "query": {
                "and": [
                    {"operation": "EQ", "field_name": "username", "field_values": [username]}
                ]
            },
            "start_date": start,
            "end_date": end,
            "max_count": MAX_COUNT,
            "cursor": cursor,
        }

        if search_id:
            body["search_id"] = search_id

        r = requests.post(url, headers=headers, data=json.dumps(body))

        if r.status_code == 429:
            print("Rate limit reached, waiting 60s...")
            time.sleep(60)
            continue

        if not r.ok:
            print(f"HTTP {r.status_code}: {r.text}")
            break

        data = r.json()
        if data.get("error", {}).get("code") != "ok":
            print(f"API error: {data.get('error')}")
            break

        batch = data["data"].get("videos", [])
        has_more = data["data"].get("has_more", False)
        cursor = data["data"].get("cursor", 0)
        search_id = data["data"].get("search_id", "")

        videos.extend(batch)
        time.sleep(1)

    return videos


def fetch_user(token: str, username: str, start_date: str, end_date: str) -> list[dict]:
    """Fetch all videos for a user across a full date range (YYYY-MM-DD strings)."""
    all_videos = []
    for start, end in date_windows(start=start_date, end=end_date):
        print(start, end)
        print(f"  {username}: {start} -> {end}")
        all_videos.extend(fetch_window(token, username, start, end))
    return all_videos


def fetch_existing_video_ids(token: str, video_ids: list[str], start: str, end: str) -> set[str]:
    """
    Return the ids among *video_ids* that the Research API still returns, for videos
    created between *start* and *end* (YYYYMMDD, both included, at most 30 days apart).
    API errors are raised, never taken as "unavailable".
    """
    url = f"{VIDEO_QUERY_URL}?fields=id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    found = set()
    for i in range(0, len(video_ids), MAX_COUNT):
        batch = [str(v) for v in video_ids[i:i + MAX_COUNT]]
        cursor, search_id, has_more = 0, "", True
        while has_more:
            body = {
                "query": {"and": [{"operation": "IN", "field_name": "video_id", "field_values": batch}]},
                "start_date": start,
                "end_date": end,
                "max_count": MAX_COUNT,
                "cursor": cursor,
            }
            if search_id:
                body["search_id"] = search_id

            r = requests.post(url, headers=headers, data=json.dumps(body))
            if r.status_code == 429:
                print("Rate limit reached, waiting 60s...")
                time.sleep(60)
                continue
            if not r.ok:
                raise RuntimeError(f"TikTok Research API HTTP {r.status_code}: {r.text}")
            data = r.json()
            if data.get("error", {}).get("code") != "ok":
                raise RuntimeError(f"TikTok Research API error: {data.get('error')}")

            found |= {str(v["id"]) for v in data["data"].get("videos", [])}
            has_more = data["data"].get("has_more", False)
            cursor = data["data"].get("cursor", 0)
            search_id = data["data"].get("search_id", "")
            time.sleep(1)
    return found


def load_existing_videos(output_json) -> list[dict]:
    """Load existing videos from a JSON file if present."""
    if os.path.exists(output_json):
        print(f"Loading existing JSON: {output_json}")
        with open(output_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    print("No existing file found, starting fresh.")
    return []


def get_existing_channels(videos: list[dict]) -> set[str]:
    """Return the set of usernames already present in the saved file."""
    channels = set()
    for v in videos:
        username = v.get("username")
        if username:
            channels.add(str(username))
    return channels


def save(videos: list[dict], output_json) -> None:
    if not videos:
        print("No videos to save.")
        return

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=4)

    print(f"Saved {len(videos)} unique videos to {output_json}")