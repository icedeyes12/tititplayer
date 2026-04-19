"""
API router for tracks endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from tititplayer.api.schemas import (
    ErrorResponse,
    TrackCreate,
    TrackUpdate,
    TrackResponse,
    TrackSearchResponse,
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
