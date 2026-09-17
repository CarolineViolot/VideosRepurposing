import requests
import json
import time
import os
from datetime import datetime, timedelta
import pandas as pd
from src.utils import get_election_periods

if os.path.isdir("../data/"):
    os.chdir("../")

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

CLIENT_KEY    = "***REMOVED***"
CLIENT_SECRET = "***REMOVED***"

collection_periods = get_election_periods()

FIELDS = ",".join([
    "id", "create_time", "username", "region_code",
    "video_description", "music_id", "like_count",
    "comment_count", "share_count", "view_count", "favorites_count",
    "effect_info_list", "hashtag_names",
    "video_duration", "voice_to_text"
])

BASE_URL   = "https://open.tiktokapis.com/v2/research/video/query/"
MAX_COUNT  = 100


# ─── AUTH ─────────────────────────────────────────────────────────────────────

def get_access_token() -> str:
    r = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
        },
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
    )
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise ValueError(f"Token not received: {r.json()}")
    return token


# ─── DATE WINDOWING ───────────────────────────────────────────────────────────

def date_windows(start: str, end: str, window_days: int = 30):
    """Split a date range into chunks of at most window_days (API limit)."""
    fmt = "%Y-%m-%d"
    cur = datetime.strptime(start, fmt)
    fin = datetime.strptime(end, fmt)
    while cur < fin:
        nxt = min(cur + timedelta(days=window_days - 1), fin)
        yield cur.strftime("%Y%m%d"), nxt.strftime("%Y%m%d")
        cur = nxt + timedelta(days=1)


# ─── LOAD EXISTING DATA ───────────────────────────────────────────────────────

def load_existing_videos(output_json) -> list[dict]:
    """Load existing videos from JSON or CSV if present."""
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


# ─── FETCH ────────────────────────────────────────────────────────────────────

def fetch_window(token: str, username: str, start: str, end: str, fields = FIELDS) -> list[dict]:
    """Fetch all videos for a user within a single 30-day window, handling pagination."""
    url = f"{BASE_URL}?fields={fields}"
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


def fetch_user(token: str, username: str, year: str) -> list[dict]:
    """Fetch all videos for a user across the full date range."""
    all_videos = []
    start_date, end_date = collection_periods[year]

    for start, end in date_windows(start=start_date, end=end_date):
        print(start, end)
        print(f"  {username}: {start} -> {end}")
        all_videos.extend(fetch_window(token, username, start, end))
    return all_videos

# ─── EXPORT ───────────────────────────────────────────────────────────────────

def save(videos: list[dict], output_json) -> None:
    if not videos:
        print("No videos to save.")
        return

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=4)

    print(f"Saved {len(videos)} unique videos to {output_json}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    year = "2022"
    channel_type = "news"
    output_json = f"data/tiktok/videos/{channel_type}_videos_{year}.json"
    # Load existing data first
    existing_videos = load_existing_videos(output_json=output_json)
    existing_channels = get_existing_channels(existing_videos)

    print(f"Channels already in file: {sorted(existing_channels)}")
    with open(f"data/tiktok/channels/{channel_type}_channels.json", "r") as f:
        channel_ids = list(json.load(f)['channels'].keys())
        print(channel_ids)

    # Only collect channels not already present
    channels_to_collect = [ch for ch in channel_ids if ch not in existing_channels]

    if not channels_to_collect:
        print("All channels already exist in the file. Nothing to collect.")
        return

    print(f"Channels to collect: {channels_to_collect}")

    token = get_access_token()
    new_videos = []

    all_videos = existing_videos

    for username in channels_to_collect:
        try:
            vids = fetch_user(token, username, year)
            print(f"@{username}: {len(vids)} videos collected")
            new_videos.extend(vids)
            all_videos = all_videos + new_videos
            save(all_videos, output_json=output_json)
            new_videos = []
        except Exception as e:
            all_videos = all_videos + new_videos
            save(all_videos, output_json=output_json)
            print(f"@{username} failed: {e}")

    # Merge old + new
    all_videos = all_videos + new_videos
    save(all_videos, output_json=output_json)


if __name__ == "__main__":
    main()