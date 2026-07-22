import json
import warnings
from pathlib import Path

import pandas as pd
from src.utils import get_channel_names_dict, get_politician2party, get_party_orientation, get_tt_username2display_name, get_news_channel_orientation

def read_json_or_jsonl(base_path: str) -> list[dict]:
    """Load records from <base_path>.jsonl (one object per line) or <base_path>.json (a list)."""
    jsonl = Path(f"{base_path}.jsonl")
    if jsonl.exists():
        with open(jsonl) as f:
            return [json.loads(line) for line in f if line.strip()]
    with open(f"{base_path}_w_transcript.json") as f:
        return json.load(f)


def load_channels_files():
    nm_yt_channels = pd.read_json("data/youtube/channels/news_channels.json")
    pp_yt_channels = pd.read_json("data/youtube/channels/pp_channels.json")

    with open("data/tiktok/channels/news_channels.json") as f:
        nm_tt_channels = json.load(f)
    nm_tt_channels = pd.DataFrame.from_dict(nm_tt_channels['channels'], orient="index").reset_index().rename(columns={
        'index':'username'
    })

    nm_tt_channels['channelTitle'] = nm_tt_channels['username'].map(get_channel_names_dict())
    nm_tt_channels['orientation'] = nm_tt_channels['channelTitle'].map(get_news_channel_orientation())

    with open("data/tiktok/channels/pp_channels.json") as f:
        pp_tt_channels = json.load(f)
    pp_tt_channels = pd.DataFrame.from_dict(pp_tt_channels['channels'], orient="index").reset_index().rename(columns={
        'index': 'username'
    })
    pp_tt_channels.rename(columns={'display_name': 'channelTitle'}, inplace=True)
    pp_tt_channels['orientation'] = pp_tt_channels['party'].apply(lambda x: get_party_orientation()[x])

    return {"news_youtube_channels" : nm_yt_channels,
            "pp_youtube_channels" : pp_yt_channels,
            "news_tiktok_channels" : nm_tt_channels,
            "pp_tiktok_channels" : pp_tt_channels}


def read_video_file(filename):
    if "youtube" in filename:
        videos_df = pd.read_json(filename, lines=True)
        videos_df.columns = videos_df.columns.str.replace(r'_\d{4}-\d{2}$', '', regex=True)
    elif "tiktok" in filename:
        videos_df = pd.read_json(filename, lines=True)
        videos_df.rename(columns = {'id':'videoId', 'video_description':'description',
                              'video_duration':'duration', 'create_time': 'publishedAt',
                              'view_count':'views', 'comment_count':'comments', 'like_count':'likes',
                               'share_count':'shares'}, inplace=True)
        #print("in file_io.read_video_file videos_df.username.unique() : ", videos_df.username.unique() )
        videos_df['channelTitle'] = videos_df['username'].apply(lambda x: get_channel_names_dict().get(x, x))
        #print(get_channel_names_dict())
        #print("in file_io.read_video_file videos_df.channelTitle.unique() : ", videos_df.channelTitle.unique())
        ordered_columns_list = ['videoId', 'channelTitle', 'username', 'description', 'duration', 'publishedAt',
                                'views', 'likes','comments','shares', 'favorites_count',
                                'region_code', 'hashtag_names','music_id', 'effect_info_list']
        videos_df = videos_df[ordered_columns_list + list(set(videos_df.columns) - set(ordered_columns_list))]
    else :
        raise ValueError(f'filepath does not contain "youtube" or "tiktok"')
    return videos_df

def create_all_channel_df(news_channel_df, pp_channel_df):
    channel_title_dict = get_channel_names_dict()
    assert set(news_channel_df.orientation.unique()) == {'Center (news)', 'Right (news)', 'Left (news)'}
    news_channel_df["broad_orientation"] = news_channel_df.orientation
    pp_channel_df["broad_orientation"] = pp_channel_df.orientation.apply(lambda x: {'Far Left': "Left",
                                                                                    'Far Right': 'Right'}.get(x, x))

    news_channel_df.channelTitle = news_channel_df.channelTitle.apply(lambda x: channel_title_dict.get(x, x))
    pp_channel_df.channelTitle = pp_channel_df.channelTitle.apply(lambda x: channel_title_dict.get(x, x))
    channel_df = pd.concat([news_channel_df, pp_channel_df])
    return channel_df

def load_videos_only_df(year, type, platform):
    raise NotImplementedError()

