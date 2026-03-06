"""Spotify Web API client for metadata/ISRC resolution."""

import base64
import re
import time
from typing import Optional

import httpx

from syncer.models import TrackInfo

# Token cache: {token, expires_at}
_token_cache: dict = {"token": None, "expires_at": 0}


def parse_spotify_url(url: str) -> Optional[str]:
    """Extract Spotify track ID from URL or URI.

    Args:
        url: Spotify URL (https://open.spotify.com/track/ID) or URI (spotify:track:ID)

    Returns:
        Track ID string, or None if invalid input
    """
    if not url:
        return None

    # Handle spotify:track:ID format
    uri_match = re.match(r"^spotify:track:([A-Za-z0-9]+)$", url)
    if uri_match:
        return uri_match.group(1)

    # Handle https://open.spotify.com/track/ID format (with optional query params)
    url_match = re.match(r"https?://open\.spotify\.com/track/([A-Za-z0-9]+)", url)
    if url_match:
        return url_match.group(1)

    return None


def get_client_token(client_id: str, client_secret: str) -> Optional[str]:
    """Get Spotify client credentials token.

    Args:
        client_id: Spotify API client ID
        client_secret: Spotify API client secret

    Returns:
        Access token string, or None if credentials empty or request fails
    """
    if not client_id or not client_secret:
        return None

    now = time.time()
    # Return cached token if still valid (with 60s buffer)
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                "https://accounts.spotify.com/api/token",
                headers={"Authorization": f"Basic {credentials}"},
                data={"grant_type": "client_credentials"},
            )
            if resp.status_code == 200:
                data = resp.json()
                _token_cache["token"] = data["access_token"]
                _token_cache["expires_at"] = now + data.get("expires_in", 3600)
                return _token_cache["token"]
    except (httpx.TimeoutException, httpx.RequestError):
        pass

    return None


def resolve_spotify_url(
    url: str, client_id: str = "", client_secret: str = ""
) -> Optional[TrackInfo]:
    """Resolve Spotify URL to TrackInfo.

    Args:
        url: Spotify track URL or URI
        client_id: Spotify API client ID
        client_secret: Spotify API client secret

    Returns:
        TrackInfo object, or None if URL invalid, credentials empty, or request fails
    """
    track_id = parse_spotify_url(url)
    if not track_id:
        return None

    token = get_client_token(client_id, client_secret)
    if not token:
        return None  # No credentials configured — not an error

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"https://api.spotify.com/v1/tracks/{track_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                artists = ", ".join(a["name"] for a in data.get("artists", []))
                return TrackInfo(
                    title=data["name"],
                    artist=artists,
                    duration=data["duration_ms"] / 1000,
                    isrc=data.get("external_ids", {}).get("isrc"),
                    spotify_id=track_id,
                    source_url=url,
                )
    except (httpx.TimeoutException, httpx.RequestError):
        pass

    return None
