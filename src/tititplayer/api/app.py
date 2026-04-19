"""
Main FastAPI application for tititplayer.

Provides REST API for controlling the music player.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import routers
from tititplayer.api import playback, playlists, queue, status, tracks
from tititplayer.api.schemas import ErrorResponse
from tititplayer.config import API_HOST, API_PORT, DATABASE_PATH, MPV_SOCKET_PATH
from tititplayer.core.queue import QueueEngine
from tititplayer.core.state import StateManager
from tititplayer.db.manager import Database
from tititplayer.mpv.client import MPVClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("tititplayer.api")


# Global components
_db: Database | None = None
_mpv_client: MPVClient | None = None
_state_manager: StateManager | None = None
_queue_engine: QueueEngine | None = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan - startup and shutdown."""
    global _db, _mpv_client, _state_manager, _queue_engine

    logger.info("Starting tititplayer daemon...")

    # Initialize database
    logger.info(f"Connecting to database: {DATABASE_PATH}")
    _db = Database(DATABASE_PATH)
    await _db.__aenter__()

    # Initialize MPV client
    logger.info(f"Connecting to MPV: {MPV_SOCKET_PATH}")
    _mpv_client = MPVClient(MPV_SOCKET_PATH)

    # Initialize state manager
    _state_manager = StateManager(_db, str(MPV_SOCKET_PATH))
    await _state_manager.start()

    # Initialize queue engine
    _queue_engine = QueueEngine(_db, _state_manager)
    await _queue_engine.load()

    # Set dependencies for routers
    playback.set_dependencies(_state_manager, _queue_engine, _db)
    queue.set_dependencies(_state_manager, _queue_engine, _db)
    tracks.set_dependencies(_db)
    playlists.set_dependencies(_db)
    status.set_dependencies(_state_manager, _queue_engine, _db, _mpv_client)

    # Start MPV connection in background
    # (will auto-reconnect if MPV is not running yet)
    async def connect_mpv():
        """Try to connect to MPV, with retries."""
        max_retries = 10
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                await _mpv_client.connect()
                logger.info("Connected to MPV")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"MPV connection attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"Failed to connect to MPV after {max_retries} attempts: {e}"
                    )
                    logger.warning(
                        "Running in headless mode - "
                        "start MPV with: mpv --idle --input-ipc-server=~/.mpvsocket"
                    )

    mpv_task = asyncio.create_task(connect_mpv())

    logger.info("Tititplayer daemon started")

    yield

    # Cleanup
    logger.info("Shutting down tititplayer daemon...")

    mpv_task.cancel()
    try:
        await mpv_task
    except asyncio.CancelledError:
        pass

    if _mpv_client and _mpv_client.is_connected:
        await _mpv_client.disconnect()
        logger.info("Disconnected from MPV")

    if _db:
        await _db.__aexit__(None, None, None)
        logger.info("Database connection closed")

    logger.info("Tititplayer daemon stopped")


# Create FastAPI app
app = FastAPI(
    title="Tititplayer API",
    description="REST API for controlling the tititplayer music daemon",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            detail=str(exc),
            code="INTERNAL_ERROR",
        ).model_dump(),
    )


# Include routers
app.include_router(playback.router, prefix="/api/v1")
app.include_router(queue.router, prefix="/api/v1")
app.include_router(tracks.router, prefix="/api/v1")
app.include_router(playlists.router, prefix="/api/v1")
app.include_router(status.router, prefix="/api/v1")


# Root endpoint
@app.get("/", include_in_schema=False)
async def root() -> dict:
    """Root endpoint redirect."""
    return {
        "name": "Tititplayer API",
        "version": "0.1.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


# Convenience function to run the server
def run_server(host: str = API_HOST, port: int = API_PORT) -> None:
    """Run the FastAPI server."""
    import uvicorn

    uvicorn.run(
        "tititplayer.api.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )
