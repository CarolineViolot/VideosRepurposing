from src.file_io import load_channels_files, create_transcripts_and_videos_by_year

def prepare_pairs_df(pairs_df):
    pairs_df = pairs_df[pairs_df.transcript1_length > 50]
    pairs_df = pairs_df[pairs_df.transcript2_length > 50]
    all_probas = model.predict_proba(pairs_df[model.feature_names_in_]
                                    )[:,1]

    pairs_df['predicted_proba'] = all_probas
    pairs_df['predicted_label'] = pairs_df['predicted_proba'].apply(
        lambda x: 1 if x > best_thr else 0)
    pairs_df = pairs_df.merge(
        all_videos[['videoId', 'name_abbr']], left_on = 'videoId1', right_on='videoId')
    return pairs_df[['name_abbr', 'videoId1', 'videoId2', 'predicted_proba', 'predicted_label', 'videoId'] +
    list(model.feature_names_in_)]

def main():
    channels = load_channels_files()
    nm_yt_channels = channels['news_youtube_channels']
    pp_yt_channels = channels['pp_youtube_channels']
    nm_tt_channels = channels['news_tiktok_channels']
    pp_tt_channels = channels['pp_tiktok_channels']

    transcripts_yt, videos_yt = create_transcripts_and_videos_by_year()
    transcripts_tt, videos_tt = create_transcripts_and_videos_by_year(platform='tiktok')

if __name__ == "__main__":
    main()