"""LRCLIB HTTP client and LRC format parser."""

import re
from dataclasses import dataclass

import httpx

from syncer.models import SyncedLine


@dataclass
class LrcLibResult:
    """Result from LRCLIB API query."""

    track_name: str
    artist_name: str
    album_name: str | None
    duration: float | None
    synced_lyrics: str | None  # LRC format text, e.g. "[00:17.12] line text"
    plain_lyrics: str | None  # plain text
    instrumental: bool


def fetch_lyrics(
    title: str, artist: str, duration: float | None = None
) -> LrcLibResult | None:
    """Fetch lyrics from LRCLIB. Returns None if not found."""
    base_url = "https://lrclib.net/api"

    # Primary: exact get
    params = {"track_name": title, "artist_name": artist}
    if duration is not None:
        params["duration"] = duration

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base_url}/get", params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("instrumental"):
                    return LrcLibResult(
                        track_name=data.get("trackName", title),
                        artist_name=data.get("artistName", artist),
                        album_name=data.get("albumName"),
                        duration=data.get("duration"),
                        synced_lyrics=None,
                        plain_lyrics=None,
                        instrumental=True,
                    )
                return LrcLibResult(
                    track_name=data.get("trackName", title),
                    artist_name=data.get("artistName", artist),
                    album_name=data.get("albumName"),
                    duration=data.get("duration"),
                    synced_lyrics=data.get("syncedLyrics"),
                    plain_lyrics=data.get("plainLyrics"),
                    instrumental=False,
                )

            # Fallback: search
            if resp.status_code == 404:
                search_resp = client.get(
                    f"{base_url}/search",
                    params={"track_name": title, "artist_name": artist},
                )
                if search_resp.status_code == 200:
                    results = search_resp.json()
                    if results:
                        data = results[0]  # Take first result
                        return LrcLibResult(
                            track_name=data.get("trackName", title),
                            artist_name=data.get("artistName", artist),
                            album_name=data.get("albumName"),
                            duration=data.get("duration"),
                            synced_lyrics=data.get("syncedLyrics"),
                            plain_lyrics=data.get("plainLyrics"),
                            instrumental=data.get("instrumental", False),
                        )
    except (httpx.TimeoutException, httpx.RequestError):
        return None

    return None


def parse_lrc(lrc_text: str) -> list[SyncedLine]:
    """Parse LRC format text into SyncedLine list (words array empty — filled by alignment later)."""
    if not lrc_text or not lrc_text.strip():
        return []

    TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})\.(\d{2,3})\]")
    METADATA_TAG_RE = re.compile(r"^\[(?:ti|ar|al|by|length|offset|#|re|ve):.*\]", re.IGNORECASE)

    lines = []
    for raw_line in lrc_text.strip().split("\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        # Skip metadata tags
        if METADATA_TAG_RE.match(raw_line):
            continue
        # Find first timestamp
        m = TIMESTAMP_RE.search(raw_line)
        if not m:
            continue
        minutes = int(m.group(1))
        seconds = int(m.group(2))
        centiseconds = m.group(3)
        # Handle both 2-digit (centiseconds) and 3-digit (milliseconds)
        if len(centiseconds) == 2:
            frac = int(centiseconds) / 100
        else:
            frac = int(centiseconds) / 1000
        timestamp = minutes * 60 + seconds + frac

        # Text is everything after the last timestamp tag
        text = TIMESTAMP_RE.sub("", raw_line).strip()
        if not text:
            continue

        lines.append((timestamp, text))

    # Convert to SyncedLine, setting end = next line's start
    result = []
    for i, (start, text) in enumerate(lines):
        if i + 1 < len(lines):
            end = lines[i + 1][0]
        else:
            end = start + 5.0  # Last line gets 5s duration
        result.append(SyncedLine(text=text, start=start, end=end, words=[]))

    return result
