"""
Tests for the API server.

These tests use FastAPI's TestClient to verify endpoint behavior.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tititplayer.api.app import app
from tititplayer.db.manager import Database, Track, QueueState, QueueItem


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def mock_components(temp_db_path):
    """Mock all components for testing."""
    # Create mock components
    mock_db = MagicMock(spec=Database)
    mock_state_manager = MagicMock()
    mock_queue_engine = MagicMock()
    mock_mpv_client = MagicMock()

    # Set up state manager mock
    mock_state = MagicMock()
    mock_state.pause = True
    mock_state.filename = None
    mock_state.time_pos = 0.0
    mock_state.duration = 0.0
    mock_state.volume = 100
    mock_state.speed = 1.0
    mock_state.mute = False
    mock_state.current_track = None
    mock_state.current_track_id = None
    mock_state_manager.state = mock_state
    mock_state_manager.pause = AsyncMock()
    mock_state_manager.resume = AsyncMock()
    mock_state_manager.toggle_pause = AsyncMock()
    mock_state_manager.stop = AsyncMock()
    mock_state_manager.set_volume = AsyncMock()
    mock_state_manager.set_speed = AsyncMock()
    mock_state_manager.set_mute = AsyncMock()
    mock_state_manager.set_track = AsyncMock()
    mock_state_manager.seek = AsyncMock()

    # Set up queue engine mock
    mock_queue_state = MagicMock()
    mock_queue_state.items = []
    mock_queue_state.current_position = -1
    mock_queue_state.current_track_id = None
    mock_queue_state.repeat_mode = MagicMock()
    mock_queue_state.repeat_mode.value = "off"
    mock_queue_state.shuffle_enabled = False
    mock_queue_engine.state = mock_queue_state
    mock_queue_engine.repeat_mode = mock_queue_state.repeat_mode
    mock_queue_engine.shuffle_enabled = False
    mock_queue_engine.add_track = AsyncMock(return_value=0)
    mock_queue_engine.add_tracks = AsyncMock()
    mock_queue_engine.remove_track = AsyncMock(return_value=None)
    mock_queue_engine.move_track = AsyncMock(return_value=True)
    mock_queue_engine.clear = AsyncMock()
    mock_queue_engine.goto = AsyncMock(return_value=None)
    mock_queue_engine.next = AsyncMock(return_value=None)
    mock_queue_engine.prev = AsyncMock(return_value=None)
    mock_queue_engine.toggle_shuffle = AsyncMock()
    mock_queue_engine.toggle_repeat = AsyncMock()
    mock_queue_engine.set_repeat_mode = AsyncMock()
    mock_queue_engine.get_track_at = AsyncMock(return_value=None)
    mock_queue_engine.get_length = MagicMock(return_value=0)

    # Set up mpv client mock
    mock_mpv_client.is_connected = False

    return {
        "db": mock_db,
        "state_manager": mock_state_manager,
        "queue_engine": mock_queue_engine,
        "mpv_client": mock_mpv_client,
    }


class TestStatusEndpoints:
    """Tests for status endpoints."""

    def test_health_check(self, mock_components):
        """Test health check endpoint."""
        # Set dependencies manually
        from tititplayer.api import status as status_router
        status_router._state_manager = mock_components["state_manager"]
        status_router._queue_engine = mock_components["queue_engine"]
        status_router._db = mock_components["db"]
        status_router._mpv_client = mock_components["mpv_client"]
        status_router._start_time = 0.0

        client = TestClient(app)
        response = client.get("/api/v1/status/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestPlaybackEndpoints:
    """Tests for playback endpoints."""

    def test_get_playback_state_stopped(self, mock_components):
        """Test getting playback state when stopped."""
        from tititplayer.api import playback as playback_router
        playback_router._state_manager = mock_components["state_manager"]
        playback_router._queue_engine = mock_components["queue_engine"]
        playback_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.get("/api/v1/playback")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert data["track"] is None

    def test_pause(self, mock_components):
        """Test pause endpoint."""
        from tititplayer.api import playback as playback_router
        playback_router._state_manager = mock_components["state_manager"]
        playback_router._queue_engine = mock_components["queue_engine"]
        playback_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.post("/api/v1/playback/pause")
        assert response.status_code == 200
        mock_components["state_manager"].pause.assert_called_once()

    def test_stop(self, mock_components):
        """Test stop endpoint."""
        from tititplayer.api import playback as playback_router
        playback_router._state_manager = mock_components["state_manager"]
        playback_router._queue_engine = mock_components["queue_engine"]
        playback_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.post("/api/v1/playback/stop")
        assert response.status_code == 200
        mock_components["state_manager"].stop.assert_called_once()

    def test_set_volume(self, mock_components):
        """Test volume endpoint."""
        from tititplayer.api import playback as playback_router
        playback_router._state_manager = mock_components["state_manager"]
        playback_router._queue_engine = mock_components["queue_engine"]
        playback_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.post("/api/v1/playback/volume", json={"volume": 50})
        assert response.status_code == 200
        mock_components["state_manager"].set_volume.assert_called_once_with(50)

    def test_set_volume_invalid(self, mock_components):
        """Test volume endpoint with invalid value."""
        from tititplayer.api import playback as playback_router
        playback_router._state_manager = mock_components["state_manager"]
        playback_router._queue_engine = mock_components["queue_engine"]
        playback_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.post("/api/v1/playback/volume", json={"volume": 150})
        assert response.status_code == 422  # Validation error

    def test_seek_no_track(self, mock_components):
        """Test seek when no track is loaded."""
        from tititplayer.api import playback as playback_router
        playback_router._state_manager = mock_components["state_manager"]
        playback_router._queue_engine = mock_components["queue_engine"]
        playback_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.post("/api/v1/playback/seek", json={"position": 30.0})
        assert response.status_code == 400


class TestQueueEndpoints:
    """Tests for queue endpoints."""

    def test_get_empty_queue(self, mock_components):
        """Test getting empty queue."""
        from tititplayer.api import queue as queue_router
        queue_router._state_manager = mock_components["state_manager"]
        queue_router._queue_engine = mock_components["queue_engine"]
        queue_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.get("/api/v1/queue")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["length"] == 0
        assert data["current_position"] == -1

    def test_clear_queue(self, mock_components):
        """Test clearing queue."""
        from tititplayer.api import queue as queue_router
        queue_router._state_manager = mock_components["state_manager"]
        queue_router._queue_engine = mock_components["queue_engine"]
        queue_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.post("/api/v1/queue/clear")
        assert response.status_code == 200
        mock_components["queue_engine"].clear.assert_called_once()

    def test_shuffle(self, mock_components):
        """Test shuffle endpoint."""
        from tititplayer.api import queue as queue_router
        queue_router._state_manager = mock_components["state_manager"]
        queue_router._queue_engine = mock_components["queue_engine"]
        queue_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.post("/api/v1/queue/shuffle")
        assert response.status_code == 200
        mock_components["queue_engine"].toggle_shuffle.assert_called_once()


class TestTrackEndpoints:
    """Tests for tracks endpoints."""

    def test_search_empty(self, mock_components):
        """Test searching tracks with empty query."""
        mock_components["db"].get_all_tracks = AsyncMock(return_value=[])
        mock_components["db"].search_tracks = AsyncMock(return_value=[])

        from tititplayer.api import tracks as tracks_router
        tracks_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.get("/api/v1/tracks?q=")
        assert response.status_code == 200
        data = response.json()
        assert data["tracks"] == []

    def test_get_track_not_found(self, mock_components):
        """Test getting non-existent track."""
        mock_components["db"].get_track = AsyncMock(return_value=None)

        from tititplayer.api import tracks as tracks_router
        tracks_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.get("/api/v1/tracks/999")
        assert response.status_code == 404


class TestPlaylistEndpoints:
    """Tests for playlists endpoints."""

    def test_get_playlists_empty(self, mock_components):
        """Test getting empty playlists."""
        mock_components["db"].get_all_playlists = AsyncMock(return_value=[])

        from tititplayer.api import playlists as playlists_router
        playlists_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.get("/api/v1/playlists")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_playlist_not_found(self, mock_components):
        """Test getting non-existent playlist."""
        mock_components["db"].get_playlist = AsyncMock(return_value=None)

        from tititplayer.api import playlists as playlists_router
        playlists_router._db = mock_components["db"]

        client = TestClient(app)
        response = client.get("/api/v1/playlists/999")
        assert response.status_code == 404