def load_transcripts_only_df(year, channel_type, platform):
    data = read_json_or_jsonl(f"data/{platform}/videos/{channel_type}_videos_{year}")

    if platform == "tiktok":
        return [
            {"video_id": row["id"], "channel": row["username"], "transcript": row["voice_to_text"]}
            for row in data
            if row["video_duration"] > 0
        ]
    if platform == "youtube":
        return [
            {"video_id": row["videoId"], "channel":row["channelId"], "transcript": row["transcript"]}
            for row in data
            if row["duration"] > 0
        ]


def create_transcripts_and_videos_by_year(platform='youtube'):
    if platform not in ['youtube', 'tiktok']:
        raise ValueError(f"invalid platform {platform}. Must be 'tiktok' or 'youtube'")

    channel_title_dict = get_channel_names_dict()
    politician2party = get_politician2party()

    def process_video_df(videos_df, channel_df, get_party=False, merge_on = 'channelTitle'):
        videos_df["day"] = videos_df.publishedAt.astype(str).apply(lambda x: x[0:10])
        videos_df["comments_by_views"] = videos_df.comments / videos_df.views
        videos_df['publishedAt'] = pd.to_datetime(videos_df['publishedAt'])
        videos_df["week"] = videos_df['publishedAt'].dt.strftime('%Y-W%U')
        videos_df["channelTitle"] = videos_df["channelTitle"].apply(lambda x: channel_title_dict.get(x, x))

        if get_party:
            videos_df['party'] = videos_df['channelTitle'].apply(lambda x: politician2party.get(x))
        channel_df["channelTitle"] = channel_df["channelTitle"].apply(lambda x: channel_title_dict.get(x, x))
        if len(set(videos_df[merge_on]).symmetric_difference(set(channel_df[merge_on]))) > 0:
            if len(set(videos_df[merge_on]) - set(channel_df[merge_on])) > 0:
                warnings.warn(message=
                    f"Differences in {merge_on} !\n {merge_on} in videos_df not in channel_df : {
                    set(videos_df[merge_on]) - set(channel_df[merge_on])}")
            if len(set(channel_df[merge_on]) - set(videos_df[merge_on])) > 0:
                warnings.warn(message=
                    f"Differences in {merge_on} !\n {merge_on} in channel_df not in video_df : {
                    set(channel_df[merge_on]) - set(videos_df[merge_on])}")
        print("in file_io.create_transcripts_and_videos_by_year.process_video_df, channel_df")
        videos_df = videos_df.merge(channel_df[[merge_on, "orientation"]], on=merge_on)
        return videos_df

    print("Creating all channel df")
    channels = load_channels_files()
    transcripts_by_year = {}
    videos_by_year = {}

    merge_on = 'channelTitle'

    print("Creating all video dfs")
    for year in ["2022", "2024"]:
        videos_by_year[year] = {}
        transcripts_by_year[year] = {}
        for channel_type in ['news', 'pp']:
            if platform == 'youtube':
                video_filename = f"data/{platform}/videos/{channel_type}_videos_{year}.csv"
                transcript_filename = f"data/{platform}/transcripts/{channel_type}_transcripts_{year}.json"
            else:
                video_filename = f"data/{platform}/videos/{channel_type}_videos_{year}_w_transcript.json"
                transcript_filename = video_filename
                if channel_type == 'pp': merge_on = 'username'
            try:
                videos_df = read_video_file(video_filename)
                videos_df = videos_df[videos_df["duration"] != "P0D"].astype({"duration": "float"}).astype(
                    {"duration": "int"})
                processed_videos_df = process_video_df(videos_df, channels[f'{channel_type}_{platform}_channels'],
                                                       get_party=(channel_type == "pp"), merge_on=merge_on)
                assert len(processed_videos_df)  == len(videos_df), f"length processed_videos_df is {len(processed_videos_df)}, length videos_df is {len(videos_df)}"
                videos_df = processed_videos_df.copy()
                videos_df['videoId'] = videos_df['videoId'].apply(str)
                videos_by_year[year][channel_type] = videos_df
            except Exception as e:
                print(f"Failed to process video {video_filename}")
                raise e

            try:
                transcripts = read_transcript_file(transcript_filename)
                transcripts['videoId'] = transcripts['videoId'].apply(str)
                if platform == "youtube":
                    transcripts = transcripts.merge(
                        videos_df[["videoId", "channelTitle", "isShort"]])
                else:
                    transcripts = transcripts.merge(
                        videos_df[["videoId", "channelTitle"]])
            except Exception as e:
                print(f"Failed to process transcript {transcript_filename}")
                raise e
            transcripts_by_year[year][channel_type] = transcripts
    return transcripts_by_year, videos_by_year