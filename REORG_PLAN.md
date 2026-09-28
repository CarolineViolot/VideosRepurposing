# Reorganize VideosRepurposing into src / scripts / notebooks

## Context

The repo currently mixes three kinds of code together without a clear boundary: `src/` contains some genuinely reusable YouTube/TikTok helpers but also project-specific logic (hardcoded channel names, "news"/"pp" categories, years, paths); `scripts/` is mostly correct but a couple of files bury generic, reusable logic inside project-specific orchestration; and `notebooks/` mixes real data-visualization/exploration with data-cleaning/collection/merging pipelines that write to disk.

The target principle, confirmed in conversation:
- **`src/`** — reusable library code with zero project-specific values (no hardcoded channel names, no "news"/"pp" category strings, no hardcoded years, no paths tied to this study's data layout). Eventually could become a personal cross-project library.
- **`scripts/`** — this-project-specific CLI entry points/pipelines, allowed to hardcode this study's variables and paths.
- **`notebooks/`** — visualization and exploration only. Any notebook section that persists processed data to disk (`to_json`/`to_csv`/pickle/model artifacts) belongs in a script instead.

Three read-only audit agents inventoried every file in `src/`, `scripts/`, and `notebooks/` against this principle. This document synthesizes their findings into a phased, actionable list. **This is a planning/documentation deliverable** — nothing has been moved or changed yet. Two issues surfaced during the audit are flagged here but deliberately not fixed yet, per your choice: hardcoded proxy credentials in a `scripts/` file, and a project-specific import bug in `src/`.

## Target directory structure

```
src/                                    # generic, reusable, zero project-specific values
  downloader_utils.py                   # unchanged — ffmpeg checks, audio validation, cookie opts
  tiktok_downloader.py                  # unchanged — TikTokDownloader class, CLI
  youtube_downloader.py                 # unchanged
  transcript_matching.py                # unchanged; becomes canonical home for cleaning logic (Phase D)
  transcripts_collection.py             # trimmed to transcript_to_text, fetch_auto_transcript
  transcripts_read_and_clean.py         # kept short-term, flagged for consolidation (Phase D)
  tiktok_api_collection.py   [NEW]      # generic TikTok API helpers consolidated from
                                         # collect_tiktok_channels.py + collect_tiktok_videos.py:
                                         # get_access_token (deduped), fetch_user_info, fetch_oldest_video,
                                         # load_existing_channels, date_windows, fetch_window, fetch_user,
                                         # load_existing_videos, get_existing_channels, save
  whisper_transcription.py   [NEW]      # download_video, transcribe_video, video_url pulled from
                                         # scripts/collect_missing_transcripts.py (already generic, params-driven)
  utils.py                              # trimmed to purely generic helpers (list below)

scripts/                                # this-study-specific CLI/orchestration
  project_config.py          [NEW]      # project dicts/loaders moved out of src/utils.py. OK 
  collect_tiktok_channels.py            # main() + channel-name lists + paths; imports generic helpers from src. OK 
  collect_tiktok_videos.py              # main() + year/channel_type hardcoding + paths; imports generic
                                         # helpers from src; election-period import now lives here, not in src
  run_transcripts_collection.py         # renamed from the project-specific half of transcripts_collection.py
                                         # (avoids name clash with the src module of the same name)
  collect_missing_transcripts.py        # unchanged CLI/orchestration + load_pending_videos; now imports
                                         # download_video/transcribe_video/video_url from src
  add_missing_transcripts.py            # unchanged (already correct, done earlier this session)
  compute_distances_w_preprocessing.py  # unchanged
  create_all_vid_pairs.py               # unchanged (minus dead _DELETE functions, Phase A optional)
  create_tiktok_helper_dict.py          # unchanged
  create_vid_pairs_to_be_annotated.py   # unchanged (arg-count bug flagged, Phase D optional)
  detect_politicians_and_parties_in_videos.py  # unchanged
  recollect_missing_wrong_transcripts_f_Vera.py # unchanged except credentials removed (Phase A item, deferred)
  prepare_channels.py         [NEW]     # from notebook 01: channel verification/standardization writes
  prepare_videos.py           [NEW]     # from notebook 01: csv->jsonl, P0D fix, transcript merge,
                                         # TikTok->jsonl, remove photos from tiktok files
  merge_ner_results.py        [NEW]     # from notebook 01: merge cleaned NER results into main jsonl
  standardize_channel_names.py [NEW]    # from notebook 01: standard-name merge, remove arte everywhere
  train_matching_model.py     [NEW]     # from notebook 05: build training set -> threshold selection ->
                                         # save data/model.pkl, data/best_thr.txt
  validate_whisper_transcripts.py [NEW] # from notebook 06: download+whisper collection writing to
                                         # data/test_transcript_collection_accuracy/
  classify_and_build_graphs.py [NEW]    # from notebook 07 sections 1-4.5: run classifier, write .gv graphs
  run_collect_missing_transcripts.sh    # unchanged
  run_compute_*_transcripts_matching.sh # kept, fixed (Phase D7)
  run_evaluate_transcripts_matching.sh  # kept, fixed (Phase D7)
  # add_labels.py, compare_tiktok_transcripts_methods.py -> deleted (Phase D5)

notebooks/
  plotting_helpers.py         [NEW]     # project-local (not src) home for src/plots_utils.py's content
                                         # + the plotting helpers pulled from src/utils.py
  01_cleaning...ipynb                   # reduced to true exploration/QA once write-sections are extracted
  02_dataset description...ipynb        # unchanged
  03_matching_preprocessing_evaluation.ipynb  # unchanged
  04_thefuzz vs fuzzywuzzy...ipynb      # unchanged (or archived, optional)
  05_model_training.ipynb               # reduced to loading model.pkl/best_thr.txt + diagnostics plots
  06_compare that whisper results are ok.ipynb  # reduced to analysis of already-collected test transcripts
  07_video pairs classification...ipynb # reduced to section 5+ (visualization reading pre-built graphs)
  08_channels_own_reposts.ipynb         # unchanged
  09_reuse_and_sourcing.ipynb           # unchanged
  10_engagement_gains.ipynb             # unchanged
  PoliticalAgendaSetting/01 - ...ipynb  # unchanged
  # .ipynb_checkpoints/ -> gitignored (Phase A)
```

**Import mechanics note:** there's no `__init__.py` anywhere; `from src.X import Y` works today via implicit namespace packages, run from repo root. The same pattern extends to `from scripts.project_config import ...`. No packaging changes needed, but every `from src.X import ...` reference that moves must be updated across `scripts/*.py`, `tests/*.py`, and the affected notebooks — budget this mechanical cost into Phases B and C.

## Phased list of changes

### Phase A — quick wins, low risk
4. `scripts/recollect_missing_wrong_transcripts_f_Vera.py`'s `fetch_auto_transcript`, load from an env var instead. Check `git log -p` on that file/its prior name for whether the credentials were ever committed — if so, they should be treated as compromised and rotated, since removing them from the working tree doesn't remove them from history. Removed. Git history cleaned on 2026-09-28: git-filter-repo replaced every `user:pass@` URL (smartproxy, evomi, oxylabs, dataimpulse) and every TikTok `CLIENT_KEY`/`CLIENT_SECRET` literal with `***REMOVED***` in the 2 affected commits (dbe294b -> 6526eb0, e0d0c9d -> 2db4317), tags moved, main force-pushed, local reflog/objects purged. Credentials still to rotate (they were on GitHub from 2026-09-17 and appeared in a Claude session transcript).

### Phase B — src/scripts splits for mixed files (core of the principle)
1. **`src/utils.py` three-way split:**
   - Stays generic in `src/utils.py`: `create_youtube_client`, `compact_sci`, `eng_format*`, `ISO8601_duration_to_sec`, `is_short`, `contains_link`/`get_links`, `remove_breaklines`, `get_YT_category_guide`, `time_usage`, `merge_and_save`, `append_if_exists_save_otherwise`. done manually
   - Moves to `scripts/project_config.py`: `get_election_periods`, `get_news_channel_type`, `get_channel_names_dict`, `get_politician2party`, `get_tt_username2display_name`, `get_youtube2tiktok_channels`, `get_party_orientation`, `get_politician_abbr_name`, `get_news_channel_orientation`, `readAPIkey`, `read_db_pass`. done manually
   - Moves to `notebooks/plotting_helpers.py`: `plot_election_days`, `add_election_days`, `custom_ticks`, `short_intro_box` (these also reference an undefined `week_to_month_dict` global — optionally fix while moving, since the function is already broken). dead code, deleted
2. **`src/file_io.py` → `scripts/file_io.py`**, wholesale move. Update every importer: `scripts/add_labels.py`, `scripts/create_tiktok_helper_dict.py`, `scripts/create_vid_pairs_to_be_annotated.py`, `scripts/create_all_vid_pairs.py`, `scripts/detect_politicians_and_parties_in_videos.py`, notebooks 01, 02, 05, 09, and `tests/test_file_io.py`. deleted, dead code
3. **`src/collect_tiktok_channels.py` split:** generic helpers (`get_access_token`, `fetch_user_info`, `fetch_oldest_video`, `load_existing_channels`) → new `src/tiktok_api_collection.py`; `main()` + hardcoded `channel_type="pp"` + channel-name lists + paths → `scripts/collect_tiktok_channels.py`.
4. **`src/collect_tiktok_videos.py` split:** generic helpers (`date_windows`, `fetch_window`, `fetch_user`, `load_existing_videos`, `get_existing_channels`, `save`) → same new `src/tiktok_api_collection.py`; `main()` + hardcoded `year="2022"`/`channel_type="news"`/paths → `scripts/collect_tiktok_videos.py`. **Fix the module-level import bug here:** move `from src.utils import get_election_periods` out of src entirely — once `get_election_periods` relocates to `scripts/project_config.py` (step B1), the import belongs in `scripts/collect_tiktok_videos.py` at point of use, never at module level inside anything under `src/`.
5. **`src/transcripts_collection.py` split:** `transcript_to_text`, `fetch_auto_transcript` stay; `main()` + hardcoded `video_filename`/`json_output`/paths → `scripts/run_transcripts_collection.py`.
6. **`src/plots_utils.py` → `notebooks/plotting_helpers.py`** (merge with the utils.py plotting helpers from B1). Update importers: notebooks 03, 05, 08, 09, 10.
7. **`scripts/collect_missing_transcripts.py` split:** extract `download_video`, `transcribe_video`, `video_url` into new `src/whisper_transcription.py`; keep CLI/orchestration + `load_pending_videos` (project-specific jsonl schema assumptions) in `scripts/`. Bundle in the dead-code cleanup for this file since it's touched anyway (commented-out `__main__` debug block, unused `SKIP_IDS` reference, unused `sys` import).

### Phase C — notebook extraction into scripts (highest effort/risk — touches data-writing logic, needs re-validation against real data)
1. **Notebook 01:** "add missing transcripts" already extracted this session. Extract remaining write-to-disk sections:
   - `scripts/prepare_channels.py` ← "Channels verification and standardization"
   - `scripts/prepare_videos.py` ← "Change youtube video csv in jsonl", "remove 'P0D' from youtube videos", "Add transcripts to youtube video jsonl", "Put TikTok in jsonl as well", "remove photos from tiktok files"
   - `scripts/merge_ner_results.py` ← "after collecting NER, add just the clean NER results..."
   - `scripts/standardize_channel_names.py` ← "Standard names in video files", "Remove arte from everywhere"
   - Document run order (these appear to be a sequential pipeline) via a short README or driver script. Notebook 01 keeps only true exploratory/inspection cells, or gets retired if nothing remains.
2. **Notebook 05:** extract "3. Build Training Set" through "6. Threshold Selection" and "8. Save Model Artefacts" (writes `data/model.pkl`, `data/best_thr.txt`) into `scripts/train_matching_model.py`. "7. Diagnostics" plots can stay notebook-side, reading the persisted artifacts. done — chunk-match features dropped (final model = partial ratio + sort ratio); script also writes `data/pairs_of_transcripts/training_pairs.jsonl` for the notebook's diagnostics
3. **Notebook 06:** extract "1.1.2 collect transcripts using whisper" and "1.2.2 collect youtube transcripts using whisper" (download + Whisper, writes to `data/test_transcript_collection_accuracy/`) into `scripts/validate_whisper_transcripts.py`. Keep the later comparison analysis as notebook exploration. done
4. **Notebook 07:** extract sections 1–4.5 (run classifier, write `.gv` graphs to `data/networks/{pp_only,news_only,diff,parties}_2024/`) into `scripts/classify_and_build_graphs.py`. Keep section 5+ ("Upload Pattern Visualisations") and section 8 ("Negative-Delay Sanity Check") as notebook visualization. done — verified with the previous model: all 107 graphs identical to the existing ones. Section 8 was already broken (undefined `videos_yt_df`/`all_videos`, `get_source(name_abbr=...)`), left as is

Notebooks 02, 03, 04, 08, 09, 10, and `PoliticalAgendaSetting/01` need **no changes** — pure exploration/description/visualization, no data writes (09/10's `savefig` calls only write figures, which is fine).

### Phase D — consolidation / dead-code cleanup (optional, nice-to-have — not required by the principle)
1. Consolidate `src/transcripts_read_and_clean.py`'s cleaning logic with `transcript_matching.py`'s `clean_transcripts`/`strip_accents_f` (duplicate French-cleaning regex) into one canonical implementation. done — file deleted, `clean_transcripts` in `src/transcript_matching.py` is the only implementation
2. Deduplicate `get_access_token` once both copies land in `src/tiktok_api_collection.py` (Phase B3/B4). done — single copy
3. Consider generalizing `recollect_missing_wrong_transcripts_f_Vera.py`'s `fetch_auto_transcript` into the shared src transcript-collection module, once credentials are externalized. moot — file deleted
4. Fix the arg-count bug in `scripts/create_vid_pairs_to_be_annotated.py` (`__main__` calls `create_pairs_to_label_diff_platform(year, yt_transcripts, all_videos_df)` but the function only accepts `year`). done — function now takes `(year, all_tt_videos_df, all_yt_videos_dfs)`
5. Delete or finish `scripts/add_labels.py` (references undefined `model`/`best_thr`/`all_videos`, `main()` never calls `prepare_pairs_df`) and `scripts/compare_tiktok_transcripts_methods.py` (references undefined `read_transcript_file`). done — both deleted (`compare_tiktok_transcripts_methods.py` superseded by `validate_whisper_transcripts.py`)
6. Delete the two `_DELETE`-suffixed dead functions in `scripts/create_all_vid_pairs.py`. done — also removed the now-unused `extract_short_transcript` import and fixed the broken `from transcript_matching import` (missing `src.`)
7. Decide whether `run_compute_both/news/polit_transcripts_matching.sh` and `run_evaluate_transcripts_matching.sh` are still used (they point at a stale `data/transcripts/pairs_*.csv` layout, not the current `data/pairs_of_transcripts/...`) — delete if superseded, keep if still used on the SLURM cluster. done — kept and fixed: run from repo root via `python -m`, current paths and preprocessing, `[year]` arg; `compute_distances_w_preprocessing.py` now honours CLI args (no args = 2024 batch), `--test 1` reproduces notebook 03's evaluate files, fixed `if pairs_df:` / `raise (ValueError, ...)` / `--test` bool parsing. Verified: evaluate variants `_`, `_strip_accents`, `_cut_2000` identical to the existing files in `data/youtube/transcripts/evaluate/`; normal mode on the first 2000 pairs of `pairs_yt_same_channel_pp_2024` identical to the existing `_w_d.csv` rows
8. Homogeneize the comment for structure, sometimes it's # ====SAVE==== sometimes # ─────────────────────────────────────────────
#  USER / CHANNEL INFO
# ───────────────────────────────────────────── sometimes # ─── FETCH ───────────────────────────────────────────────────── done — all section headers are now `# ── Title ───…` padded to 80 cols, sentence case

## Flagged issues (tracked as line items, not fixed yet)
- **Security:** hardcoded proxy credentials in `scripts/recollect_missing_wrong_transcripts_f_Vera.py` — Phase A item 4. History cleaned (see A4); rotation of the proxy and TikTok credentials pending.
- **Bug:** project-specific module-level import (`get_election_periods`) inside `src/collect_tiktok_videos.py` — fixed as part of Phase B4/B1.

## Suggested execution order
Given the scope, recommend executing this across multiple future sessions rather than one pass: Phase A (fast, low-risk) → Phase B (mechanical but touches many import sites, should be done file-by-file with `python -m py_compile` / import smoke tests after each) → Phase C (needs the most care, one notebook at a time, re-running against real data to confirm output files are byte-identical or intentionally changed) → Phase D (whenever convenient).

## Verification
- After each Phase B split: `python -m py_compile` on every touched file, then `grep -rn "from src\." scripts/ notebooks/ tests/` to confirm no stale imports remain pointing at moved symbols.
- After each Phase C notebook extraction: run the new script against the real `data/` directory and diff its output files against what the original notebook cells produced (on a backup/copy) to confirm no behavior change, then re-run the trimmed notebook end-to-end to confirm it still executes cleanly reading the script's output.
- Run existing tests (`tests/test_file_io.py` and any others) after Phase B2's `file_io.py` move.
