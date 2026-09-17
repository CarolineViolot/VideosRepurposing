import yt_dlp
import os
import json

from datetime import datetime
if os.path.isdir("../data/"):
    os.chdir("../")

USERS = ["user1", "user2", "user3"]
DATE_FROM = "20240101"  # YYYYMMDD
DATE_TO   = "20240331"

ydl_opts = {
    "quiet": True,
    "extract_flat": False,         # Full metadata per post
    "no_download": True,
    "sleep_interval": 5,           # Be polite to avoid rate limits
    "max_sleep_interval": 10,
}

results = []

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    for user in USERS:
        url = f"https://www.instagram.com/{user}/"
        try:
            info = ydl.extract_info(url, download=False)
            entries = info.get("entries", [])
            for entry in entries:
                if entry is None:
                    continue
                results.append({
                    "user":         entry.get("uploader"),
                    "post_id":      entry.get("id"),
                    "url":          entry.get("webpage_url"),
                    "date":         entry.get("upload_date"),
                    "description":  entry.get("description"),
                    "view_count":   entry.get("view_count"),
                    "like_count":   entry.get("like_count"),
                    "comment_count":entry.get("comment_count"),
                    "duration":     entry.get("duration"),
                    "thumbnail":    entry.get("thumbnail"),
                })
        except Exception as e:
            print(f"Failed for {user}: {e}")

# Save to JSON
import json
with open("data/instagram/channels/instagram_metadata.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"Collected {len(results)} posts")