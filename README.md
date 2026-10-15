# VideosRepurposing

Code for studying how French political actors and news media reuse video content
across YouTube (regular videos and Shorts) and TikTok, around the 2022 and 2024
French elections.

The pipeline collects the videos of politicians, parties and news channels,
transcribes them, finds pairs of videos that share the same content (fuzzy
matching of transcripts + a logistic-regression classifier), and builds, for each
channel, a graph of matched videos used in the analyses.

The collected data is not included in this repository.

## Structure

```
src/        reusable code, no project-specific values: API collection (YouTube, TikTok),
            video downloaders, faster-whisper transcription, transcript matching
scripts/    the pipeline of this study, one script per step (see scripts/README.md);
            years, channel types and collection periods are set in scripts/project_config.py
notebooks/  analyses and figures, reading the pipeline's outputs
tests/      tests/pipeline/: the whole pipeline on a small subset (one politician,
            one news channel, three days), compared with the full run
```

## Setup

```
pip install -r requirements.txt
```

`ffmpeg` must be installed. API keys go in a `.env` file at the repository root:

```
YOUTUBE_API_KEY=...
TIKTOK_CLIENT_KEY=...         # TikTok Research API
TIKTOK_CLIENT_SECRET=...
PROXY_HTTP_URL=...            # proxy used by youtube_transcript_api
PROXY_HTTPS_URL=...
```

## Running

Scripts are run from the repository root as modules, e.g.
`python -m scripts.collect_youtube_videos`. The order of the steps is described
in `scripts/README.md`.

To check the whole pipeline on a small subset without touching `data/`:

```
bash tests/pipeline/run_pipeline.sh
```

## License

MIT, see `LICENSE`.