"""CLI entry point: python -m syncer <url_or_query> [--verbose]"""
import argparse
import logging
import sys

from syncer.config import Settings
from syncer.models import SyncRequest
from syncer.pipeline import SyncPipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m syncer",
        description="Sync lyrics with timestamps for a song",
    )
    parser.add_argument(
        "query",
        help="YouTube URL, Spotify URL, or title/artist search query",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    # Configure logging to stderr (keep stdout clean for JSON)
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    
    query = args.query.strip()
    if not query:
        print("Error: query cannot be empty", file=sys.stderr)
        return 1
    
    # Detect input type
    if "youtube.com" in query or "youtu.be" in query:
        request = SyncRequest(url=query)
    elif "spotify.com" in query or query.startswith("spotify:"):
        request = SyncRequest(url=query)
    else:
        # Title/artist query — try to split on " - " for "Artist - Title" format
        if " - " in query:
            parts = query.split(" - ", 1)
            request = SyncRequest(title=parts[1].strip(), artist=parts[0].strip())
        else:
            request = SyncRequest(title=query)
    
    try:
        settings = Settings()
        pipeline = SyncPipeline(settings)
        result = pipeline.sync(request)
        print(result.model_dump_json(indent=2))
        return 0
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
