"""
TikTok Video Downloader with Audio Validation

TikTok exposes duplicate format variants (-0 and -1) for every stream.
The -1 variants are video-only despite reporting aac in metadata.
This script picks only -0 variants, guaranteeing audio is present.

Requirements:
    pip install yt-dlp
    brew install ffmpeg   # macOS
    apt install ffmpeg    # Linux

Usage:
    python tiktok_downloader.py URL [URL ...]
    python tiktok_downloader.py --browser firefox URL
    python tiktok_downloader.py --cookies cookies.txt URL
    python tiktok_downloader.py --list-formats URL
    python tiktok_downloader.py -o ~/tiktoks URL1 URL2
"""

import logging
import os
import re
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
log = logging.getLogger("tiktok_downloader")

# Re-export for callers that import from this module.
__all__ = [
    "TikTokDownloader",
    "DownloadError",
    "NoAudioStreamError",
    "FileNotFoundAfterDownload",
    "SUPPORTED_BROWSERS",
]

# Keep the old name as an alias for backwards compatibility.
TikTokDownloadError = DownloadError


# ── Format selection ──────────────────────────────────────────────────────────

def pick_best_format(formats: list[dict]) -> str:
    """
    Return the format_id of the best TikTok format that carries real audio.

    TikTok's -0 variants have audio; -1 variants are video-only duplicates
    despite reporting 'aac' in their metadata.  Prefers h264, then highest
    resolution, then highest total bitrate.
    """
    candidates = [
        f for f in formats
        if not re.search(r"-[1-9]\d*$", f.get("format_id", ""))  # keep only -0
        and (f.get("acodec") or "none").lower() != "none"
    ]
    if not candidates:
        raise DownloadError(
            "No audio-bearing format found. Run --list-formats to debug."
        )
    candidates.sort(key=lambda f: (
        0 if "h264" in (f.get("vcodec") or "") else 1,
        -(f.get("height") or 0),
        -(f.get("tbr") or 0),
    ))
    chosen = candidates[0]
    log.info(
        f"Format: {chosen['format_id']} "
        f"({chosen.get('vcodec', '?')} / {chosen.get('acodec', '?')} / "
        f"{chosen.get('height', '?')}p)"
    )
    return chosen["format_id"]


# ── Downloader ────────────────────────────────────────────────────────────────

class TikTokDownloader:
    def __init__(
        self,
        output_dir: str = "downloads",
        browser: str | None = "chrome",
        cookies_file: str | None = None,
    ) -> None:
        require_ffmpeg()
        if browser and cookies_file:
            raise ValueError("Use browser or cookies_file, not both.")
        self.output_dir = os.path.abspath(output_dir)
        self._cookies = cookie_opts(browser, cookies_file, logger=log)

    def list_formats(self, url: str) -> None:
        """Print all available formats for *url* (does not download)."""
        with yt_dlp.YoutubeDL(
            {"listformats": True, "quiet": False, **self._cookies}
        ) as ydl:
            ydl.extract_info(url, download=False)

    def download(self, url: str) -> str:
        """Download a single TikTok video and return its local path."""
        log.info(f"Downloading: {url}")

        # Step 1: fetch metadata only → select the right format id.
        with yt_dlp.YoutubeDL(
            {"quiet": True, "skip_download": True, **self._cookies}
        ) as ydl:
            info = ydl.extract_info(url, download=False)

        fmt_id = pick_best_format(info.get("formats", []))

        # Step 2: download the selected format and remux into MP4.
        os.makedirs(self.output_dir, exist_ok=True)
        opts = {
            "format": fmt_id,
            "outtmpl": os.path.join(self.output_dir, "%(id)s.%(ext)s"),
            "postprocessors": [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}
            ],
            "retries": 10,
            "fragment_retries": 10,
            "socket_timeout": 30,
            **self._cookies,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        filepath = self._find_file(info)
        validate_audio(filepath, logger=log)
        log.info(f"Saved: {filepath}")
        return filepath

    def download_many(self, urls: list[str]) -> list[str]:
        """
        Download multiple URLs in sequence.

        Errors on individual URLs are logged but do not abort the batch.
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

    def _find_file(self, info: dict) -> str:
        """Locate the downloaded file using several fallback strategies."""
        for key in ("filepath", "_filename", "filename"):
            val = info.get(key)
            if val and os.path.isfile(str(val)):
                return str(val)

        for rd in info.get("requested_downloads", []):
            for key in ("filepath", "filename", "_filename"):
                val = rd.get(key)
                if val and os.path.isfile(str(val)):
                    return str(val)

        video_id = info.get("id", "unknown")
        candidate = os.path.join(self.output_dir, f"{video_id}.mp4")
        if os.path.isfile(candidate):
            return candidate

        matches = sorted(
            Path(self.output_dir).glob(f"*{video_id}*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return str(matches[0])

        raise FileNotFoundAfterDownload(
            f"Could not find downloaded file in {self.output_dir}"
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description="Download TikTok videos with guaranteed audio."
    )
    p.add_argument("urls", nargs="+", metavar="URL")
    p.add_argument("-o", "--output-dir", default="downloads")
    p.add_argument(
        "--list-formats", action="store_true",
        help="List available formats and exit (no download).",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--browser",
        default="chrome",
        choices=SUPPORTED_BROWSERS,
        help="Browser to pull TikTok cookies from (must be closed). Default: chrome",
    )
    g.add_argument("--cookies", default=None, metavar="FILE")
    args = p.parse_args()

    dl = TikTokDownloader(
        output_dir=args.output_dir,
        browser=args.browser if not args.cookies else None,
        cookies_file=args.cookies,
    )

    if args.list_formats:
        for url in args.urls:
            dl.list_formats(url)
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
