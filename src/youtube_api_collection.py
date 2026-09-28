"""
src/youtube_api_collection.py
------------------------------
Generic YouTube Data API v3 collection: channel-info lookups, video fetching
(API helpers, response parsing, channel list management), and Shorts
labelling. No project-specific values (channel IDs, date windows, output
paths) -- callers supply those.

Video collection strategies
----------------------------
  "playlist"  : retrieve videos via the channel's upload playlist (YouTube Data API v3).
                Stops automatically once videos older than `published_after` are reached,
                so no unnecessary pages are fetched.
  "ytdlp"     : retrieve videos via yt-dlp (no API quota consumed). Useful for channels
                that have more than ~20 000 videos, or when API quota is tight.

Both strategies filter the returned videos to the requested date window
[published_after, published_before] before returning.

Public API
----------
  get_channel_stats(ids, api_key, parts)  Call channels.list for a set of channel IDs.
  collect_channel_stats_df(ids, api_key)  Tidy DataFrame of channel metadata/statistics.
  list_query(api_key, ids, parts)         Call videos.list for a set of video IDs.
  add_statistics(df, api_key)             Enrich a DataFrame with today's view/like/comment counts.
  get_missing_channel_ids(...)            Return channel IDs not yet collected.
  ChannelVideoFetcher                     Fetch videos for a single channel.
  ChannelBatchCollector                   Fetch and save videos for a list of channels.
  ShortsLabeller                          Label videos as Shorts using multi-threaded URL checks.
"""

import os
import datetime
import datetime as dt
import json
import subprocess
import time
import tqdm
import pandas as pd
import googleapiclient.errors
from more_itertools import chunked
from threading import Thread, Condition, Event

from src.utils import create_youtube_client, ISO8601_duration_to_sec, remove_breaklines, is_short
from src.exceptions import EmptyChannelException, ProblemChannelException

_PLAYLIST_ID_ERROR = "<code>playlistId</code> parameter cannot be found."


# ── Channel info ──────────────────────────────────────────────────────────────

def get_channel_stats(channel_ids: str, api_key: str, parts: str = "snippet,contentDetails,statistics") -> dict:
    """
    Call the YouTube Data API channels.list endpoint.

    Args:
        channel_ids: Comma-separated string of channel IDs (max 50 per call).
        api_key:     Google API key.
        parts:       Comma-separated API parts string.

    Returns:
        Raw API response dict.
    """
    youtube = create_youtube_client(api_key)
    return youtube.channels().list(
        part=parts,
        id=channel_ids,
        maxResults=50,
    ).execute()


def collect_channel_stats_df(channel_ids: list[str], api_key: str) -> pd.DataFrame:
    """
    Fetch channel metadata/statistics for a list of channel IDs, batching
    requests in groups of 50 (the API's per-call limit).

    Returns a tidy DataFrame with columns:
        channelId, channelTitle, description, publishedAt,
        number_subscribers, number_videos, number_views
    """
    rows = []
    for batch in chunked(channel_ids, 50):
        response = get_channel_stats(",".join(batch), api_key=api_key)
        for item in response.get("items", []):
            rows.append({
                "channelId": item["id"],
                "channelTitle": item["snippet"]["title"],
                "description": item["snippet"].get("description"),
                "publishedAt": item["snippet"].get("publishedAt"),
                "number_subscribers": item["statistics"].get("subscriberCount"),
                "number_videos": item["statistics"].get("videoCount"),
                "number_views": item["statistics"].get("viewCount"),
            })
    return pd.DataFrame(rows)


# ── Low-level video API helpers ───────────────────────────────────────────────

def list_query(api_key: str, video_ids: str, parts: str) -> dict:
    """
    Call the YouTube Data API videos.list endpoint.

    Args:
        api_key:   Google API key.
        video_ids: Comma-separated string of video IDs (max ~50 per call for
                   most parts; the caller is responsible for batching).
        parts:     Comma-separated API parts string, e.g. "snippet,statistics".

    Returns:
        Raw API response dict.
    """
    youtube = create_youtube_client(api_key)
    return youtube.videos().list(
        part=parts,
        id=video_ids,
        regionCode="US",
    ).execute()


