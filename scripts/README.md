# Data collection pipeline

Run from the repo root as modules (`python -m scripts.<name>`). Without
arguments, each script processes every year, channel type and platform set in
`scripts/project_config.py` (`YEARS`, `CHANNEL_TYPES`, `get_collect_periods`);
`--year`, `--channel_type` and `--platform` restrict it where available.

## YouTube

1. **Channels** — `python -m scripts.collect_youtube_channels`
   Refreshes stats (subscribers, video/view counts) of the channels listed in
   `data/youtube/channels/{channel_type}_channels.json` (to add a channel, add it there).

2. **Videos** — `python -m scripts.collect_youtube_videos`
   Collects the channels' videos in the collection period
   (`project_config.get_collect_periods`, end day excluded), then labels Shorts.
   Writes `data/youtube/videos/{channel_type}_videos_{year}.jsonl`.

3. **Transcripts** — `python -m scripts.run_transcripts_collection`
   Auto-generated transcripts via `youtube_transcript_api`; videos without one get
   the reason in `error_transcript` and are transcribed by faster-whisper later.

## TikTok

1. **Channels** — `python -m scripts.collect_tiktok_channels`
   Refreshes the info of the accounts listed in
   `data/tiktok/channels/{channel_type}_channels.json`.

2. **Videos** — `python -m scripts.collect_tiktok_videos`
   Writes the raw `data/tiktok/videos/{channel_type}_videos_{year}.json` (a plain
   JSON array, converted to jsonl in the shared steps below). Transcripts come
   with the videos (`voice_to_text`).

## Shared steps (both platforms)

Run after collecting videos for both platforms:

1. `python -m scripts.prepare_videos` — converts TikTok's raw JSON to jsonl,
   splits out zero-duration TikTok posts (photo carousels), and drops
   zero-duration YouTube videos.
2. `python -m scripts.prepare_channels` — standardizes channel names/orientation
   for both platforms, then propagates each channel's `name_standard` onto its
   video files. Run *after* `prepare_videos`, since it needs the video jsonl
   files already in place.
3. Transcripts still missing (both platforms):
   - `python -m scripts.collect_missing_transcripts` — downloads and transcribes them
     with faster-whisper (`--keep_videos no` to delete the downloads afterwards);
     videos that can't be downloaded are marked "[video unavailable]".
   - `python -m scripts.add_missing_transcripts` — merges the faster-whisper output
     back into the video files (`generated_by="fastwhisper"`) and sets the videos
     marked unavailable aside in `{channel_type}_videos_not_available_{year}.jsonl`.
4. `python -m scripts.check_video_availability` — asks the YouTube Data API and
   the TikTok Research API which videos still exist; the ones no longer returned
   (deleted, private, ...) are moved to `data/{platform}/videos/unavailable_videos.jsonl`
   and are not part of the shared data. Leaves a file unchanged if more than half of
   its videos come back unavailable (`--max_unavailable_share`), as that points to an
   API problem.
5. `python -m scripts.detect_politicians_and_parties_in_videos` — NER on the
   news videos' titles on YouTube, descriptions on TikTok (CamemBERT, only for videos without a `PER` value
   yet), then cleaned politician names (`PER_clean`) and the parties they belong
   to (`parties`), all written into the news video files of both platforms.
   `--platform`, `--year` and `--steps ner clean parties` restrict it.

Video ids are text everywhere (TikTok `id` included): read the video files with
`dtype={"id": str}` / `{"videoId": str}`, otherwise pandas turns them into numbers.

## Transcript-matching model

`python -m scripts.train_matching_model` — trains the logistic-regression
matching classifier (features: fuzzy partial, token sort and token set ratios
between each video's first 2000 cleaned characters and the other video's full
cleaned transcript) on all labeled pairs in the manual annotation files. Writes
`data/model.pkl`, `data/best_thr.txt` (F1-maximizing threshold) and
`data/pairs_of_transcripts/training_pairs.jsonl` (training pairs + features,
read by notebook `03_model_training_diagnosis.ipynb` for diagnostics). Run after the
shared steps above, since it needs `name_standard` and transcripts on the
video jsonl files.

`python -m scripts.evaluate_matching_methods` — compares feature sets (partial /
sort / set ratios and their combinations) over the full grid of transcript
preprocessings (every combination of accents, case, brackets and openers x every
cut length: 96 variants) by 5-fold cross-validation on the same labeled pairs. Writes `data/pairs_of_transcripts/evaluation/matching_evaluation.csv`
(shown in notebook `02_matching_preprocessing_evaluation.ipynb`) and the ratios per variant (`features_{variant}.csv`, reused
on later runs: the variants without a cut take long; `--recompute` to redo them).

## Pair distances

`scripts/compute_distances_w_preprocessing.py` computes the fuzzy-ratio features
for candidate pairs (`data/pairs_of_transcripts/<pairs>_<year>.csv` ->
`<pairs>_<year>_w_d.csv`, appended and resumable). Run from the repo root:
- `bash scripts/run_compute_polit_transcripts_matching.sh [year]` — politicians'/parties'
  own reposts; `..._news_...` — news channels' own reposts; `..._both_...` —
  politicians/parties x news. Year defaults to 2024.
- `python -m scripts.compute_distances_w_preprocessing` with no arguments runs the
  whole 2024 batch.

## Pair classification and similarity graphs

`python -m scripts.classify_and_build_graphs` — classifies the 2024 candidate
pairs in `data/pairs_of_transcripts/*_2024_w_d.csv` with `data/model.pkl` /
`data/best_thr.txt` (writes `data/pairs_of_transcripts/classified/*_classified.csv`),
then builds one similarity graph per channel/party (videos as nodes, matches as
edges) in `data/networks/{pp_only,news_only,diff,parties}_2024/`. Run after
`train_matching_model`; re-run whenever the model changes. The graphs are read
by notebooks 05 (upload patterns), 06, 07 and 08.

## Whisper validation

`python -m scripts.validate_whisper_transcripts` — downloads and transcribes
(faster-whisper) the test samples in
`data/test_transcript_collection_accuracy/{tiktok,youtube}_test.jsonl`, videos
that already have a platform transcript, writing to
`data/test_transcript_collection_accuracy/transcripts/`. Skips videos already
transcribed. Notebook `04_API_vs_whisper_transcripts.ipynb` then
compares the whisper and platform transcripts with the matching model.
