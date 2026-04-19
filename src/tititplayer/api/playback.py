"""
API router for playback endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from tititplayer.api.schemas import (
    ErrorResponse,
    PlaybackStateResponse,
    PlaybackStatus,
    PlayRequest,
    RepeatMode,
    RepeatRequest,
    SeekRequest,
    SpeedRequest,
    VolumeRequest,
)
from tititplayer.core.queue import QueueEngine
from tititplayer.core.state import RepeatMode as CoreRepeatMode
from tititplayer.core.state import StateManager
from tititplayer.db.manager import Database

router = APIRouter(prefix="/playback", tags=["playback"])


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


@router.get(
    "",
    response_model=PlaybackStateResponse,
    summary="Get current playback state",
    description="Returns the current playback state including track info, position, volume, etc.",
)
async def get_playback_state() -> PlaybackStateResponse:
    """Get current playback state."""
    sm = get_state_manager()
    qe = get_queue_engine()
    state = sm.state

    # Map repeat mode
    repeat_map = {
        CoreRepeatMode.OFF: RepeatMode.OFF,
        CoreRepeatMode.SINGLE: RepeatMode.SINGLE,
        CoreRepeatMode.ALL: RepeatMode.ALL,
    }

    # Map playback status
    if not state.pause and state.filename:
        pb_status = PlaybackStatus.PLAYING
    elif state.filename:
        pb_status = PlaybackStatus.PAUSED
    else:
        pb_status = PlaybackStatus.STOPPED

    # Build track response
    track_response = None
    if state.current_track:
        t = state.current_track
        track_response = {
            "id": t.id,
            "path": t.path,
            "title": t.title,
            "artist": t.artist,
            "album": t.album,
            "duration": t.duration,
            "source": t.source,
            "kind": t.kind,
            "created_at": t.created_at,
        }

    return PlaybackStateResponse(
        status=pb_status,
        track=track_response,
        position=state.time_pos or 0.0,
        duration=state.duration or 0.0,
        volume=state.volume,
        speed=state.speed,
        mute=state.mute,
        repeat_mode=repeat_map.get(qe.repeat_mode, RepeatMode.OFF),
        shuffle=qe.shuffle_enabled,
    )


@router.post(
    "/play",
    response_model=PlaybackStateResponse,
    summary="Start or resume playback",
    description="Start playing a specific track (by track_id) or resume current track.",
    responses={
        404: {"model": ErrorResponse, "description": "Track not found"},
        500: {"model": ErrorResponse, "description": "MPV not connected"},
    },
)
async def play(request: PlayRequest) -> PlaybackStateResponse:
    """Start or resume playback."""
    sm = get_state_manager()
    qe = get_queue_engine()
    db = get_db()

    # If track_id provided, play that track
    if request.track_id is not None:
        track = await db.get_track(request.track_id)
        if not track:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Track {request.track_id} not found",
            )

        # Add to queue if not already there
        if qe.current_position < 0:
            await qe.add_track(track.id)
            await qe.goto(0)
        else:
            await qe.goto(await qe.add_track(track.id))

        # Set track in state manager
        position = request.position if request.position is not None else 0.0
        await sm.set_track(track, position=position)
    else:
        # Resume current track
        if not sm.state.current_track:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No track loaded. Provide track_id.",
            )
        await sm.resume()

    return await get_playback_state()


@router.post(
    "/pause",
    response_model=PlaybackStateResponse,
    summary="Pause playback",
    description="Pause the currently playing track.",
)
async def pause() -> PlaybackStateResponse:
    """Pause playback."""
    sm = get_state_manager()
    await sm.pause()
    return await get_playback_state()


@router.post(
    "/resume",
    response_model=PlaybackStateResponse,
    summary="Resume playback",
    description="Resume a paused track.",
)
async def resume() -> PlaybackStateResponse:
    """Resume playback."""
    sm = get_state_manager()
    await sm.resume()
    return await get_playback_state()


@router.post(
    "/toggle",
    response_model=PlaybackStateResponse,
    summary="Toggle play/pause",
    description="Toggle between play and pause states.",
)
async def toggle() -> PlaybackStateResponse:
    """Toggle play/pause."""
    sm = get_state_manager()
    await sm.toggle_pause()
    return await get_playback_state()


@router.post(
    "/stop",
    response_model=PlaybackStateResponse,
    summary="Stop playback",
    description="Stop playback and clear current track.",
)
async def stop() -> PlaybackStateResponse:
    """Stop playback."""
    sm = get_state_manager()
    await sm.stop()
    return await get_playback_state()


@router.post(
    "/seek",
    response_model=PlaybackStateResponse,
    summary="Seek to position",
    description="Seek to a specific position in the current track.",
    responses={
        400: {"model": ErrorResponse, "description": "No track playing"},
    },
)
async def seek(request: SeekRequest) -> PlaybackStateResponse:
    """Seek to position."""
    sm = get_state_manager()

    if not sm.state.current_track:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No track loaded",
        )

    await sm.seek(request.position)
    return await get_playback_state()


@router.post(
    "/volume",
    response_model=PlaybackStateResponse,
    summary="Set volume",
    description="Set the playback volume (0-100).",
)
async def set_volume(request: VolumeRequest) -> PlaybackStateResponse:
    """Set volume."""
    sm = get_state_manager()
    await sm.set_volume(request.volume)
    return await get_playback_state()


@router.post(
    "/speed",
    response_model=PlaybackStateResponse,
    summary="Set playback speed",
    description="Set the playback speed multiplier (0.25-4.0).",
)
async def set_speed(request: SpeedRequest) -> PlaybackStateResponse:
    """Set playback speed."""
    sm = get_state_manager()
    await sm.set_speed(request.speed)
    return await get_playback_state()


@router.post(
    "/mute",
    response_model=PlaybackStateResponse,
    summary="Toggle mute",
    description="Toggle mute on/off.",
)
async def toggle_mute() -> PlaybackStateResponse:
    """Toggle mute."""
    sm = get_state_manager()
    await sm.set_mute(not sm.state.mute)
    return await get_playback_state()


@router.post(
    "/repeat",
    response_model=PlaybackStateResponse,
    summary="Set repeat mode",
    description="Set the repeat mode (off, single, all).",
)
async def set_repeat(request: RepeatRequest) -> PlaybackStateResponse:
    """Set repeat mode."""
    qe = get_queue_engine()

    mode_map = {
        RepeatMode.OFF: CoreRepeatMode.OFF,
        RepeatMode.SINGLE: CoreRepeatMode.SINGLE,
        RepeatMode.ALL: CoreRepeatMode.ALL,
    }

    await qe.set_repeat_mode(mode_map[request.mode])
    return await get_playback_state()


@router.post(
    "/next",
    response_model=PlaybackStateResponse,
    summary="Next track",
    description="Skip to the next track in the queue.",
    responses={
        400: {"model": ErrorResponse, "description": "No next track"},
    },
)
async def next_track() -> PlaybackStateResponse:
    """Go to next track."""
    qe = get_queue_engine()

    track = await qe.next()
    if not track:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No next track in queue",
        )

    return await get_playback_state()


@router.post(
    "/prev",
    response_model=PlaybackStateResponse,
    summary="Previous track",
    description="Go to the previous track in the queue.",
    responses={
        400: {"model": ErrorResponse, "description": "No previous track"},
    },
)
async def prev_track() -> PlaybackStateResponse:
    """Go to previous track."""
    qe = get_queue_engine()

    track = await qe.prev()
    if not track:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No previous track in queue",
        )

    return await get_playback_state()
