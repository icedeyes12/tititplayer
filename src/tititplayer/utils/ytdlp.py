"""
YouTube/Streaming metadata extraction via yt-dlp.

Extracts track metadata without downloading the file.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from typing import Any


@dataclass
class StreamMetadata:
    """Metadata extracted from a streaming URL."""

    url: str
    title: str
    artist: str | None = None
    album: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    uploader: str | None = None
    channel_url: str | None = None
    date: str | None = None
    track_id: str | None = None

    @classmethod
    def from_ytdlp(cls, url: str, data: dict[str, Any]) -> StreamMetadata:
        """Create from yt-dlp JSON output."""
        return cls(
            url=url,
            title=data.get("title", "Unknown"),
            artist=data.get("artist") or data.get("uploader") or data.get("channel"),
            album=data.get("album"),
            duration=data.get("duration"),
            thumbnail=data.get("thumbnail"),
            uploader=data.get("uploader"),
            channel_url=data.get("channel_url"),
            date=data.get("upload_date") or data.get("release_date"),
            track_id=data.get("id"),
        )


def is_ytdlp_available() -> bool:
    """Check if yt-dlp is installed."""
    return shutil.which("yt-dlp") is not None


async def extract_metadata(url: str, timeout: int = 30) -> StreamMetadata | None:
    """
    Extract metadata from a URL using yt-dlp.

    Args:
        url: YouTube, YT Music, or other streaming URL
        timeout: Timeout in seconds

    Returns:
        StreamMetadata if successful, None if failed
    """
    if not is_ytdlp_available():
        raise RuntimeError("yt-dlp is not installed. Install with: pip install yt-dlp")

    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-download",
        "--no-playlist",
        "--flat-playlist",
        url,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"yt-dlp failed: {error_msg}")

        data = json.loads(stdout.decode())
        return StreamMetadata.from_ytdlp(url, data)

    except TimeoutError:
        raise RuntimeError(f"yt-dlp timeout after {timeout}s") from None
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse yt-dlp output: {e}") from None


async def extract_playlist_metadata(
    playlist_url: str,
    timeout: int = 120,
    max_entries: int = 100,
) -> list[StreamMetadata]:
    """
    Extract metadata for all entries in a playlist.

    Args:
        playlist_url: Playlist URL
        timeout: Timeout in seconds
        max_entries: Maximum number of entries to extract

    Returns:
        List of StreamMetadata
    """
    if not is_ytdlp_available():
        raise RuntimeError("yt-dlp is not installed")

    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-download",
        "--flat-playlist",
        f"--playlist-end={max_entries}",
        playlist_url,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"yt-dlp failed: {error_msg}")

        results: list[StreamMetadata] = []
        # Each line is a separate JSON object
        for line in stdout.decode().strip().split("\n"):
            if line:
                try:
                    data = json.loads(line)
                    # Build the actual URL from the entry
                    entry_url = data.get("url") or data.get("webpage_url") or playlist_url
                    results.append(StreamMetadata.from_ytdlp(entry_url, data))
                except json.JSONDecodeError:
                    continue

        return results

    except TimeoutError:
        raise RuntimeError(f"yt-dlp timeout after {timeout}s") from None


async def get_stream_url(url: str, timeout: int = 30) -> str | None:
    """
    Get the direct stream URL from a video page.

    Useful for players that don't support yt-dlp directly.

    Args:
        url: Video URL
        timeout: Timeout in seconds

    Returns:
        Direct stream URL or None
    """
    if not is_ytdlp_available():
        return None

    cmd = [
        "yt-dlp",
        "--get-url",
        "--format=bestaudio/best",
        url,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        if process.returncode == 0:
            return stdout.decode().strip()
        return None

    except Exception:
        return None


# Test
if __name__ == "__main__":
    import sys

    async def test():
        url = sys.argv[1] if len(sys.argv) > 1 else "https://music.youtube.com/watch?v=V2VtQbYCg24"
        print(f"Extracting metadata from: {url}")

        metadata = await extract_metadata(url)
        if metadata:
            print(f"Title: {metadata.title}")
            print(f"Artist: {metadata.artist}")
            print(f"Album: {metadata.album}")
            print(f"Duration: {metadata.duration}s")
            print(f"Date: {metadata.date}")

    asyncio.run(test())
