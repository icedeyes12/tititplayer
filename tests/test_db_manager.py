"""
Tests for the database manager.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from tititplayer.db.manager import Database, Track, QueueState, QueueItem, HistoryEntry, Playlist


@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        async with db:
            yield db


@pytest.mark.asyncio
async def test_add_and_get_track(temp_db: Database):
    """Test adding and retrieving a track."""
    track_id = await temp_db.add_track(
        path="/music/test.mp3",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        duration=180.5,
    )

    assert track_id > 0

    track = await temp_db.get_track(track_id)
    assert track is not None
    assert track.title == "Test Song"
    assert track.artist == "Test Artist"
    assert track.album == "Test Album"
    assert track.duration == 180.5


@pytest.mark.asyncio
async def test_get_track_by_path(temp_db: Database):
    """Test retrieving a track by path."""
    await temp_db.add_track(
        path="/music/unique.mp3",
        title="Unique Song",
    )

    track = await temp_db.get_track_by_path("/music/unique.mp3")
    assert track is not None
    assert track.title == "Unique Song"


@pytest.mark.asyncio
async def test_search_tracks(temp_db: Database):
    """Test searching tracks."""
    await temp_db.add_track(path="/a.mp3", title="Alpha", artist="Artist A")
    await temp_db.add_track(path="/b.mp3", title="Beta", artist="Artist B")
    await temp_db.add_track(path="/c.mp3", title="Gamma", artist="Artist C")

    results = await temp_db.search_tracks("Alpha")
    assert len(results) == 1
    assert results[0].title == "Alpha"

    results = await temp_db.search_tracks("Artist")
    assert len(results) == 3


@pytest.mark.asyncio
async def test_queue_state(temp_db: Database):
    """Test queue state operations."""
    state = await temp_db.get_queue_state()
    assert state.volume == 100
    assert state.playback_status == "stopped"
    assert state.repeat_mode == "none"

    # Create a track first (FK constraint)
    track_id = await temp_db.add_track(path="/state.mp3", title="State Test")

    # Update state
    updated = await temp_db.update_queue_state(
        current_track_id=track_id,
        playback_position=30.5,
        playback_status="playing",
        volume=80,
    )
    assert updated.current_track_id == track_id
    assert updated.playback_position == 30.5
    assert updated.playback_status == "playing"
    assert updated.volume == 80


@pytest.mark.asyncio
async def test_queue_items(temp_db: Database):
    """Test queue item operations."""
    track_id = await temp_db.add_track(path="/queue.mp3", title="Queue Test")

    item_id = await temp_db.add_queue_item(track_id, position=0)
    assert item_id > 0

    items = await temp_db.get_queue_items()
    assert len(items) == 1
    assert items[0].track_id == track_id

    await temp_db.clear_queue()
    items = await temp_db.get_queue_items()
    assert len(items) == 0


@pytest.mark.asyncio
async def test_history(temp_db: Database):
    """Test history operations."""
    track_id = await temp_db.add_track(path="/history.mp3", title="History Test")

    entry_id = await temp_db.add_history_entry(
        track_id=track_id,
        title_snapshot="History Test",
        artist_snapshot="Test Artist",
        position=120,
        completed=True,
    )
    assert entry_id > 0

    history = await temp_db.get_history(limit=10)
    assert len(history) == 1
    assert history[0].track_id == track_id
    assert history[0].position == 120
    assert history[0].completed is True
    assert history[0].title_snapshot == "History Test"


@pytest.mark.asyncio
async def test_playlists(temp_db: Database):
    """Test playlist operations."""
    # Create playlist
    playlist_id = await temp_db.create_playlist(
        name="My Playlist", description="Test playlist"
    )
    assert playlist_id > 0

    # Add tracks
    track_id1 = await temp_db.add_track(path="/p1.mp3", title="Playlist Song 1")
    track_id2 = await temp_db.add_track(path="/p2.mp3", title="Playlist Song 2")

    await temp_db.add_track_to_playlist(playlist_id, track_id1, position=0)
    await temp_db.add_track_to_playlist(playlist_id, track_id2, position=1)

    # Get playlist
    playlist = await temp_db.get_playlist(playlist_id)
    assert playlist is not None
    assert playlist.name == "My Playlist"
    assert len(playlist.tracks) == 2

    # Remove track
    await temp_db.remove_track_from_playlist(playlist_id, track_id1)
    playlist = await temp_db.get_playlist(playlist_id)
    assert len(playlist.tracks) == 1

    # Delete playlist
    deleted = await temp_db.delete_playlist(playlist_id)
    assert deleted is True

    playlist = await temp_db.get_playlist(playlist_id)
    assert playlist is None


@pytest.mark.asyncio
async def test_delete_track(temp_db: Database):
    """Test deleting a track."""
    track_id = await temp_db.add_track(path="/delete.mp3", title="Delete Me")

    deleted = await temp_db.delete_track(track_id)
    assert deleted is True

    track = await temp_db.get_track(track_id)
    assert track is None
