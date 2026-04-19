"""
API router for queue endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from tititplayer.api.schemas import (
    AddToQueueRequest,
    ErrorResponse,
    MoveQueueItemRequest,
    QueueItemResponse,
    QueueNavigationRequest,
    QueueStateResponse,
    RepeatMode,
)
from tititplayer.core.queue import QueueEngine
from tititplayer.core.state import RepeatMode as CoreRepeatMode
from tititplayer.core.state import StateManager
from tititplayer.db.manager import Database

router = APIRouter(prefix="/queue", tags=["queue"])


# Global references (set by app lifespan)
_state_manager: StateManager | None = None
_queue_engine: QueueEngine | None = None
_db: Database | None = None


def set_dependencies(
    state_manager: StateManager,
    queue_engine: QueueEngine,
    db: Database,
) -> None:
    """Set global dependencies. Called during app startup."""
    global _state_manager, _queue_engine, _db
    _state_manager = state_manager
    _queue_engine = queue_engine
    _db = db


def get_state_manager() -> StateManager:
    if _state_manager is None:
        raise RuntimeError("State manager not initialized")
    return _state_manager


def get_queue_engine() -> QueueEngine:
    if _queue_engine is None:
        raise RuntimeError("Queue engine not initialized")
    return _queue_engine


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


async def build_queue_item_response(item) -> dict:
    """Build a queue item response with track data."""
    db = get_db()
    track = await db.get_track(item.track_id)

    track_data = None
    if track:
        track_data = {
            "id": track.id,
            "path": track.path,
            "title": track.title,
            "artist": track.artist,
            "album": track.album,
            "duration": track.duration,
            "source": track.source,
            "kind": track.kind,
            "created_at": track.created_at,
        }

    return {
        "id": item.id,
        "track_id": item.track_id,
        "position": item.position,
        "track": track_data,
    }


@router.get(
    "",
    response_model=QueueStateResponse,
    summary="Get queue state",
    description="Returns the current queue state including all items and current position.",
)
async def get_queue() -> QueueStateResponse:
    """Get current queue state."""
    qe = get_queue_engine()
    state = qe.state

    # Build items
    items = []
    for item in state.items:
        items.append(await build_queue_item_response(item))

    # Map repeat mode
    repeat_map = {
        CoreRepeatMode.OFF: RepeatMode.OFF,
        CoreRepeatMode.SINGLE: RepeatMode.SINGLE,
        CoreRepeatMode.ALL: RepeatMode.ALL,
    }

    return QueueStateResponse(
        items=items,
        current_position=state.current_position,
        current_track_id=state.current_track_id,
        length=len(items),
        repeat_mode=repeat_map.get(state.repeat_mode, RepeatMode.OFF),
        shuffle=state.shuffle_enabled,
    )


@router.post(
    "/add",
    response_model=QueueStateResponse,
    summary="Add tracks to queue",
    description="Add one or more tracks to the queue.",
    responses={
        404: {"model": ErrorResponse, "description": "Track not found"},
    },
)
async def add_to_queue(request: AddToQueueRequest) -> QueueStateResponse:
    """Add tracks to queue."""
    qe = get_queue_engine()
    db = get_db()

    # Validate all track IDs exist
    for track_id in request.track_ids:
        track = await db.get_track(track_id)
        if not track:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Track {track_id} not found",
            )

    # Add to queue
    if len(request.track_ids) == 1:
        await qe.add_track(request.track_ids[0], request.position)
    else:
        await qe.add_tracks(request.track_ids, request.position)

    return await get_queue()


@router.post(
    "/remove/{position}",
    response_model=QueueStateResponse,
    summary="Remove track from queue",
    description="Remove a track from the queue by position.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid position"},
    },
)
async def remove_from_queue(position: int) -> QueueStateResponse:
    """Remove track from queue by position."""
    qe = get_queue_engine()

    track_id = await qe.remove_track(position)
    if track_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid position: {position}",
        )

    return await get_queue()


@router.post(
    "/move",
    response_model=QueueStateResponse,
    summary="Move track in queue",
    description="Move a track to a different position in the queue.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid position"},
    },
)
async def move_in_queue(request: MoveQueueItemRequest) -> QueueStateResponse:
    """Move track within queue."""
    qe = get_queue_engine()

    success = await qe.move_track(request.old_position, request.new_position)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid position(s)",
        )

    return await get_queue()


@router.post(
    "/clear",
    response_model=QueueStateResponse,
    summary="Clear queue",
    description="Clear all tracks from the queue.",
)
async def clear_queue() -> QueueStateResponse:
    """Clear the entire queue."""
    qe = get_queue_engine()
    await qe.clear()
    return await get_queue()


@router.post(
    "/goto",
    response_model=QueueStateResponse,
    summary="Go to position in queue",
    description="Go to a specific position in the queue and play that track.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid position"},
    },
)
async def goto_position(request: QueueNavigationRequest) -> QueueStateResponse:
    """Go to a specific position in queue."""
    qe = get_queue_engine()

    track = await qe.goto(request.position)
    if not track:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid position: {request.position}",
        )

    return await get_queue()


@router.post(
    "/shuffle",
    response_model=QueueStateResponse,
    summary="Toggle shuffle",
    description="Toggle shuffle mode on/off.",
)
async def toggle_shuffle() -> QueueStateResponse:
    """Toggle shuffle mode."""
    qe = get_queue_engine()
    await qe.toggle_shuffle()
    return await get_queue()


@router.post(
    "/repeat",
    response_model=QueueStateResponse,
    summary="Toggle repeat mode",
    description="Cycle through repeat modes (off -> single -> all -> off).",
)
async def toggle_repeat() -> QueueStateResponse:
    """Toggle repeat mode."""
    qe = get_queue_engine()
    await qe.toggle_repeat()
    return await get_queue()


@router.get(
    "/{position}",
    response_model=QueueItemResponse,
    summary="Get queue item",
    description="Get a specific queue item by position.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid position"},
    },
)
async def get_queue_item(position: int) -> QueueItemResponse:
    """Get queue item at position."""
    qe = get_queue_engine()

    item = qe.get_track_at(position)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid position: {position}",
        )

    return QueueItemResponse(**await build_queue_item_response(item))
