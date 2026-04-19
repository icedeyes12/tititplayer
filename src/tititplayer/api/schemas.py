"""
Pydantic models for API request/response schemas.

These models define the strict contract between the server and clients.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# Enums


class PlaybackStatus(StrEnum):
    """Playback status values."""

    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


class RepeatMode(StrEnum):
    """Repeat mode values."""

    OFF = "off"
    SINGLE = "single"
    ALL = "all"


class TrackSource(StrEnum):
    """Track source types."""

    LOCAL = "local"
    STREAM = "stream"
    YOUTUBE = "youtube"
    YTMUSIC = "ytmusic"


# Base Models


class TrackBase(BaseModel):
    """Base track fields."""

    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float = Field(default=0.0, ge=0.0)
    source: TrackSource = TrackSource.LOCAL


class TrackCreate(TrackBase):
    """Schema for creating a track."""

    path: str


class URLImportRequest(BaseModel):
    """Schema for importing a track by URL."""

    url: str = Field(..., description="YouTube, YT Music, or other streaming URL")
    add_to_queue: bool = Field(default=True, description="Add to queue after import")


class M3UImportRequest(BaseModel):
    """Schema for importing an M3U playlist."""

    path: str = Field(..., description="Path to .m3u or .m3u8 file")
    create_playlist: bool = Field(
        default=True, description="Create a playlist from imported tracks"
    )
    playlist_name: str | None = Field(
        default=None, description="Playlist name (uses filename if None)"
    )
    add_to_queue: bool = Field(
        default=False, description="Add imported tracks to queue"
    )


class TrackUpdate(BaseModel):
    """Schema for updating a track."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None


class TrackResponse(TrackBase):
    """Schema for track responses."""

    id: int
    path: str
    kind: str = "unknown"
    created_at: int

    model_config = {"from_attributes": True}


# Import responses (must be after TrackResponse)


class URLImportResponse(BaseModel):
    """Schema for URL import response."""

    track: TrackResponse
    metadata: dict[str, str | float | None] = Field(
        default_factory=dict, description="Extracted metadata"
    )


class M3UImportResponse(BaseModel):
    """Schema for M3U import response."""

    imported: int = Field(..., description="Number of tracks imported")
    failed: int = Field(default=0, description="Number of failed imports")
    playlist_id: int | None = Field(default=None, description="Created playlist ID")
    tracks: list[TrackResponse] = Field(default_factory=list)


# Playback


class PlaybackStateResponse(BaseModel):
    """Schema for playback state response."""

    status: PlaybackStatus
    track: TrackResponse | None = None
    position: float = Field(default=0.0, ge=0.0, description="Current position in seconds")
    duration: float = Field(default=0.0, ge=0.0, description="Track duration in seconds")
    volume: int = Field(default=100, ge=0, le=100)
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    mute: bool = False
    repeat_mode: RepeatMode = RepeatMode.OFF
    shuffle: bool = False


class PlayRequest(BaseModel):
    """Schema for play request."""

    track_id: int | None = Field(default=None, description="Track ID to play, or None to resume")
    position: float | None = Field(default=None, ge=0.0, description="Start position in seconds")


class SeekRequest(BaseModel):
    """Schema for seek request."""

    position: float = Field(..., ge=0.0, description="Target position in seconds")


class VolumeRequest(BaseModel):
    """Schema for volume request."""

    volume: int = Field(..., ge=0, le=100, description="Volume level 0-100")


class SpeedRequest(BaseModel):
    """Schema for speed request."""

    speed: float = Field(..., ge=0.25, le=4.0, description="Playback speed multiplier")


class RepeatRequest(BaseModel):
    """Schema for repeat mode request."""

    mode: RepeatMode


# Queue


class QueueItemResponse(BaseModel):
    """Schema for queue item response."""

    id: int
    track_id: int
    position: int
    track: TrackResponse | None = None

    model_config = {"from_attributes": True}


class QueueStateResponse(BaseModel):
    """Schema for queue state response."""

    items: list[QueueItemResponse]
    current_position: int = -1
    current_track_id: int | None = None
    length: int = 0
    repeat_mode: RepeatMode = RepeatMode.OFF
    shuffle: bool = False


class AddToQueueRequest(BaseModel):
    """Schema for adding tracks to queue."""

    track_ids: list[int] = Field(
        ..., min_length=1, description="List of track IDs to add"
    )
    position: int | None = Field(
        default=None, ge=0, description="Position to insert at (default: end)"
    )


class MoveQueueItemRequest(BaseModel):
    """Schema for moving a queue item."""

    old_position: int = Field(..., ge=0, description="Current position of item")
    new_position: int = Field(..., ge=0, description="New position for item")


class QueueNavigationRequest(BaseModel):
    """Schema for queue navigation (goto)."""

    position: int = Field(..., ge=0, description="Position to go to")


# Playlists


class PlaylistCreate(BaseModel):
    """Schema for creating a playlist."""

    name: str = Field(..., min_length=1, max_length=255, description="Playlist name")
    description: str = Field(default="", max_length=1000, description="Playlist description")


class PlaylistUpdate(BaseModel):
    """Schema for updating a playlist."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class PlaylistAddTracks(BaseModel):
    """Schema for adding tracks to a playlist."""

    track_ids: list[int] = Field(..., min_length=1, description="List of track IDs to add")


class PlaylistResponse(BaseModel):
    """Schema for playlist response."""

    id: int
    name: str
    description: str
    track_count: int = 0
    created_at: int
    updated_at: int
    tracks: list[TrackResponse] = []

    model_config = {"from_attributes": True}


# Status


class ProgressResponse(BaseModel):
    """Schema for progress endpoint (lightweight polling)."""

    status: PlaybackStatus
    track_id: int | None = None
    position: float = 0.0
    duration: float = 0.0
    volume: int = 100
    speed: float = 1.0


class ServerStatusResponse(BaseModel):
    """Schema for server status."""

    status: str = "ok"
    mpv_connected: bool = False
    database_connected: bool = False
    queue_length: int = 0
    uptime_seconds: float = 0.0


# History


class HistoryEntryResponse(BaseModel):
    """Schema for history entry response."""

    id: int
    track_id: int | None
    title: str
    artist: str
    source: str
    played_at: int
    position: int
    completed: bool

    model_config = {"from_attributes": True}


class HistoryListResponse(BaseModel):
    """Schema for history list response."""

    entries: list[HistoryEntryResponse]
    total: int
    limit: int
    offset: int


# Search


class SearchQuery(BaseModel):
    """Schema for search query."""

    q: str = Field(default="", min_length=1, description="Search query")
    limit: int = Field(default=20, ge=1, le=100, description="Max results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class TrackSearchResponse(BaseModel):
    """Schema for track search results."""

    tracks: list[TrackResponse]
    total: int
    limit: int
    offset: int


# Error Responses


class ErrorResponse(BaseModel):
    """Schema for error responses."""

    error: str
    detail: str | None = None
    code: str | None = None


class NotFoundError(ErrorResponse):
    """Schema for not found errors."""

    error: str = "not_found"
    code: str = "NOT_FOUND"


class ValidationError(ErrorResponse):
    """Schema for validation errors."""

    error: str = "validation_error"
    code: str = "VALIDATION_ERROR"


class ServerError(ErrorResponse):
    """Schema for server errors."""

    error: str = "server_error"
    code: str = "SERVER_ERROR"