def add_statistics(df: pd.DataFrame, api_key: str) -> pd.DataFrame:
    """
    Enrich *df* with view, like, and comment counts fetched from the API today.

    The statistics columns are named  ``viewCount_on_YYYY-MM-DD``,
    ``likeCount_on_YYYY-MM-DD``, and ``commentCount_on_YYYY-MM-DD``
    where the date suffix is today's date.

    Requests are batched in windows of 500 video-ID characters and retried
    automatically on transient failures.  If a partial failure occurs mid-run,
    whatever has been collected so far is merged and returned.

    Args:
        df:      DataFrame that must contain a ``videoId`` column.
        api_key: Google API key.

    Returns:
        Input DataFrame merged with the three statistics columns.
    """
    today = dt.date.today()
    view_col = f"viewCount_on_{today}"
    like_col = f"likeCount_on_{today}"
    comment_col = f"commentCount_on_{today}"

    ids_str = ",".join(df["videoId"].dropna().unique())
    n_buckets = len(ids_str) // 500
    stat_dfs: list[pd.DataFrame] = []

    for i in tqdm.tqdm(range(n_buckets + 1), desc="Fetching statistics"):
        bucket = (
            ids_str[i * 500:]
            if i == n_buckets
            else ids_str[i * 500: (i + 1) * 500]
        )
        if not bucket.strip(","):
            continue
        try:
            response = list_query(api_key, bucket, parts="statistics,topicDetails")
            page_df = pd.json_normalize(
                response,
                record_path="items",
                meta=["etag", ["pageInfo", "totalResults"], ["pageInfo", "resultsPerPage"]],
                meta_prefix="meta.",
            )
            stat_dfs.append(page_df)
        except Exception as exc:
            print(f"Statistics fetch failed at bucket {i}: {exc}")
            if stat_dfs:
                # Partial merge and return so progress is not lost.
                partial = pd.concat(stat_dfs).rename(columns={
                    "statistics.viewCount": view_col,
                    "statistics.likeCount": like_col,
                    "statistics.commentCount": comment_col,
                })
                return df.merge(
                    partial[["id", view_col, like_col, comment_col]],
                    left_on="videoId", right_on="id",
                )
            raise

    combined_stats = pd.concat(stat_dfs).rename(columns={
        "statistics.viewCount": view_col,
        "statistics.likeCount": like_col,
        "statistics.commentCount": comment_col,
    })

    return df.merge(
        combined_stats[["id", view_col, like_col, comment_col]],
        left_on="videoId", right_on="id",
    )


def _collect_playlist_page(youtube_client, playlist_id: str, page_token=None) -> dict:
    """Fetch a single page of a playlist, returning the raw API response."""
    kwargs = dict(
        part="snippet",
        maxResults=50,
        playlistId=playlist_id,
    )
    if page_token:
        kwargs["pageToken"] = page_token
    return youtube_client.playlistItems().list(**kwargs).execute()


def _process_videos_response(
    api_key: str,
    response: dict,
    from_playlist: bool = False,
) -> pd.DataFrame:
    """
    Convert a multi-page raw API response dict into a single tidy DataFrame.

    Args:
        api_key:       Google API key (passed through to _process_videos_df).
        response:      Dict of the form {"page_0": <API response>, "page_1": ...}.
        from_playlist: Whether the response came from the playlistItems endpoint.

    Returns:
        Concatenated, deduplicated DataFrame of videos.
    """
    dfs = []
    for page in response.values():
        if not page.get("items"):
            continue
        page_df = pd.json_normalize(
            page,
            record_path="items",
            record_prefix="items.",
            meta=["etag", ["pageInfo", "totalResults"], ["pageInfo", "resultsPerPage"]],
            meta_prefix="meta.",
        )
        dfs.append(_process_videos_df(api_key=api_key, videos_df=page_df, from_playlist=from_playlist))

    result = pd.concat(dfs).reset_index(drop=True)
    result["snippet.tags"] = result["snippet.tags"].map(
        lambda x: "#".join(x), na_action="ignore"
    )
    return result.drop_duplicates()


