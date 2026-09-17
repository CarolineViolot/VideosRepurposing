from scripts.collect_missing_transcripts import *

if __name__ == '__main__':
    # 1. Create a DF which contains 25 samples of tiktok w transcripts from each file to have a total of 100 records
    tiktok_w_transcipts = []
    for filename in ["data/tiktok/videos/news_videos_2022.json", "data/tiktok/videos/news_videos_2024.json",
                     "data/tiktok/videos/pp_videos_2022.json", "data/tiktok/videos/pp_videos_2024.json"]:
        df = read_transcript_file(filename)
        tiktok_w_transcipts.append(df[~df['transcript'].isna()].sample(25, random_state=0))
    tiktok_w_transcipts = pd.concat(tiktok_w_transcipts)

    # download videos from step 1. and transcribe then using whisper
    model = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=8)
    tiktok_w_transcipts = []
    for filename in ["data/tiktok/videos/news_videos_2022.json", "data/tiktok/videos/news_videos_2024.json",
                     "data/tiktok/videos/pp_videos_2022.json", "data/tiktok/videos/pp_videos_2024.json"]:
        df = read_transcript_file(filename)
        df = df[~df['transcript'].isna()]
        tiktok_w_transcipts.append(df.sample(25, random_state=0))
    tiktok_w_transcipts = pd.concat(tiktok_w_transcipts)
    videos_dir = "data/tiktok/videos/downloaded_test/"
    transcripts_dir = "data/tiktok/videos/transcripts_test/"
    for video_id in tqdm(tiktok_w_transcipts.videoId.values):
        matches = list(Path(videos_dir).glob(f"{video_id}.*"))
        video_path = matches[0] if matches else None
        if video_path is None:
            video_path = download_video(video_id, 'user', videos_dir, platform='youtube')
        result = transcribe_video(video_path, model, language='fr')
        save_transcript(video_id, result, transcripts_dir)
