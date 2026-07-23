"""
downloader_common.py — Shared utilities for video downloaders.

Used by tiktok_downloader.py and youtube_downloader.py.
"""

import json
import logging
import shutil
import subprocess

log = logging.getLogger("downloader_common")

SUPPORTED_BROWSERS = (
    "chrome", "chromium", "firefox", "edge",
    "safari", "opera", "brave", "vivaldi",
)


# ── Exceptions ────────────────────────────────────────────────────────────────

class DownloadError(Exception):
    """Base class for all downloader errors."""


class NoAudioStreamError(DownloadError):
    """Raised when a downloaded file contains no audio stream."""


class FileNotFoundAfterDownload(DownloadError):
    """Raised when the output file cannot be located after download."""


# ── System checks ─────────────────────────────────────────────────────────────

def require_ffmpeg() -> None:
    """Raise RuntimeError if ffmpeg or ffprobe are not on PATH."""
    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if missing:
        raise RuntimeError(
            f"{', '.join(missing)} not found. Install ffmpeg:\n"
            "  macOS : brew install ffmpeg\n"
            "  Linux : sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )


# ── Audio validation ──────────────────────────────────────────────────────────

def validate_audio(filepath: str, *, logger: logging.Logger | None = None) -> None:
    """
    Raise NoAudioStreamError if *filepath* contains no audio stream.

    Args:
        filepath: Path to the media file to inspect.
        logger:   Logger to use; falls back to the module-level logger.
    """
    _log = logger or log
    _log.info("Validating audio …")
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", filepath],
        capture_output=True,
        text=True,
    )
    streams = json.loads(result.stdout).get("streams", [])
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise NoAudioStreamError(
            f"No audio stream found in: {filepath}\n"
            "The file may be silent, or authentication may have failed.\n"
            "Try --list-formats to inspect what the site is serving."
        )
    _log.info("Audio stream confirmed.")


# ── Cookie helpers ────────────────────────────────────────────────────────────

def cookie_opts(
    browser: str | None,
    cookies_file: str | None,
    *,
    logger: logging.Logger | None = None,
) -> dict:
    """
    Return a yt-dlp options dict for cookie authentication.

    Pass *browser* **or** *cookies_file*, never both (the caller should enforce
    mutual exclusivity before calling this function).

    Args:
        browser:      Browser name (must be in SUPPORTED_BROWSERS).
        cookies_file: Path to a Netscape-format cookies file.
        logger:       Logger for info/warning messages.

    Returns:
        A dict suitable for merging into yt-dlp YoutubeDL options.
    """
    _log = logger or log
    if browser:
        _log.info(f"Cookie source: {browser} browser profile")
        return {"cookiesfrombrowser": (browser.lower(),)}
    if cookies_file:
        _log.info(f"Cookie source: {cookies_file}")
        return {"cookiefile": cookies_file}
    _log.warning(
        "No cookies supplied — the site may restrict available formats. "
        "Use --browser or --cookies."
    )
    return {}
