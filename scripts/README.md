# Data collection pipeline

Run from the repo root (all scripts `os.chdir` there automatically if launched
from `notebooks/`). Most scripts hardcode `channel_type`/`year`/`platform` as
plain variables at the top of `main()` rather than CLI args — edit those
before each run unless noted otherwise.

## YouTube

1. **Channels** — `python -m scripts.collect_youtube_channels`
   Refreshes stats (subscribers, video/view counts) for the channel IDs
   already in `data/youtube/channels/{channel_type}_channels.json`. Edit
   `channel_type` in `main()` ("news" or "pp") and run once per type.

2. **Videos** — `python -m scripts.collect_youtube_videos`
   Collects videos for one `channel_type`/`year` (edit both in `main()`)
   within that year's election window (`scripts/project_config.get_collect_periods`),
   then labels Shorts. Writes `data/youtube/videos/{channel_type}_videos_{year}.jsonl`.
   Run once per `channel_type` x `year` combination (4 runs total: news/pp x 2022/2024).

3. **Transcripts**
   - `python -m scripts.run_transcripts_collection` — auto-generated transcripts via
     `youtube_transcript_api`. Edit `video_filename`/`json_output` in `main()`.
   - `python -m scripts.collect_missing_transcripts --platform youtube --year <year>
     --channel_type <type> --video_filepath data/youtube/videos/<type>_videos_<year>.jsonl
     --transcripts_dir data/youtube/videos/transcripts --downloaded_videos_dir data/youtube/videos/downloaded`
     — faster-whisper fallback for videos still missing a transcript.
   - `python -m scripts.add_missing_transcripts` — merges the faster-whisper output
     back into the video jsonl files (tags `generated_by="fastwhisper"`).

## TikTok

1. **Channels** — `python -m scripts.collect_tiktok_channels`
   Edit `channel_type` in `main()` ("news" or "pp") and run once per type.

2. **Videos** — `python -m scripts.collect_tiktok_videos`
   Edit `year`/`channel_type` in `main()`. Writes the raw
   `data/tiktok/videos/{channel_type}_videos_{year}.json` (a plain JSON array,
   converted to jsonl in the shared step below).

3. **Transcripts** — same `collect_missing_transcripts`/`add_missing_transcripts`
   steps as YouTube, with `--platform tiktok`.

## Shared steps (both platforms)

Run after collecting videos for both platforms:

1. `python -m scripts.prepare_videos` — converts TikTok's raw JSON to jsonl,
   splits out zero-duration TikTok posts (photo carousels), and drops
   zero-duration YouTube videos. Covers all 4 `channel_type` x `year`
   combinations for both platforms in one run.
2. `python -m scripts.prepare_channels` — standardizes channel names/orientation
   for both platforms, then propagates each channel's `name_standard` onto its
   video files. Run *after* `prepare_videos`, since it needs the video jsonl
   files already in place.
3. `python -m scripts.check_video_availability` — asks the YouTube Data API and
   the TikTok Research API which videos still exist; the ones no longer returned
   (deleted, private, ...) are moved to `data/{platform}/videos/unavailable_videos.jsonl`
   and are not part of the shared data. Leaves a file unchanged if more than half of
   its videos come back unavailable (`--max_unavailable_share`), as that points to an
   API problem.
4. `python -m scripts.detect_politicians_and_parties_in_videos` — NER on the
   news videos' titles on YouTube, descriptions on TikTok (CamemBERT, only for videos without a `PER` value
   yet), then cleaned politician names (`PER_clean`) and the parties they belong
   to (`parties`), all written into the news video files of both platforms.
   `--platform`, `--year` and `--steps ner clean parties` restrict it.

Video ids are text everywhere (TikTok `id` included): read the video files with
`dtype={"id": str}` / `{"videoId": str}`, otherwise pandas turns them into numbers.

## Transcript-matching model

`python -m scripts.train_matching_model` — trains the logistic-regression
matching classifier (features: fuzzy partial ratio + token sort ratio between
each video's first 2000 cleaned characters and the other video's full cleaned
transcript) on all labeled pairs in the manual annotation files. Writes
`data/model.pkl`, `data/best_thr.txt` (F1-maximizing threshold) and
`data/pairs_of_transcripts/training_pairs.jsonl` (training pairs + features,
read by notebook `05_model_training.ipynb` for diagnostics). Run after the
shared steps above, since it needs `name_standard` and transcripts on the
video jsonl files.

## Pair distances

`scripts/compute_distances_w_preprocessing.py` computes the fuzzy-ratio features
for candidate pairs (`data/pairs_of_transcripts/<pairs>_<year>.csv` ->
`<pairs>_<year>_w_d.csv`, appended and resumable). Run from the repo root:
- `bash scripts/run_compute_polit_transcripts_matching.sh [year]` — politicians'/parties'
  own reposts; `..._news_...` — news channels' own reposts; `..._both_...` —
  politicians/parties x news. Year defaults to 2024.
- `python -m scripts.compute_distances_w_preprocessing` with no arguments runs the
  whole 2024 batch.
- `bash scripts/run_evaluate_transcripts_matching.sh` — `--test 1` mode on the
  labeled pairs, one output per preprocessing/cut variant in
  `data/youtube/transcripts/evaluate/`, compared in notebook 03.

## Pair classification and similarity graphs

`python -m scripts.classify_and_build_graphs` — classifies the 2024 candidate
pairs in `data/pairs_of_transcripts/*_2024_w_d.csv` with `data/model.pkl` /
`data/best_thr.txt` (writes `data/pairs_of_transcripts/classified/*_classified.csv`),
then builds one similarity graph per channel/party (videos as nodes, matches as
edges) in `data/networks/{pp_only,news_only,diff,parties}_2024/`. Run after
`train_matching_model`; re-run whenever the model changes. The graphs are read
by notebooks 07 (upload patterns), 08, 09 and 10.

## Whisper validation

`python -m scripts.validate_whisper_transcripts` — downloads and transcribes
(faster-whisper) the test samples in
`data/test_transcript_collection_accuracy/{tiktok,youtube}_test.jsonl`, videos
that already have a platform transcript, writing to
`data/test_transcript_collection_accuracy/transcripts/`. Skips videos already
transcribed. Notebook `06_compare that whisper results are ok.ipynb` then
compares the whisper and platform transcripts with the matching model.
