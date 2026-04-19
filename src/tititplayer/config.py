"""
Configuration constants for tititplayer.
"""

from pathlib import Path

# Database
DATABASE_PATH: Path = Path.home() / ".local" / "share" / "tititplayer" / "titit.db"
DATABASE_SCHEMA_PATH: Path = Path(__file__).parent / "db" / "schema.sql"

# MPV
MPV_SOCKET_PATH: Path = Path.home() / ".mpvsocket"
MPV_BINARY: str = "mpv"

# API Server
API_HOST: str = "127.0.0.1"
API_PORT: int = 8765
API_BASE_URL: str = f"http://{API_HOST}:{API_PORT}"

# Playback defaults
DEFAULT_VOLUME: int = 100
DEFAULT_REPEAT_MODE: str = "none"
DEFAULT_SHUFFLE_MODE: bool = False

# Supported audio formats
SUPPORTED_EXTENSIONS: set[str] = {
    ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".wma", ".ape"
}