def _process_videos_df(
    api_key: str,
    videos_df: pd.DataFrame,
    from_playlist: bool = False,
) -> pd.DataFrame:
    """
    Select relevant columns, rename them, then enrich with duration/tags/categoryId
    via a secondary videos.list call.

    Args:
        api_key:       Google API key.
        videos_df:     Raw normalised DataFrame from a single API page.
        from_playlist: Whether the data came from the playlistItems endpoint
                       (different column names than the search endpoint).

    Returns:
        Processed DataFrame with clean column names and enriched metadata.
    """
    if not from_playlist:
        keep = [
            "items.id.videoId", "items.snippet.publishedAt", "items.snippet.channelId",
            "items.snippet.title", "items.snippet.description",
            "items.snippet.liveBroadcastContent",
        ]
        df = videos_df[
            (videos_df["items.snippet.liveBroadcastContent"] == "none") &
            (videos_df["items.id.kind"] == "youtube#video")
        ]
        if df.empty:
            return pd.DataFrame(columns=[
                "videoId", "publishedAt", "channelId", "title", "description",
                "liveBroadcastContent", "duration", "snippet.tags", "snippet.categoryId",
            ])
        rename = {c: c.split(".")[2] for c in keep}
    else:
        keep = [
            "items.snippet.resourceId.videoId", "items.snippet.publishedAt",
            "items.snippet.channelId", "items.snippet.title", "items.snippet.description",
            "items.snippet.channelTitle", "items.snippet.playlistId",
        ]
        df = videos_df[videos_df["items.snippet.resourceId.kind"] == "youtube#video"]
        if df.empty:
            return pd.DataFrame(columns=[
                "videoId", "publishedAt", "channelId", "title", "description",
                "channelTitle", "playlistId", "duration", "snippet.tags", "snippet.categoryId",
            ])
        rename = {c: c.split(".")[-1] for c in keep}

    df = df[keep].rename(columns=rename).drop_duplicates().reset_index(drop=True)

    # Enrich with duration, tags, and categoryId via videos.list.
    video_ids = ",".join(df["videoId"].dropna().unique())
    try:
        details = list_query(api_key, video_ids, parts="contentDetails,snippet")
    except googleapiclient.errors.HttpError:
        print("Exceeded API quota during video processing.")
        raise

    details_df = pd.json_normalize(
        details,
        record_path="items",
        meta=["etag", ["pageInfo", "totalResults"], ["pageInfo", "resultsPerPage"]],
        meta_prefix="meta.",
    )

    try:
        details_df["duration"] = details_df["contentDetails.duration"].apply(
            ISO8601_duration_to_sec
        )
    except KeyError:
        details_df["duration"] = float("nan")

    try:
        merged = df.merge(
            details_df[["id", "duration", "snippet.tags", "snippet.categoryId"]],
            left_on="videoId", right_on="id", how="outer",
        )
    except KeyError:
        details_df["snippet.tags"] = None
        merged = df.merge(
            details_df[["id", "duration", "snippet.tags", "snippet.categoryId"]],
            left_on="videoId", right_on="id", how="outer",
        )

    merged["description"] = merged["description"].apply(remove_breaklines)
    merged["title"] = merged["title"].apply(remove_breaklines)
    return merged


# ── Channel list helpers ──────────────────────────────────────────────────────

def get_missing_channel_ids(
    channel_ids: list[str],
    videos_folder: str,
    recollect: bool = False,
) -> list[str]:
    """
    Return channel IDs that have not yet been collected.

    Compares *channel_ids* against channel IDs already present in jsonl files
    inside *videos_folder*. If *recollect=True*, returns all IDs regardless.

    Args:
        channel_ids:    Full reference list of channel IDs.
        videos_folder:  Folder where collected video jsonl files live.
        recollect:      If True, ignore already-collected channels.
    """
    all_ids = set(channel_ids)
    print(f"Total channels in reference list: {len(all_ids)}")

    if recollect:
        return list(all_ids)

    done_ids: set[str] = set()
    for filename in sorted(os.listdir(videos_folder)):
        if not filename.endswith(".jsonl"):
            continue
        try:
            df = pd.read_json(os.path.join(videos_folder, filename), lines=True)
            new_ids = set(df["channelId"].dropna().unique())
            done_ids.update(new_ids)
            print(f"  {filename}: {len(new_ids)} channels | running total: {len(done_ids)}")
        except Exception as exc:
            print(f"  Warning: could not read {filename}: {exc}")

    missing = list(all_ids - done_ids)
    print(f"Channels still to collect: {len(missing)}")
    return missing


# ── Channel-level video fetcher ───────────────────────────────────────────────

