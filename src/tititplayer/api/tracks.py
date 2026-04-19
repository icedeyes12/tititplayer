"""
API router for tracks endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from tititplayer.api.schemas import (
    ErrorResponse,
    M3UImportRequest,
    M3UImportResponse,
    TrackCreate,
    TrackResponse,
    TrackSearchResponse,
    TrackSource,
    TrackUpdate,
    URLImportRequest,
    URLImportResponse,
)
from tititplayer.db.manager import Database

router = APIRouter(prefix="/tracks", tags=["tracks"])


# Global references (set by app lifespan)
_db: Database | None = None


def set_dependencies(db: Database) -> None:
    """Set global dependencies. Called during app startup."""
    global _db
    _db = db


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


@router.get(
    "",
    response_model=TrackSearchResponse,
    summary="Search tracks",
    description="Search tracks by title, artist, or album.",
)
async def search_tracks(
    q: str = Query(default="", description="Search query"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> TrackSearchResponse:
    """Search tracks."""
    db = get_db()

    if not q:
        # Return all tracks (paginated)
        tracks = await db.get_all_tracks()
        total = len(tracks)
        tracks = tracks[offset : offset + limit]
    else:
        tracks = await db.search_tracks(q, limit=limit, offset=offset)
        total = len(tracks)  # Approximate

    return TrackSearchResponse(
        tracks=[
            TrackResponse(
                id=t.id,
                path=t.path,
                title=t.title,
                artist=t.artist,
                album=t.album,
                duration=t.duration,
                source=t.source,
                kind=t.kind,
                created_at=t.created_at,
            )
            for t in tracks
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=TrackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add track",
    description="Add a new track to the library.",
)
async def add_track(request: TrackCreate) -> TrackResponse:
    """Add a new track."""
    db = get_db()

    track_id = await db.add_track(
        path=request.path,
        title=request.title,
        artist=request.artist,
        album=request.album,
        duration=request.duration,
        source=request.source,
    )

    track = await db.get_track(track_id)
    if not track:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve created track",
        )

    return TrackResponse(
        id=track.id,
        path=track.path,
        title=track.title,
        artist=track.artist,
        album=track.album,
        duration=track.duration,
        source=track.source,
        kind=track.kind,
        created_at=track.created_at,
    )


@router.get(
    "/{track_id}",
    response_model=TrackResponse,
    summary="Get track",
    description="Get a track by ID.",
    responses={
        404: {"model": ErrorResponse, "description": "Track not found"},
    },
)
async def get_track(track_id: int) -> TrackResponse:
    """Get a track by ID."""
    db = get_db()

    track = await db.get_track(track_id)
    if not track:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track {track_id} not found",
        )

    return TrackResponse(
        id=track.id,
        path=track.path,
        title=track.title,
        artist=track.artist,
        album=track.album,
        duration=track.duration,
        source=track.source,
        kind=track.kind,
        created_at=track.created_at,
    )


@router.patch(
    "/{track_id}",
    response_model=TrackResponse,
    summary="Update track",
    description="Update track metadata.",
    responses={
        404: {"model": ErrorResponse, "description": "Track not found"},
    },
)
async def update_track(track_id: int, request: TrackUpdate) -> TrackResponse:
    """Update track metadata."""
    db = get_db()

    track = await db.get_track(track_id)
    if not track:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track {track_id} not found",
        )

    # Update only provided fields
    updates = {}
    if request.title is not None:
        updates["title"] = request.title
    if request.artist is not None:
        updates["artist"] = request.artist
    if request.album is not None:
        updates["album"] = request.album

    if updates:
        # Would need to add an update_track method to Database
        pass

    return TrackResponse(
        id=track.id,
        path=track.path,
        title=updates.get("title", track.title),
        artist=updates.get("artist", track.artist),
        album=updates.get("album", track.album),
        duration=track.duration,
        source=track.source,
        kind=track.kind,
        created_at=track.created_at,
    )


@router.delete(
    "/{track_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete track",
    description="Delete a track from the library.",
    responses={
        404: {"model": ErrorResponse, "description": "Track not found"},
    },
)
async def delete_track(track_id: int) -> None:
    """Delete a track."""
    db = get_db()

    track = await db.get_track(track_id)
    if not track:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track {track_id} not found",
        )

    await db.delete_track(track_id)


@router.post(
    "/import/url",
    response_model=URLImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import track from URL",
    description="Import a track from YouTube, YT Music, or other streaming URL.",
)
async def import_from_url(request: URLImportRequest) -> URLImportResponse:
    """Import a track from a streaming URL using yt-dlp."""
    from tititplayer.utils.ytdlp import extract_metadata, is_ytdlp_available

    if not is_ytdlp_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="yt-dlp is not installed. Install with: pip install yt-dlp",
        )

    db = get_db()

    try:
        # Extract metadata from URL
        metadata = await extract_metadata(request.url)
        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to extract metadata from URL",
            )

        # Determine source type
        url_lower = request.url.lower()
        if "music.youtube.com" in url_lower:
            source = TrackSource.YTMUSIC
        elif "youtube.com" in url_lower or "youtu.be" in url_lower:
            source = TrackSource.YOUTUBE
        else:
            source = TrackSource.STREAM

        # Add track to database
        track_id = await db.add_track(
            path=request.url,
            title=metadata.title,
            artist=metadata.artist,
            album=metadata.album,
            duration=metadata.duration or 0.0,
            source=source,
        )

        track = await db.get_track(track_id)
        if not track:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve imported track",
            )

        # TODO: Add to queue if request.add_to_queue

        return URLImportResponse(
            track=TrackResponse(
                id=track.id,
                path=track.path,
                title=track.title,
                artist=track.artist,
                album=track.album,
                duration=track.duration,
                source=track.source,
                kind=track.kind,
                created_at=track.created_at,
            ),
            metadata={
                "thumbnail": metadata.thumbnail,
                "uploader": metadata.uploader,
                "date": metadata.date,
                "track_id": metadata.track_id,
            },
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from None


@router.post(
    "/import/m3u",
    response_model=M3UImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import tracks from M3U playlist",
    description="Import tracks from an M3U or M3U8 playlist file.",
)
async def import_from_m3u(request: M3UImportRequest) -> M3UImportResponse:
    """Import tracks from an M3U playlist file."""
    from pathlib import Path

    from tititplayer.utils.m3u import parse_m3u

    db = get_db()

    m3u_path = Path(request.path).expanduser()
    if not m3u_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"M3U file not found: {request.path}",
        )

    entries = parse_m3u(m3u_path)
    if not entries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tracks found in M3U file",
        )

    imported_tracks: list[TrackResponse] = []
    failed = 0

    for entry in entries:
        try:
            # Determine source type
            if entry.is_youtube:
                source = TrackSource.YOUTUBE
            elif entry.is_url:
                source = TrackSource.STREAM
            else:
                source = TrackSource.LOCAL

            track_id = await db.add_track(
                path=entry.path,
                title=entry.title or Path(entry.path).stem,
                artist=entry.artist,
                duration=entry.duration or 0.0,
                source=source,
            )

            track = await db.get_track(track_id)
            if track:
                imported_tracks.append(
                    TrackResponse(
                        id=track.id,
                        path=track.path,
                        title=track.title,
                        artist=track.artist,
                        album=track.album,
                        duration=track.duration,
                        source=track.source,
                        kind=track.kind,
                        created_at=track.created_at,
                    )
                )
        except Exception:
            failed += 1

    playlist_id = None
    if request.create_playlist and imported_tracks:
        # Create playlist
        playlist_name = request.playlist_name or m3u_path.stem
        playlist_id = await db.create_playlist(
            name=playlist_name,
            description=f"Imported from {m3u_path.name}",
        )

        # Add tracks to playlist
        for track in imported_tracks:
            await db.add_track_to_playlist(playlist_id, track.id)

    # TODO: Add to queue if request.add_to_queue

    return M3UImportResponse(
        imported=len(imported_tracks),
        failed=failed,
        playlist_id=playlist_id,
        tracks=imported_tracks,
    )


@router.get(
    "/path/{path:path}",
    response_model=TrackResponse,
    summary="Get track by path",
    description="Get a track by file path.",
    responses={
        404: {"model": ErrorResponse, "description": "Track not found"},
    },
)
async def get_track_by_path(path: str) -> TrackResponse:
    """Get a track by file path."""
    db = get_db()

    track = await db.get_track_by_path(path)
    if not track:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track not found at path: {path}",
        )

    return TrackResponse(
        id=track.id,
        path=track.path,
        title=track.title,
        artist=track.artist,
        album=track.album,
        duration=track.duration,
        source=track.source,
        kind=track.kind,
        created_at=track.created_at,
    )
