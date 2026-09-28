"""
YouTube Video Downloader

Mirrors the TikTokDownloader interface so both classes are interchangeable.

YouTube format strategy: YouTube serves video and audio as *separate* adaptive streams (DASH).  yt-dlp
merges them automatically via ffmpeg when given a combined format string such as ``bestvideo+bestaudio``.

Quality presets:
``"best"``       — best video + best audio (default)
``"1080p"``      — up to 1080p video + best audio
``"720p"``       — up to  720p video + best audio
``"480p"``       — up to  480p video + best audio
``"audio-only"`` — best audio, saved as .m4a (no video, no ffmpeg merge needed)

Requirements: yt-dlp, ffmpeg

Usage:
    python youtube_videos_downloader.py URL [URL ...]
    python youtube_videos_downloader.py --quality 1080p URL
    python youtube_videos_downloader.py --audio-only URL
    python youtube_videos_downloader.py --subs URL
    python youtube_videos_downloader.py --browser firefox URL
    python youtube_videos_downloader.py --cookies cookies.txt URL
    python youtube_videos_downloader.py --list-formats URL
    python youtube_videos_downloader.py -o ~/videos URL1 URL2
    python youtube_videos_downloader.py --playlist URL
"""

import logging
import os
import subprocess
from pathlib import Path

import yt_dlp

from src.downloader_utils import (
    SUPPORTED_BROWSERS,
    DownloadError,
    FileNotFoundAfterDownload,
    NoAudioStreamError,
    cookie_opts,
    require_ffmpeg,
    validate_audio,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("youtube_videos_downloader")

# Re-export so callers that import from this module get everything they need.
__all__ = [
    "YouTubeDownloader",
    "DownloadError",
    "NoAudioStreamError",
    "FileNotFoundAfterDownload",
    "SUPPORTED_BROWSERS",
]

# yt-dlp format strings for each preset.
# ``bestvideo[ext=mp4]`` prefers h264 MP4, falling back to any video if absent.
_FORMAT_PRESETS: dict[str, str] = {
    "best":       "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "1080p":      "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p":       "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":       "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]",
    "audio-only": "bestaudio[ext=m4a]/bestaudio",
}


# ── Downloader ────────────────────────────────────────────────────────────────

