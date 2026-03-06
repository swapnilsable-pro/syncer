"""Unit tests for CLI entry point."""

import sys
from io import StringIO
from unittest.mock import patch, MagicMock
import pytest

from syncer.__main__ import main


class TestHelpFlag:
    """Test --help flag."""

    def test_help_flag(self, capsys):
        """--help should exit with code 0."""
        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["syncer", "--help"]):
                main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower()


class TestEmptyQuery:
    """Test empty query handling."""

    def test_empty_query_exits_nonzero(self, capsys):
        """Empty query should exit with code 1 and error on stderr."""
        with patch("sys.argv", ["syncer", ""]):
            result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "empty" in captured.err.lower()


class TestURLDetection:
    """Test URL vs query detection."""

    def test_youtube_url_detected(self, capsys):
        """YouTube URL should be passed as url= parameter."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch(
            "sys.argv", ["syncer", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
        ):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        # Verify URL was passed as url= not title=
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.url is not None
        assert call_args.title is None

    def test_youtu_be_url_detected(self, capsys):
        """youtu.be short URL should be detected."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "https://youtu.be/dQw4w9WgXcQ"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.url is not None

    def test_spotify_url_detected(self, capsys):
        """Spotify URL should be detected."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "https://open.spotify.com/track/123"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.url is not None

    def test_spotify_uri_detected(self, capsys):
        """Spotify URI format should be detected."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "spotify:track:123"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.url is not None


class TestTitleArtistSplit:
    """Test title/artist query parsing."""

    def test_title_artist_split(self, capsys):
        """Query with ' - ' should split into artist and title."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "The Beatles - Yesterday"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.title == "Yesterday"
        assert call_args.artist == "The Beatles"
        assert call_args.url is None

    def test_title_only_query(self, capsys):
        """Query without ' - ' should be treated as title only."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "Yesterday"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.title == "Yesterday"
        assert call_args.artist is None
        assert call_args.url is None

    def test_title_artist_with_multiple_dashes(self, capsys):
        """Query with multiple ' - ' should split on first occurrence."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "Artist - Song - Remix"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.artist == "Artist"
        assert call_args.title == "Song - Remix"


class TestPipelineError:
    """Test error handling from pipeline."""

    def test_pipeline_value_error_exits_nonzero(self, capsys):
        """ValueError from pipeline should exit with code 1."""
        mock_pipeline = MagicMock()
        mock_pipeline.sync.side_effect = ValueError("Invalid input")

        with patch("sys.argv", ["syncer", "Yesterday Beatles"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_pipeline_runtime_error_exits_nonzero(self, capsys):
        """RuntimeError from pipeline should exit with code 1."""
        mock_pipeline = MagicMock()
        mock_pipeline.sync.side_effect = RuntimeError("Could not download audio")

        with patch("sys.argv", ["syncer", "Yesterday Beatles"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "Could not download audio" in captured.err


class TestSuccessOutput:
    """Test successful execution and JSON output."""

    def test_success_prints_json_to_stdout(self, capsys):
        """Successful sync should print JSON to stdout."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        json_output = (
            '{"track": {"title": "Yesterday", "artist": "The Beatles"}, "lines": []}'
        )
        mock_result.model_dump_json.return_value = json_output
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "The Beatles - Yesterday"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert json_output in captured.out
        assert captured.err == ""  # No errors on stderr


class TestVerboseLogging:
    """Test verbose flag."""

    def test_verbose_flag_sets_debug_logging(self, capsys):
        """--verbose should set logging level to DEBUG."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "--verbose", "Yesterday"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0

    def test_short_verbose_flag(self, capsys):
        """Short -v flag should work."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "-v", "Yesterday"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0


class TestWhitespaceHandling:
    """Test whitespace handling in queries."""

    def test_leading_trailing_whitespace_stripped(self, capsys):
        """Leading/trailing whitespace should be stripped."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "  Yesterday  "]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.title == "Yesterday"


class TestLanguageFlag:
    """Test --language flag."""

    def test_language_flag(self, capsys):
        """--language flag is threaded to SyncRequest."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "--language", "hi", "test query"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.language == "hi"

    def test_short_language_flag(self, capsys):
        """Short -l flag should work."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "-l", "en", "test query"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.language == "en"

    def test_no_language_flag_defaults_to_none(self, capsys):
        """No --language flag means language=None."""
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = '{"lines": []}'
        mock_pipeline.sync.return_value = mock_result

        with patch("sys.argv", ["syncer", "test query"]):
            with patch("syncer.__main__.SyncPipeline", return_value=mock_pipeline):
                result = main()

        assert result == 0
        call_args = mock_pipeline.sync.call_args[0][0]
        assert call_args.language is None
