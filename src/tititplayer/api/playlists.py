"""
API router for playlists endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from tititplayer.api.schemas import (
    ErrorResponse,
    PlaylistAddTracks,
    PlaylistCreate,
    PlaylistResponse,
    PlaylistUpdate,
    TrackResponse,
)
from tititplayer.db.manager import Database

router = APIRouter(prefix="/playlists", tags=["playlists"])


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


def build_playlist_response(playlist) -> PlaylistResponse:
    """Build a playlist response from a Playlist object."""
    tracks = [
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
        for t in playlist.tracks
    ]

    return PlaylistResponse(
        id=playlist.id,
        name=playlist.name,
        description=playlist.description,
        track_count=len(playlist.tracks),
        created_at=playlist.created_at,
        updated_at=playlist.updated_at,
        tracks=tracks,
    )


@router.get(
    "",
    response_model=list[PlaylistResponse],
    summary="Get all playlists",
    description="Get all playlists in the library.",
)
async def get_playlists() -> list[PlaylistResponse]:
    """Get all playlists."""
    db = get_db()
    playlists = await db.get_all_playlists()
    return [build_playlist_response(p) for p in playlists]


@router.post(
    "",
    response_model=PlaylistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create playlist",
    description="Create a new playlist.",
)
async def create_playlist(request: PlaylistCreate) -> PlaylistResponse:
    """Create a new playlist."""
    db = get_db()

    playlist_id = await db.create_playlist(
        name=request.name,
        description=request.description,
    )

    playlist = await db.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve created playlist",
        )

    return build_playlist_response(playlist)


@router.get(
    "/{playlist_id}",
    response_model=PlaylistResponse,
    summary="Get playlist",
    description="Get a playlist by ID.",
    responses={
        404: {"model": ErrorResponse, "description": "Playlist not found"},
    },
)
async def get_playlist(playlist_id: int) -> PlaylistResponse:
    """Get a playlist by ID."""
    db = get_db()

    playlist = await db.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist {playlist_id} not found",
        )

    return build_playlist_response(playlist)


@router.patch(
    "/{playlist_id}",
    response_model=PlaylistResponse,
    summary="Update playlist",
    description="Update playlist metadata.",
    responses={
        404: {"model": ErrorResponse, "description": "Playlist not found"},
    },
)
async def update_playlist(
    playlist_id: int,
    request: PlaylistUpdate,
) -> PlaylistResponse:
    """Update playlist metadata."""
    db = get_db()

    playlist = await db.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist {playlist_id} not found",
        )

    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description

    if updates:
        await db.update_playlist(
            playlist_id,
            name=updates.get("name"),
            description=updates.get("description"),
        )

    playlist = await db.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated playlist",
        )

    return build_playlist_response(playlist)


@router.delete(
    "/{playlist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete playlist",
    description="Delete a playlist.",
    responses={
        404: {"model": ErrorResponse, "description": "Playlist not found"},
    },
)
async def delete_playlist(playlist_id: int) -> None:
    """Delete a playlist."""
    db = get_db()

    playlist = await db.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist {playlist_id} not found",
        )

    await db.delete_playlist(playlist_id)


@router.post(
    "/{playlist_id}/tracks",
    response_model=PlaylistResponse,
    summary="Add tracks to playlist",
    description="Add tracks to a playlist.",
    responses={
        404: {"model": ErrorResponse, "description": "Playlist or track not found"},
    },
)
async def add_tracks_to_playlist(
    playlist_id: int,
    request: PlaylistAddTracks,
) -> PlaylistResponse:
    """Add tracks to a playlist."""
    db = get_db()

    playlist = await db.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist {playlist_id} not found",
        )

    # Validate tracks exist
    for track_id in request.track_ids:
        track = await db.get_track(track_id)
        if not track:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Track {track_id} not found",
            )

    # Add tracks
    await db.add_tracks_to_playlist(playlist_id, request.track_ids)

    playlist = await db.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated playlist",
        )

    return build_playlist_response(playlist)


@router.delete(
    "/{playlist_id}/tracks/{track_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove track from playlist",
    description="Remove a track from a playlist.",
    responses={
        404: {"model": ErrorResponse, "description": "Playlist or track not found"},
    },
)
async def remove_track_from_playlist(
    playlist_id: int,
    track_id: int,
) -> None:
    """Remove a track from a playlist."""
    db = get_db()

    playlist = await db.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist {playlist_id} not found",
        )

    await db.remove_track_from_playlist(playlist_id, track_id)


@router.post(
    "/{playlist_id}/play",
    response_model=PlaylistResponse,
    summary="Play playlist",
    description="Load all tracks from a playlist into the queue and start playing.",
    responses={
        404: {"model": ErrorResponse, "description": "Playlist not found"},
    },
)
async def play_playlist(playlist_id: int) -> PlaylistResponse:
    """Play a playlist."""
    from tititplayer.api.queue import get_queue_engine

    db = get_db()
    qe = get_queue_engine()

    playlist = await db.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist {playlist_id} not found",
        )

    if not playlist.tracks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Playlist is empty",
        )

    # Clear queue and add all tracks
    await qe.clear()
    track_ids = [t.id for t in playlist.tracks]
    await qe.add_tracks(track_ids)

    # Start playing first track
    await qe.goto(0)

    return build_playlist_response(playlist)
