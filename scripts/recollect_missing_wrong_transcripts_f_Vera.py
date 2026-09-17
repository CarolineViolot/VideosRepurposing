import os
import json
import time
import pandas as pd
from tqdm import tqdm
from youtube_transcript_api.proxies import GenericProxyConfig
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

if os.path.isdir("../data/"):
    os.chdir("../")

from src.transcripts_collection import transcript_to_text

# -----------------------------
# Config
# -----------------------------
proxy_config = GenericProxyConfig(
    http_url="http://***REMOVED***@proxy.smartproxy.net:3120",
    https_url="http://***REMOVED***@proxy.smartproxy.net:3120"
)

ytt_api = YouTubeTranscriptApi(proxy_config=proxy_config)

INPUT_COL = "videoId"
OUTPUT_FILE = "data/youtube/transcripts/transcript_metadata.jsonl"
CHECKPOINT_EVERY = 1000
SLEEP_EVERY = 100
SLEEP_SECONDS = 2

def clean_vera_json():
    # read raw jsons
    vera_transcript_1 = pd.read_json('data/youtube/transcripts/news_transcripts_Vera.json')
    vera_transcript_2 = pd.read_json('data/youtube/transcripts/news_transcripts_Vera_2.json')

    # keep only video and text columns and save it
    with open('data/youtube/transcripts/news_transcripts_Vera.json', 'w') as f:
        json.dump(dict(zip(vera_transcript_1['video_id'], vera_transcript_1['text'])), f)
    with open('data/youtube/transcripts/news_transcripts_Vera_2json', 'w') as f:
        json.dump(dict(zip(vera_transcript_2['video_id'], vera_transcript_2['text'])), f)

    # load again the saved data
    with open('data/youtube/transcripts/news_transcripts_Vera.json') as f:
        vera_transcript_1 = json.load(f)
    with open('data/youtube/transcripts/news_transcripts_Vera_2.json') as f:
        vera_transcript_2 = json.load(f)

    # put it in dataframe with two columns, videoId and transcript
    vera_transcript_1_df = pd.DataFrame.from_dict(vera_transcript_1, orient='index').reset_index().rename(columns={
        'index': 'videoId', 0: 'transcript'
    })
    vera_transcript_2_df = pd.DataFrame.from_dict(vera_transcript_2, orient='index').reset_index().rename(columns={
        'index': 'videoId', 0: 'transcript'
    })

    # merge the two df on videoId to compare the transcripts when both df contains the same videoId
    merged_transcripts = vera_transcript_1_df.merge(vera_transcript_2_df, on='videoId', how='inner',
                                                    suffixes=('_1', '_2'))
    merged_transcripts['same_transcript'] = merged_transcripts['transcript_1'] == merged_transcripts['transcript_2']

    # after verification, transcripts that are in both are nan in vera_transcript_2_df so remove them
    videos_to_remove = list(set(merged_transcripts[merged_transcripts['same_transcript'] == False]['videoId']))

    vera_transcript_2_df = vera_transcript_2_df[
        (~vera_transcript_2_df.videoId.isin(videos_to_remove)) & (vera_transcript_2_df.transcript != '')]


    videos_set_1 = set(vera_transcript_1_df.videoId)
    videos_set_2 = set(vera_transcript_2_df.videoId)
    only_in_1 = videos_set_1 - videos_set_2
    only_in_2 = videos_set_2 - videos_set_1
    in_both = videos_set_1.intersection(videos_set_2)

    # keep transcripts that are only in 1 or only in 2 and when in both take them from 1
    all_transcripts = pd.concat([vera_transcript_1_df[vera_transcript_1_df.videoId.isin(only_in_1)],
                                 vera_transcript_2_df[vera_transcript_2_df.videoId.isin(only_in_2)],
                                 vera_transcript_1_df[vera_transcript_1_df.videoId.isin(in_both)]])

    # keep only videoIds which are in our time period (Vera's one was much larger)
    news_videos_2024 = pd.read_csv('data/youtube/videos/news_videos_2024.csv')
    all_transcripts = all_transcripts[all_transcripts.videoId.isin(set(news_videos_2024.videoId))]

    # save ton jsonl
    all_transcripts[['videoId', 'transcript']].to_json(
        "data/youtube/transcripts/news_transcripts_Vera_clean.jsonl", orient='records', lines=True)


def fetch_auto_transcript(video_id: str) -> str | None:

    try:
        transcript_list = ytt_api.list(video_id)

    except TranscriptsDisabled:
        print(f"  [SKIP] {video_id} — transcripts disabled")
        return "[transcripts_disabled]"
    except Exception as e:
        print(f"  [ERROR] {video_id} — {e}")
        print(f"verify video at https://www.youtube.com/watch?v={video_id}")
        if "The video is no longer available" in str(e):
            return f"[video_not_available]"
        if "This video is private" in str(e):
            return f"[video_private]"
        if "This video is age-restricted" in str(e):
            return f"[video_age_restricted]"
        if "This live event will begin in a few moments." in str(e):
            return f"[live_video]"
        if "copyright grounds" in str(e):
            return f"[copyright_grounds]"
        return None

    tracks = []
    for t in transcript_list:
        tracks.append({
            "language": t.language,
            "language_code": t.language_code,
            "is_generated": t.is_generated,
            "is_translatable": t.is_translatable,
        })

    has_manual_fr = any(
        t.get("language_code") == "fr" and not t.get("is_generated", False)
        for t in tracks
    )
    has_generated_fr = any(
        t.get("language_code") == "fr" and t.get("is_generated", False)
        for t in tracks
    )

    if has_manual_fr:
        for t in transcript_list:
            if t.language_code == "fr" and t.is_generated:
                try:
                    data = t.fetch()
                    return transcript_to_text(data)
                except Exception as e:
                    print(f"  [ERROR] {video_id} — could not fetch auto transcript: {e}")
                    print(f"verify video at https://www.youtube.com/watch?v={video_id}")
                    return None
            return "[manual_only]"
    elif has_generated_fr:
        return "[generated_likely]"
    else:
        return "[no_french_transcript_now]"

def main():
    vera_filename = "news_transcripts_Vera_clean"
    json_output = "news_transcripts_2024"

    results = {}

    # load JSON
    if os.path.exists(f"data/youtube/transcripts/{json_output}.json"):
        with open(f"data/youtube/transcripts/{json_output}.json") as f:
            results = json.load(f)

    vera_transcripts = pd.read_json(f"data/youtube/transcripts/{vera_filename}.jsonl",
                                    orient='records', lines=True)

    video_ids = list(set(vera_transcripts["videoId"]) - set(results.keys()))
    for i, vid in enumerate((pbar := tqdm(video_ids, desc="Fetching transcripts"))):
        pbar.set_postfix(video=vid)
        try:
            text = fetch_auto_transcript(vid)
            if text == "[generated_likely]":
                results[vid] = vera_transcripts.loc[vera_transcripts['videoId'] == vid, 'transcript'].values[0]
                with open(f"data/youtube/transcripts/{json_output}.json", "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
            elif text is not None:
                results[vid] = text
                # Save JSON
                with open(f"data/youtube/transcripts/{json_output}.json", "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
        except KeyboardInterrupt as e:
            with open(f"data/youtube/transcripts/{json_output}.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
                time.sleep(1)
            raise e


    # Save JSON
    with open(f"data/youtube/transcripts/{json_output}.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(results)}/{len(video_ids)} transcripts saved to '{json_output}.json'")

if __name__ == "__main__":
    main()

