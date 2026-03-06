"""Sync pipeline orchestrator — coordinates all sub-modules into a single sync() call."""

import logging
import re
import tempfile
import tempfile
import time
from pathlib import Path

from syncer.alignment.demucs_separator import VocalSeparator
from syncer.alignment.whisperx_aligner import WordAligner
from syncer.alignment.snap import snap_words_to_lyrics, compute_confidence
from syncer.cache import CacheManager
from syncer.clients.lrclib import fetch_lyrics, parse_lrc
from syncer.clients.spotify import resolve_spotify_url, parse_spotify_url
from syncer.clients.youtube import extract_audio, search_youtube, parse_youtube_url
from syncer.config import Settings
from syncer.models import SyncRequest, SyncResult, SyncedLine, SyncedWord, TrackInfo

logger = logging.getLogger(__name__)


class SyncPipeline:
    """Orchestrates the full lyrics sync pipeline.

    Steps: resolve input → check cache → fetch lyrics → extract audio →
    vocal isolation → word alignment → snap to lyrics → build result → cache.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cache = CacheManager(settings.db_path)
        self.separator = VocalSeparator(settings.demucs_model)
        self.aligner = WordAligner(
            settings.whisperx_model,
            settings.whisperx_device,
            settings.whisperx_compute_type,
        )

    def sync(self, request: SyncRequest) -> SyncResult:
        """Run the full sync pipeline for a single track.

        Args:
            request: SyncRequest with url, title, and/or artist.

        Returns:
            SyncResult with synced lines, confidence, and timing source.

        Raises:
            ValueError: If input is invalid or insufficient.
            RuntimeError: If audio extraction, separation, or alignment fails.
        """
        start_time = time.time()
        language = request.language

        # Step 1: Resolve input — determine title, artist, youtube URL
        track_info, youtube_url = self._resolve_input(request)

        # Step 2: Check cache
        cached = self.cache.get_cached(
            track_info.title, track_info.artist, track_info.duration, language=language
        )
        if cached is not None:
            cached.processing_time_seconds = time.time() - start_time
            return cached

        # Step 3: Fetch lyrics from LRCLIB
        lyrics_lines: list[SyncedLine] | None = None
        plain_lyrics_text: list[str] | None = None
        timing_source = "whisperx_only"

        try:
            lrclib_result = fetch_lyrics(
                track_info.title, track_info.artist, track_info.duration
            )
            if lrclib_result is not None:
                if lrclib_result.synced_lyrics:
                    lyrics_lines = parse_lrc(lrclib_result.synced_lyrics)
                    if lyrics_lines:
                        timing_source = "lrclib_synced"
                        # Also extract plain text for snap alignment
                        plain_lyrics_text = [line.text for line in lyrics_lines]
                if plain_lyrics_text is None and lrclib_result.plain_lyrics:
                    plain_lyrics_text = [
                        line.strip()
                        for line in lrclib_result.plain_lyrics.strip().split("\n")
                        if line.strip()
                    ]
                    timing_source = "lrclib_enhanced"
        except Exception:
            logger.warning(
                "LRCLIB fetch failed for %s - %s, proceeding without lyrics",
                track_info.title,
                track_info.artist,
            )

        # Step 4: Audio extraction
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_dir = Path(tmp_dir)
            audio_result = None

            try:
                if youtube_url:
                    audio_result = extract_audio(
                        youtube_url, temp_dir, self.settings.max_song_duration
                    )
                else:
                    # Search YouTube by title + artist
                    query = f"{track_info.title} {track_info.artist}"
                    yt_url = search_youtube(query)
                    if yt_url is None:
                        raise RuntimeError(
                            f"Could not find audio for: {query}"
                        )
                    audio_result = extract_audio(
                        yt_url, temp_dir, self.settings.max_song_duration
                    )
            except (ValueError, RuntimeError) as e:
                # If we have synced lyrics from LRCLIB, return those without word timestamps
                if timing_source == "lrclib_synced" and lyrics_lines:
                    logger.warning(
                        "Audio extraction failed (%s), returning LRCLIB synced lyrics only",
                        e,
                    )
                    result = SyncResult(
                        track=track_info,
                        lines=lyrics_lines,
                        confidence=compute_confidence(lyrics_lines),
                        timing_source="lrclib_synced",
                        cached=False,
                        processing_time_seconds=time.time() - start_time,
                        detected_language=None,
                    )
                    self.cache.store_result(result, language=language)
                    return result
                raise RuntimeError(f"Could not download audio: {e}") from e

            # Update track info from audio result if we didn't have it
            if audio_result.youtube_id and not track_info.youtube_id:
                track_info.youtube_id = audio_result.youtube_id
            if track_info.duration == 0.0 and audio_result.duration > 0:
                track_info.duration = audio_result.duration

            # If title was unknown (YouTube URL without metadata), extract from yt-dlp
            if track_info.title == "Unknown" and audio_result.title != "Unknown":
                parsed_title, parsed_artist = SyncPipeline._parse_video_title(
                    audio_result.title
                )
                track_info.title = parsed_title
                if track_info.artist == "Unknown" and parsed_artist:
                    track_info.artist = parsed_artist

                # Re-attempt LRCLIB fetch with real metadata
                logger.info(
                    "Extracted metadata from YouTube: %s - %s, retrying LRCLIB",
                    track_info.title,
                    track_info.artist,
                )
                try:
                    lrclib_result = fetch_lyrics(
                        track_info.title, track_info.artist, track_info.duration
                    )
                    if lrclib_result is not None:
                        if lrclib_result.synced_lyrics:
                            lyrics_lines = parse_lrc(lrclib_result.synced_lyrics)
                            if lyrics_lines:
                                timing_source = "lrclib_synced"
                                plain_lyrics_text = [line.text for line in lyrics_lines]
                        if plain_lyrics_text is None and lrclib_result.plain_lyrics:
                            plain_lyrics_text = [
                                line.strip()
                                for line in lrclib_result.plain_lyrics.strip().split("\n")
                                if line.strip()
                            ]
                            timing_source = "lrclib_enhanced"
                except Exception:
                    logger.warning(
                        "LRCLIB retry failed for %s - %s",
                        track_info.title,
                        track_info.artist,
                    )

            # Step 5: Vocal isolation
            try:
                vocals_path = self.separator.separate(
                    audio_result.audio_path, temp_dir
                )
            except Exception as e:
                raise RuntimeError(f"Vocal separation failed: {e}") from e

            # Step 6: Word alignment
            try:
                alignment_result = self.aligner.align(vocals_path, language=language)
            except Exception as e:
                raise RuntimeError(f"Alignment failed: {e}") from e

            # Step 7: Snap to lyrics
            asr_words = alignment_result.words
            detected_language = alignment_result.detected_language
            if plain_lyrics_text:
                synced_lines = snap_words_to_lyrics(asr_words, plain_lyrics_text)
                # Keep timing_source from step 3 (lrclib_synced or lrclib_enhanced)
                if timing_source == "lrclib_synced":
                    timing_source = "lrclib_enhanced"  # Now enhanced with word timestamps
            elif asr_words:
                # No lyrics — build SyncedLines directly from ASR words
                synced_lines = SyncPipeline._lines_from_asr(asr_words)
                timing_source = "whisperx_only"
            else:
                synced_lines = []
                timing_source = "whisperx_only"


        # Step 8: Build result
        result = SyncResult(
            track=track_info,
            lines=synced_lines,
            confidence=compute_confidence(synced_lines),
            timing_source=timing_source,
            cached=False,
            processing_time_seconds=time.time() - start_time,
            detected_language=detected_language,
        )

        # Step 9: Cache result
        self.cache.store_result(result, language=language)

        return result

    def _resolve_input(
        self, request: SyncRequest
    ) -> tuple[TrackInfo, str | None]:
        """Resolve request into TrackInfo and optional YouTube URL.

        Returns:
            Tuple of (TrackInfo, youtube_url_or_None).

        Raises:
            ValueError: If request has no usable input.
        """
        youtube_url: str | None = None

        if request.url:
            # Spotify URL
            if "spotify.com" in request.url or request.url.startswith("spotify:"):
                try:
                    track_info = resolve_spotify_url(
                        request.url,
                        self.settings.spotify_client_id,
                        self.settings.spotify_client_secret,
                    )
                    if track_info is not None:
                        track_info.source_url = request.url
                        return track_info, None
                except Exception:
                    logger.warning(
                        "Spotify resolution failed for %s, falling back",
                        request.url,
                    )

                # Spotify failed — need title/artist from request as fallback
                if request.title:
                    return (
                        TrackInfo(
                            title=request.title,
                            artist=request.artist or "Unknown",
                            duration=0.0,
                            source_url=request.url,
                        ),
                        None,
                    )
                raise ValueError(
                    "Spotify URL could not be resolved and no title provided"
                )

            # YouTube URL
            video_id = parse_youtube_url(request.url)
            if video_id is not None:
                youtube_url = request.url
                # We'll get metadata from extract_audio; use placeholders
                return (
                    TrackInfo(
                        title=request.title or "Unknown",
                        artist=request.artist or "Unknown",
                        duration=0.0,
                        youtube_id=video_id,
                        source_url=request.url,
                    ),
                    youtube_url,
                )

            raise ValueError(f"Unsupported URL format: {request.url}")

        # Title/artist provided directly
        if request.title:
            return (
                TrackInfo(
                    title=request.title,
                    artist=request.artist or "Unknown",
                    duration=0.0,
                ),
                None,
            )

        raise ValueError("Must provide url, title, or artist")

    @staticmethod
    def _lines_from_asr(asr_words: list) -> list[SyncedLine]:
        """Build SyncedLines from ASR words when no lyrics are available.

        Groups words into lines of ~10 words each.
        """
        if not asr_words:
            return []

        lines: list[SyncedLine] = []
        chunk_size = 10
        for i in range(0, len(asr_words), chunk_size):
            chunk = asr_words[i : i + chunk_size]
            synced_words = [
                SyncedWord(
                    text=w.word.strip(),
                    start=w.start,
                    end=w.end,
                    confidence=getattr(w, "score", 0.0),
                )
                for w in chunk
            ]
            text = " ".join(sw.text for sw in synced_words)
            lines.append(
                SyncedLine(
                    text=text,
                    start=synced_words[0].start,
                    end=synced_words[-1].end,
                    words=synced_words,
                )
            )

        return lines

    @staticmethod
    def _parse_video_title(video_title: str) -> tuple[str, str | None]:
        """Parse YouTube video title into (title, artist)."""
        # Common formats: "Artist - Title", "Artist - Title (Official Video)", etc.
        # Strip common suffixes first
        cleaned = video_title.strip()
        cleaned = video_title.strip()
        # Remove common YouTube suffixes
        suffixes = [
            r"\s*\(Official\s*(Music\s*)?Video\)",
            r"\s*\(Official\s*Audio\)",
            r"\s*\(Lyric\s*Video\)",
            r"\s*\(Lyrics\)",
            r"\s*\[Official\s*(Music\s*)?Video\]",
            r"\s*\[Official\s*Audio\]",
            r"\s*\(HD\)",
            r"\s*\(HQ\)",
            r"\s*\|.*$",
        ]
        for suffix in suffixes:
            cleaned = re.sub(suffix, "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        # Try "Artist - Title" split
        if " - " in cleaned:
            parts = cleaned.split(" - ", 1)
            artist = parts[0].strip()
            title = parts[1].strip()
            if artist and title:
                return title, artist

        # No separator found — use whole string as title
        return cleaned, None
