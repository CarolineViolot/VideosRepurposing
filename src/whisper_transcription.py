"""
src/whisper_transcription.py
------------------------------
Generic video download + faster-whisper transcription helpers. 
"""
from pathlib import Path

from faster_whisper import WhisperModel

from src.tiktok_videos_downloader import TikTokDownloader
from src.youtube_videos_downloader import YouTubeDownloader


def video_url(video_id: str, user: str, platform: str) -> str:
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{user}/video/{video_id}"
    return f"https://www.youtube.com/watch?v={video_id}"


def download_video(video_id: str, user: str, platform: str,
                   tiktok_dl: TikTokDownloader | None = None,
                   youtube_dl: YouTubeDownloader | None = None,
                   cookies_path: str = "") -> "Path | str | None":
    """Download a video and return its local path, the "unavailable" sentinel, or None on failure."""
    if platform == "tiktok":
        return tiktok_dl.download(video_url(video_id, user, platform))

    return youtube_dl.download_audio_cli(video_id, cookies_path=cookies_path)


def transcribe_video(video_path: Path, model: WhisperModel, language: str = "fr") -> dict:
    """Run faster-whisper on an audio/video file (ffmpeg handles decoding)."""
    segments, info = model.transcribe(
        str(video_path),
        language=language,
        beam_size=1,
        task="transcribe",
    )

    segments = list(segments)  # consume the generator

    text = " ".join(seg.text.strip() for seg in segments)
    return {
        "text": text if text.strip() else "[no spoken words]",
        "language": info.language,
        "segments": [
            {"id": i, "start": seg.start, "end": seg.end, "text": seg.text.strip()}
            for i, seg in enumerate(segments)
        ],
    }