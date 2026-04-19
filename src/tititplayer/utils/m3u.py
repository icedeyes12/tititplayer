"""
M3U Playlist parser utility.

Supports both m3u and m3u8 (extended) formats.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class M3UEntry:
    """A single entry in an M3U playlist."""

    path: str
    title: str | None = None
    duration: float | None = None
    artist: str | None = None

    @property
    def is_url(self) -> bool:
        """Check if the path is a URL."""
        try:
            result = urlparse(self.path)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    @property
    def is_youtube(self) -> bool:
        """Check if this is a YouTube URL."""
        youtube_domains = ["youtube.com", "youtu.be", "music.youtube.com"]
        try:
            result = urlparse(self.path)
            return any(domain in result.netloc for domain in youtube_domains)
        except Exception:
            return False


def parse_m3u(file_path: Path) -> list[M3UEntry]:
    """
    Parse an M3U or M3U8 playlist file.

    Args:
        file_path: Path to the .m3u or .m3u8 file

    Returns:
        List of M3UEntry objects
    """
    entries: list[M3UEntry] = []

    if not file_path.exists():
        return entries

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.strip().split("\n")

    current_title: str | None = None
    current_duration: float | None = None
    current_artist: str | None = None

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # Skip M3U header
        if line.startswith("#EXTM3U"):
            continue

        # Extended M3U info line
        if line.startswith("#EXTINF:"):
            # Parse: #EXTINF:duration,title or #EXTINF:duration,artist - title
            current_title = None
            current_duration = None
            current_artist = None

            try:
                # Remove #EXTINF: prefix
                info = line[8:]

                # Split duration and title
                if "," in info:
                    duration_str, title_part = info.split(",", 1)

                    # Parse duration (can be negative for live streams)
                    try:
                        current_duration = abs(float(duration_str))
                    except ValueError:
                        current_duration = None

                    # Parse title (may contain "artist - title" format)
                    if " - " in title_part:
                        parts = title_part.split(" - ", 1)
                        current_artist = parts[0].strip()
                        current_title = parts[1].strip()
                    else:
                        current_title = title_part.strip()

            except Exception:
                pass

        # Comment lines (skip other comments)
        elif line.startswith("#"):
            continue

        # Path/URL line
        else:
            # Resolve relative paths
            if not urlparse(line).scheme:
                # It's a relative path
                if not Path(line).is_absolute():
                    line = str((file_path.parent / line).resolve())

            entries.append(M3UEntry(
                path=line,
                title=current_title,
                duration=current_duration,
                artist=current_artist,
            ))

            # Reset for next entry
            current_title = None
            current_duration = None
            current_artist = None

    return entries


def export_m3u(entries: list[M3UEntry], output_path: Path, extended: bool = True) -> None:
    """
    Export entries to an M3U file.

    Args:
        entries: List of entries to export
        output_path: Output file path
        extended: If True, write extended M3U (m3u8) format
    """
    lines: list[str] = []

    if extended:
        lines.append("#EXTM3U")

    for entry in entries:
        if extended and (entry.title or entry.duration):
            duration = int(entry.duration) if entry.duration else -1
            title = f"{entry.artist} - {entry.title}" if entry.artist else (entry.title or "")
            lines.append(f"#EXTINF:{duration},{title}")
        lines.append(entry.path)

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Example usage and test
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m tititplayer.utils.m3u <playlist.m3u>")
        sys.exit(1)

    playlist_path = Path(sys.argv[1])
    entries = parse_m3u(playlist_path)

    print(f"Found {len(entries)} entries in {playlist_path}:")
    for i, entry in enumerate(entries, 1):
        print(f"{i}. {entry.title or 'Unknown'}")
        print(f"   Path: {entry.path}")
        print(f"   Duration: {entry.duration or 'N/A'}s")
        print(f"   Is URL: {entry.is_url}")
        print(f"   Is YouTube: {entry.is_youtube}")
        print()
