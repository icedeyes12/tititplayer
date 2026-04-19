"""
API router for status endpoints.
"""

from __future__ import annotations

import time

from fastapi import APIRouter

from tititplayer.api.schemas import ProgressResponse, ServerStatusResponse, PlaybackStatus
from tititplayer.core.state import StateManager
from tititplayer.core.queue import QueueEngine
from tititplayer.db.manager import Database
from tititplayer.mpv.client import MPVClient


router = APIRouter(prefix="/status", tags=["status"])


# Global references (set by app lifespan)
_state_manager: StateManager | None = None
_queue_engine: QueueEngine | None = None
_db: Database | None = None
_mpv_client: MPVClient | None = None
_start_time: float = 0.0


def set_dependencies(
    state_manager: StateManager,
    queue_engine: QueueEngine,
    db: Database,
    mpv_client: MPVClient,
) -> None:
    """Set global dependencies. Called during app startup."""
    global _state_manager, _queue_engine, _db, _mpv_client, _start_time
    _state_manager = state_manager
    _queue_engine = queue_engine
    _db = db
    _mpv_client = mpv_client
    _start_time = time.time()


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


def get_mpv_client() -> MPVClient:
    if _mpv_client is None:
        raise RuntimeError("MPV client not initialized")
    return _mpv_client


@router.get(
    "",
    response_model=ServerStatusResponse,
    summary="Get server status",
    description="Get the overall server status including connection states.",
)
async def get_server_status() -> ServerStatusResponse:
    """Get server status."""
    sm = get_state_manager()
    qe = get_queue_engine()
    mpv = get_mpv_client()

    return ServerStatusResponse(
        status="ok",
        mpv_connected=mpv.is_connected,
        database_connected=True,  # If we're here, DB is connected
        queue_length=qe.get_length(),
        uptime_seconds=time.time() - _start_time,
    )


@router.get(
    "/progress",
    response_model=ProgressResponse,
    summary="Get playback progress",
    description="Get lightweight playback progress for polling clients (TUI, widgets).",
)
async def get_progress() -> ProgressResponse:
    """Get playback progress (lightweight)."""
    sm = get_state_manager()
    state = sm.state

    # Map playback status
    if not state.pause and state.filename:
        pb_status = PlaybackStatus.PLAYING
    elif state.filename:
        pb_status = PlaybackStatus.PAUSED
    else:
        pb_status = PlaybackStatus.STOPPED

    return ProgressResponse(
        status=pb_status,
        track_id=state.current_track_id,
        position=state.time_pos or 0.0,
        duration=state.duration or 0.0,
        volume=state.volume,
        speed=state.speed,
    )


@router.get(
    "/health",
    summary="Health check",
    description="Simple health check endpoint.",
)
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
