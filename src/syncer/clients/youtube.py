"""YouTube audio extraction client using yt-dlp."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

logger = logging.getLogger(__name__)


@dataclass
class AudioResult:
    """Result of audio extraction from YouTube."""

    audio_path: Path
    title: str
    duration: float  # seconds
    youtube_id: str


def parse_youtube_url(url: str) -> str | None:
    """
    Extract YouTube video ID from various URL formats.

    Args:
        url: YouTube URL in various formats

    Returns:
        11-character video ID or None if invalid
    """
    if not url:
        return None

    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|music\.youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
    ]

    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)

    return None


def extract_audio(
    url: str, output_dir: Path, max_duration: int = 600
) -> AudioResult:
    """
    Download audio from YouTube URL as WAV.

    Args:
        url: YouTube URL
        output_dir: Directory to save WAV file
        max_duration: Maximum allowed video duration in seconds

    Returns:
        AudioResult with audio_path, title, duration, youtube_id

    Raises:
        ValueError: For invalid URLs or videos exceeding max_duration
        RuntimeError: For download failures
    """
    video_id = parse_youtube_url(url)
    if not video_id:
        raise ValueError(f"Not a valid YouTube URL: {url}")

    # Check duration first without downloading
    info_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration", 0)
            if duration > max_duration:
                raise ValueError(
                    f"Video duration {duration}s exceeds maximum {max_duration}s"
                )
            title = info.get("title", "Unknown")
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"Could not access video: {e}") from e

    # Download audio as WAV
    output_template = str(output_dir / f"{video_id}.%(ext)s")
    download_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        ],
    }

    try:
        with yt_dlp.YoutubeDL(download_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"Download failed: {e}") from e

    # Find the output file
    wav_files = list(output_dir.glob(f"{video_id}*.wav"))
    if not wav_files:
        raise RuntimeError(
            f"Download completed but WAV file not found in {output_dir}"
        )

    return AudioResult(
        audio_path=wav_files[0],
        title=title,
        duration=float(duration),
        youtube_id=video_id,
    )


def search_youtube(query: str) -> str | None:
    """
    Search YouTube and return URL of first result.

    Args:
        query: Search query string

    Returns:
        YouTube URL of first result or None on failure
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "default_search": "ytsearch",
        "extract_flat": True,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if info and info.get("entries"):
                entry = info["entries"][0]
                video_id = entry.get("id")
                if video_id:
                    return f"https://www.youtube.com/watch?v={video_id}"
    except Exception:
        pass

    return None