class YouTubeDownloader:
    """
    Download YouTube videos (or audio) with yt-dlp.

    Parameters
    ----------
    output_dir:
        Directory where downloaded files are saved.  Created if absent.
    quality:
        One of ``"best"``, ``"1080p"``, ``"720p"``, ``"480p"``,
        ``"audio-only"``.  Defaults to ``"best"``.
    browser:
        Browser name to pull cookies from (must be closed while running).
        Mutually exclusive with *cookies_file*.
    cookies_file:
        Path to a Netscape-format cookies file exported from your browser.
        Mutually exclusive with *browser*.
    write_subs:
        Download auto-generated and manual subtitles (SRT/VTT) alongside
        the video.
    validate:
        When ``True`` (default), run ffprobe after download to confirm an
        audio stream is present.  Set to ``False`` for audio-only downloads
        where the check is implicit, or to skip the extra subprocess call.
    """

    def __init__(
        self,
        output_dir: str = "downloads",
        quality: str = "best",
        browser: str | None = None,
        cookies_file: str | None = None,
        write_subs: bool = False,
        validate: bool = True,
    ) -> None:
        if quality not in _FORMAT_PRESETS:
            raise ValueError(
                f"Unknown quality preset {quality!r}. "
                f"Choose from: {', '.join(_FORMAT_PRESETS)}"
            )
        if browser and cookies_file:
            raise ValueError("Supply browser or cookies_file, not both.")

        require_ffmpeg()

        self.output_dir = os.path.abspath(output_dir)
        self.quality = quality
        self.write_subs = write_subs
        self._validate = validate and quality != "audio-only"
        self._cookies = cookie_opts(browser, cookies_file, logger=log)
        self._fmt = _FORMAT_PRESETS[quality]

    # ── Public API ────────────────────────────────────────────────────────────

    def list_formats(self, url: str) -> None:
        """Print all available formats for *url* (does not download)."""
        opts = {"listformats": True, "quiet": False, **self._cookies}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=False)

    def download(self, url: str) -> str:
        """
        Download a single video (or audio track) and return its local path.

        Raises
        ------
        DownloadError
            On any download-level failure.
        NoAudioStreamError
            If the downloaded file has no audio stream (and *validate* is True).
        FileNotFoundAfterDownload
            If the output file cannot be located after a successful yt-dlp run.
        """
        log.info(f"Downloading ({self.quality}): {url}")
        os.makedirs(self.output_dir, exist_ok=True)

        is_audio_only = self.quality == "audio-only"
        ext = "m4a" if is_audio_only else "mp4"

        opts: dict = {
            "format": self._fmt,
            "outtmpl": os.path.join(self.output_dir, "%(id)s.%(ext)s"),
            "retries": 10,
            "fragment_retries": 10,
            "socket_timeout": 30,
            **self._cookies,
        }

        if is_audio_only:
            # Keep the native m4a container; no remux needed.
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}
            ]
        else:
            # Remux the merged stream into a clean MP4 container.
            opts["postprocessors"] = [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}
            ]

        if self.write_subs:
            opts.update(
                {
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    "subtitleslangs": ["en"],
                    "subtitlesformat": "srt/vtt",
                }
            )

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        filepath = self._find_file(info, ext)

        if self._validate:
            validate_audio(filepath, logger=log)

        log.info(f"Saved: {filepath}")
        return filepath

    def download_many(self, urls: list[str]) -> list[str]:
        """
        Download multiple URLs in sequence.

        Errors on individual URLs are logged but do not abort the batch.

        Returns
        -------
        list[str]
            Paths of successfully downloaded files (failed URLs are omitted).
        """
        results: list[str] = []
        total = len(urls)
        for i, url in enumerate(urls, 1):
            log.info(f"[{i}/{total}] {url}")
            try:
                results.append(self.download(url))
            except DownloadError as exc:
                log.error(f"Failed: {exc}")
        return results

    def download_playlist(self, url: str) -> list[str]:
        """
        Download every video in a YouTube playlist.

        This is a thin wrapper around :meth:`download` that sets yt-dlp's
        ``noplaylist`` flag to ``False`` (the default for playlist URLs) and
        collects per-entry results.

        Returns
        -------
        list[str]
            Paths of successfully downloaded files.
        """
        log.info(f"Fetching playlist metadata: {url}")
        with yt_dlp.YoutubeDL(
            {"quiet": True, "extract_flat": True, **self._cookies}
        ) as ydl:
            playlist_info = ydl.extract_info(url, download=False)

        entries = playlist_info.get("entries") or []
        if not entries:
            log.warning("Playlist appears empty or is a single video — downloading as-is.")
            return [self.download(url)]

        video_urls = [e["url"] if e.get("url", "").startswith("http") else
                      f"https://www.youtube.com/watch?v={e['id']}"
                      for e in entries if e.get("id")]
        log.info(f"Playlist: {len(video_urls)} videos")
        return self.download_many(video_urls)

    def download_audio_cli(self, video_id: str, cookies_path: str = "") -> "Path | str | None":
        """
        Download only the audio track for *video_id* by shelling out to the
        yt-dlp CLI directly (bypassing yt_dlp's Python API), passing
        --js-runtimes/--remote-components to satisfy YouTube's current JS
        challenge requirement.

        Returns the downloaded file's Path, the string "unavailable" if the
        video is unavailable, or None on any other download failure.
        """
        os.makedirs(self.output_dir, exist_ok=True)
        url = f"https://www.youtube.com/watch?v={video_id}"
        out_template = os.path.join(self.output_dir, f"{video_id}.%(ext)s")

        cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "5",
            "--format", "bestaudio[ext=m4a]/bestaudio",
            "--output", out_template,
            "--js-runtimes", "node:/opt/homebrew/bin/node",
            "--remote-components", "ejs:github",
            "--quiet",
        ]

        if cookies_path:
            cmd += ["--cookies", cookies_path]

        cmd += [url]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            if "Video unavailable" in stderr:
                return "unavailable"  # sentinel distinct from None
            log.error(f"Download failed: {stderr}\ncheck video at {url}")
            return None

        matches = list(Path(self.output_dir).glob(f"{video_id}.*"))
        return matches[0] if matches else None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _find_file(self, info: dict, preferred_ext: str) -> str:
        """Locate the downloaded file using several fallback strategies."""
        # 1. Keys that yt-dlp may populate directly on the info dict.
        for key in ("filepath", "_filename", "filename"):
            val = info.get(key)
            if val and os.path.isfile(str(val)):
                return str(val)

        # 2. requested_downloads list (present after merging streams).
        for rd in info.get("requested_downloads", []):
            for key in ("filepath", "filename", "_filename"):
                val = rd.get(key)
                if val and os.path.isfile(str(val)):
                    return str(val)

        # 3. Reconstruct from the output template.
        video_id = info.get("id", "unknown")
        candidate = os.path.join(self.output_dir, f"{video_id}.{preferred_ext}")
        if os.path.isfile(candidate):
            return candidate

        # 4. Glob fallback — pick the most recently modified match.
        matches = sorted(
            Path(self.output_dir).glob(f"*{video_id}*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return str(matches[0])

        raise FileNotFoundAfterDownload(
            f"Cannot find downloaded file for video id '{video_id}' "
            f"in {self.output_dir}"
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description="Download YouTube videos with yt-dlp.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("urls", nargs="+", metavar="URL")
    p.add_argument("-o", "--output-dir", default="downloads", metavar="DIR")
    p.add_argument(
        "-q", "--quality",
        default="best",
        choices=list(_FORMAT_PRESETS),
        help="Quality preset (default: best)",
    )
    p.add_argument(
        "--audio-only",
        action="store_true",
        help="Download audio only (.m4a). Shortcut for --quality audio-only.",
    )
    p.add_argument(
        "--subs",
        action="store_true",
        help="Also download subtitles (English, SRT/VTT).",
    )
    p.add_argument(
        "--playlist",
        action="store_true",
        help="Treat URL(s) as playlist(s) and download all videos.",
    )
    p.add_argument(
        "--list-formats",
        action="store_true",
        help="List available formats and exit (no download).",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--browser",
        default=None,
        choices=SUPPORTED_BROWSERS,
        help="Browser to pull cookies from (must be closed). Default: none.",
    )
    g.add_argument(
        "--cookies",
        default=None,
        metavar="FILE",
        help="Path to a Netscape cookies file.",
    )
    args = p.parse_args()

    quality = "audio-only" if args.audio_only else args.quality

    dl = YouTubeDownloader(
        output_dir=args.output_dir,
        quality=quality,
        browser=args.browser,
        cookies_file=args.cookies,
        write_subs=args.subs,
    )

    if args.list_formats:
        for url in args.urls:
            dl.list_formats(url)
        return

    if args.playlist:
        for url in args.urls:
            paths = dl.download_playlist(url)
            for path in paths:
                print(f"Downloaded: {path}")
        return

    paths = (
        dl.download_many(args.urls)
        if len(args.urls) > 1
        else [dl.download(args.urls[0])]
    )
    for path in paths:
        print(f"Downloaded: {path}")


if __name__ == "__main__":
    main()