class ChannelVideoFetcher:
    """
    Fetches video metadata for a single YouTube channel using one of two strategies:

      - "playlist"  : retrieve videos from the channel's upload playlist (Data API v3).
                      Collection stops early once videos older than `published_after`
                      are encountered, so it is efficient for date-bounded queries.
      - "ytdlp"     : retrieve videos via yt-dlp (subprocess call).

    After fetching, the resulting DataFrame is always filtered to
    [published_after, published_before] before being returned.
    This class is stateless with respect to storage — callers handle saving.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.youtube = create_youtube_client(api_key)

    # ── Public interface ──────────────────────────────────────────────────────

    def fetch(
        self,
        channel_id: str,
        strategy: str = "playlist",
        published_after: str | None = None,
        published_before: str | None = None,
        channel_url: str | None = None,
    ) -> pd.DataFrame:
        """
        Fetch videos for *channel_id* using the chosen *strategy*.

        Args:
            channel_id:       YouTube channel ID (used by "playlist" strategy).
            strategy:         "playlist" or "ytdlp".
            published_after:  ISO 8601 date string — earliest video to keep (inclusive).
                              For "playlist", collection also stops when this boundary
                              is crossed, avoiding redundant API calls.
            published_before: ISO 8601 date string — latest video to keep (inclusive).
            channel_url:      YouTube channel URL used by "ytdlp" strategy
                              (e.g. "https://www.youtube.com/@AFP"). Falls back to
                              constructing a URL from channel_id if omitted.

        Returns:
            DataFrame of videos within the requested date window.
        """
        if strategy == "playlist":
            df = self._fetch_via_playlist(channel_id, published_after)
        elif strategy == "ytdlp":
            url = channel_url or f"https://www.youtube.com/channel/{channel_id}"
            df = self._fetch_via_ytdlp(url)
        else:
            raise NotImplementedError(f"Unknown collection strategy: '{strategy}'")

        return self._filter_date_window(df, published_after, published_before)

    # ── Playlist strategy ─────────────────────────────────────────────────────

    def _fetch_via_playlist(
        self, channel_id: str, published_after: str | None
    ) -> pd.DataFrame:
        """
        Fetch all uploaded videos via the channel's upload playlist.

        Pagination stops as soon as a video older than *published_after* is
        encountered, so this is efficient for bounded time-window queries.
        """
        # Resolve the upload playlist ID.
        response = self.youtube.channels().list(
            part="snippet,contentDetails", id=channel_id
        ).execute()

        if response["pageInfo"]["totalResults"] == 0:
            raise EmptyChannelException(f"Channel '{channel_id}' returned no results.")

        upload_playlist = (
            response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        )

        # Paginate through the playlist, stopping early when possible.
        all_pages: dict[str, dict] = {}
        page_token = None
        page_num = 0
        stop_early = False

        while True:
            try:
                page = _collect_playlist_page(self.youtube, upload_playlist, page_token)
            except Exception as exc:
                if _PLAYLIST_ID_ERROR in getattr(exc, "reason", ""):
                    raise ProblemChannelException(
                        f"Playlist not found for channel '{channel_id}'."
                    )
                raise

            items = page.get("items", [])
            if page_num == 0 and len(items) == 0:
                raise EmptyChannelException(
                    f"Upload playlist for '{channel_id}' is empty."
                )

            all_pages[f"page_{page_num}"] = page
            page_num += 1

            # Early-stop: if the oldest video on this page predates published_after,
            # there is no need to fetch further pages.
            if published_after and items:
                oldest_on_page = min(
                    item["snippet"].get("publishedAt", "9999")
                    for item in items
                )
                if oldest_on_page < published_after:
                    stop_early = True

            page_token = page.get("nextPageToken")
            if not page_token or stop_early:
                break

        return _process_videos_response(
            api_key=self.api_key, response=all_pages, from_playlist=True
        )

    # ── yt-dlp strategy ───────────────────────────────────────────────────────

    def _fetch_via_ytdlp(self, channel_url: str) -> pd.DataFrame:
        """
        Use yt-dlp to extract flat video metadata for an entire channel.
        No API quota is consumed.
        """
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--print-json",
            f"{channel_url}/videos",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "yt-dlp is not installed or not on PATH. "
                "Install it with: pip install yt-dlp"
            ) from exc

        videos = []
        for line in result.stdout.strip().splitlines():
            if line.strip():
                try:
                    videos.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return self._ytdlp_to_dataframe(videos)

    @staticmethod
    def _ytdlp_to_dataframe(ytdlp_data: list[dict]) -> pd.DataFrame:
        """Convert raw yt-dlp JSON records to a tidy DataFrame."""
        rows = []
        for video in ytdlp_data:
            rows.append({
                "videoId": video.get("id"),
                "channelId": video.get("playlist_channel_id"),
                "title": video.get("title"),
                "description": video.get("description"),
                "channelTitle": video.get("playlist_channel"),
                "publishedAt": video.get("upload_date"),  # YYYYMMDD from yt-dlp
                "duration": video.get("duration"),
            })
        df = pd.DataFrame(rows)

        # Normalise yt-dlp's YYYYMMDD date to ISO 8601 YYYY-MM-DD.
        if "publishedAt" in df.columns:
            df["publishedAt"] = pd.to_datetime(
                df["publishedAt"], format="%Y%m%d", errors="coerce"
            ).dt.strftime("%Y-%m-%dT00:00:00Z")

        return df

    # ── Date-window filter ────────────────────────────────────────────────────

    @staticmethod
    def _filter_date_window(
        df: pd.DataFrame,
        published_after: str | None,
        published_before: str | None,
    ) -> pd.DataFrame:
        """Keep only rows within [published_after, published_before]."""
        if "publishedAt" not in df.columns:
            return df
        if published_after:
            # ISO string comparison works correctly for the YYYY-MM-DD… format.
            df = df[df["publishedAt"] >= published_after[:10]]
        if published_before:
            df = df[df["publishedAt"] <= published_before[:10]]
        return df.reset_index(drop=True)


# ── Multi-channel batch collector with daily jsonl output ─────────────────────

class ChannelBatchCollector:
    """
    Iterates over a list of channel IDs, fetches their videos with the chosen
    strategy, and accumulates results into a single daily jsonl file.

    On error, whatever has been collected so far is saved before re-raising,
    so a run can be safely resumed later.
    """

    def __init__(self, output_folder: str, api_key: str):
        self.output_folder = output_folder
        self.api_key = api_key
        self._fetcher = ChannelVideoFetcher(self.api_key)
        self._today = datetime.date.today()

    @property
    def daily_filepath(self) -> str:
        return os.path.join(self.output_folder, f"videos_{self._today}.jsonl")

    def collect(
        self,
        channel_ids: list[str],
        strategy: str = "playlist",
        published_after: str | None = None,
        published_before: str | None = None,
        channel_urls: dict[str, str] | None = None,
        output_filepath: str | None = None,
    ) -> None:
        """
        Collect videos for a list of channels and append to a jsonl file
        (``output_filepath`` if given, otherwise today's dated file).

        Args:
            channel_ids:      List of YouTube channel IDs to process.
            strategy:         "playlist" or "ytdlp".
            published_after:  ISO 8601 start datetime (e.g. "2022-02-11T00:00:00Z").
            published_before: ISO 8601 end datetime   (e.g. "2022-06-26T00:00:00Z").
            channel_urls:     Optional {channel_id: url} mapping used by "ytdlp".
            output_filepath:  Explicit output jsonl path. Defaults to ``daily_filepath``.
        """
        collected: list[pd.DataFrame] = []
        try:
            for channel_id in tqdm.tqdm(channel_ids, desc="Collecting channels"):
                url = (channel_urls or {}).get(channel_id)
                df = self._fetcher.fetch(
                    channel_id=channel_id,
                    strategy=strategy,
                    published_after=published_after,
                    published_before=published_before,
                    channel_url=url,
                )
                if len(df) > 0:
                    collected.append(df)
        except Exception:
            if collected:
                self._save(collected, output_filepath)
            raise

        if collected:
            self._save(collected, output_filepath)

    def _save(self, new_dfs: list[pd.DataFrame], output_filepath: str | None = None) -> None:
        filepath = output_filepath or self.daily_filepath
        combined = pd.concat(new_dfs).reset_index(drop=True)
        if os.path.isfile(filepath):
            existing = pd.read_json(filepath, lines=True)
            combined = pd.concat([existing, combined]).reset_index(drop=True)
            print(f"Appended to existing file — now {len(combined)} rows.")
        else:
            print(f"Creating new file: {filepath}")
        combined.drop_duplicates(subset="videoId").to_json(
            filepath, lines=True, orient="records", force_ascii=False
        )


# ── Shorts labelling (multi-threaded) ─────────────────────────────────────────

class ShortsLabeller:
    """
    Labels each video in a jsonl file as a YouTube Short or not.

    Uses multiple threads to speed up the URL-checking process and saves
    per-thread checkpoints so work can be resumed after an interruption.
    """

    EXPECTED_COLUMNS = [
        "videoId", "publishedAt", "channelId", "title", "description",
        "channelTitle", "playlistId", "id", "duration", "snippet.tags",
        "snippet.categoryId", "isShort",
    ]

    def __init__(self, checkpoint_dir: str, n_threads: int = 50):
        self.checkpoint_dir = checkpoint_dir
        self.n_threads = n_threads
        os.makedirs(checkpoint_dir, exist_ok=True)

    def label_file(self, filepath: str) -> None:
        """
        Label all videos in a jsonl file as Short or not, using parallel threads.
        Supports resuming from checkpoints if previously interrupted.
        """
        df = pd.read_json(filepath, lines=True)
        n_rows = len(df)
        filename = os.path.basename(filepath)

        ready_condition = Condition()
        stop_event = Event()
        stop_event.set()

        threads = [
            Thread(
                target=self._worker,
                args=(
                    i, n_rows, filename, os.path.dirname(filepath),
                    ready_condition, stop_event,
                ),
            )
            for i in range(self.n_threads)
        ]

        for thread in threads:
            with ready_condition:
                thread.start()
                ready_condition.wait()

        try:
            while any(t.is_alive() for t in threads):
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Interrupt received — stopping threads gracefully...")
            stop_event.clear()

        for thread in threads:
            thread.join()

    def merge_checkpoints(self, expected_length: int) -> pd.DataFrame:
        """Merge all per-thread checkpoint files into a single validated DataFrame."""
        dfs = []
        for filename in os.listdir(self.checkpoint_dir):
            if filename == ".DS_Store":
                continue
            df = pd.read_json(os.path.join(self.checkpoint_dir, filename), lines=True)
            assert list(df.columns) == self.EXPECTED_COLUMNS, (
                f"Unexpected columns in {filename}: {list(df.columns)}"
            )
            dfs.append(df)

        merged = pd.concat(dfs).reset_index(drop=True)
        assert len(merged) == expected_length, (
            f"Expected {expected_length} rows after merge, got {len(merged)}."
        )
        return merged.drop_duplicates()

    # ── Internal worker logic ─────────────────────────────────────────────────

    def _worker(
        self,
        thread_idx: int,
        n_rows: int,
        filename: str,
        data_dir: str,
        ready_condition: Condition,
        stop_event: Event,
    ) -> None:
        df = self._load_partition(thread_idx, n_rows, filename, data_dir)

        with ready_condition:
            ready_condition.notify()

        unlabelled = df[~df["isShort"].isin([True, False])].index
        for row_idx in tqdm.tqdm(unlabelled, desc=f"thread_{thread_idx}", position=thread_idx, leave=True):
            video_id = df.loc[row_idx, "videoId"]
            try:
                df.loc[row_idx, "isShort"] = is_short(video_id)
            except KeyboardInterrupt:
                self._save_checkpoint(df, thread_idx)
                raise
            except Exception:
                try:
                    time.sleep(1)
                    df.loc[row_idx, "isShort"] = is_short(video_id)
                except Exception:
                    print(f"Failed twice on videoId: {video_id}")
                    self._save_checkpoint(df, thread_idx)
                    raise

            if not stop_event.is_set():
                self._save_checkpoint(df, thread_idx)
                raise KeyboardInterrupt

        self._save_checkpoint(df, thread_idx)

    def _load_partition(
        self, thread_idx: int, n_rows: int, filename: str, data_dir: str
    ) -> pd.DataFrame:
        df = pd.read_json(os.path.join(data_dir, filename), lines=True)
        df = df.iloc[thread_idx::self.n_threads].reset_index(drop=True)
        df["isShort"] = None

        checkpoint_path = self._checkpoint_path(thread_idx)
        if os.path.isfile(checkpoint_path):
            checkpoint = pd.read_json(checkpoint_path, lines=True)[["videoId", "isShort"]]
            checkpoint.dropna(subset=["isShort"], inplace=True)
            overlap = set(checkpoint["videoId"]) & set(df["videoId"])
            for vid in overlap:
                label = checkpoint.loc[
                    checkpoint["videoId"] == vid, "isShort"
                ].values[0]
                df.loc[df["videoId"] == vid, "isShort"] = label

        return df

    def _checkpoint_path(self, thread_idx: int) -> str:
        return os.path.join(self.checkpoint_dir, f"checkpoint_{thread_idx}.jsonl")

    def _save_checkpoint(self, df: pd.DataFrame, thread_idx: int) -> None:
        df.to_json(self._checkpoint_path(thread_idx), lines=True, orient="records", force_ascii=False)