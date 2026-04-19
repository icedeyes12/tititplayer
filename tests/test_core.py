"""
Tests for the State Manager and Queue Engine.

Note: These tests mock MPV connection to avoid needing a running MPV instance.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tititplayer.core.queue import QueueEngine, QueueEvent
from tititplayer.core.state import PlaybackState, RepeatMode, StateManager
from tititplayer.db.manager import Database, Track


@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        async with db:
            yield db


@pytest.fixture
def sample_tracks(temp_db: Database):
    """Create sample tracks for testing."""
    async def _create():
        tracks = []
        for i in range(5):
            track_id = await temp_db.add_track(
                path=f"/music/track{i}.mp3",
                title=f"Track {i}",
                artist=f"Artist {i}",
                duration=180.0 + i * 10,
            )
            tracks.append(track_id)
        return tracks
    return _create


class TestPlaybackState:
    """Tests for PlaybackState dataclass."""

    def test_default_values(self):
        """Test default values are correct."""
        state = PlaybackState()
        assert state.filename == ""
        assert state.path == ""
        assert state.time_pos == 0.0
        assert state.duration == 0.0
        assert state.pause is True
        assert state.volume == 100
        assert state.speed == 1.0
        assert state.mute is False
        assert state.current_track_id is None
        assert state.current_track is None
        assert state.repeat_mode == RepeatMode.OFF

    def test_custom_values(self):
        """Test custom values are set correctly."""
        track = Track(id=1, path="/test.mp3", title="Test")
        state = PlaybackState(
            filename="Test.mp3",
            path="/test.mp3",
            time_pos=30.5,
            duration=180.0,
            pause=False,
            volume=80,
            current_track_id=1,
            current_track=track,
        )
        assert state.filename == "Test.mp3"
        assert state.time_pos == 30.5
        assert state.pause is False
        assert state.volume == 80
        assert state.current_track_id == 1


class TestRepeatMode:
    """Tests for RepeatMode enum."""

    def test_values(self):
        """Test enum values."""
        assert RepeatMode.OFF == "off"
        assert RepeatMode.SINGLE == "single"
        assert RepeatMode.ALL == "all"


class TestStateManagerInit:
    """Tests for StateManager initialization."""

    def test_init(self, temp_db: Database):
        """Test StateManager initialization."""
        sm = StateManager(temp_db)
        assert sm._db == temp_db
        assert sm.is_connected is False
        assert sm.state.pause is True

    def test_add_remove_callbacks(self, temp_db: Database):
        """Test adding and removing callbacks."""
        sm = StateManager(temp_db)

        state_cb = MagicMock()
        conn_lost_cb = MagicMock()

        sm.add_state_callback(state_cb)
        sm.add_connection_lost_callback(conn_lost_cb)

        assert state_cb in sm._state_callbacks
        assert conn_lost_cb in sm._connection_lost_callbacks

        sm.remove_state_callback(state_cb)
        assert state_cb not in sm._state_callbacks


class TestStateManagerPlayback:
    """Tests for StateManager playback control (with mocked MPV)."""

    @pytest.mark.asyncio
    async def test_set_track(self, temp_db: Database):
        """Test setting a track."""
        sm = StateManager(temp_db)

        # Create a track
        track_id = await temp_db.add_track(
            path="/test.mp3",
            title="Test Song",
            artist="Test Artist",
            duration=180.0,
        )
        track = await temp_db.get_track(track_id)

        # Set the track
        await sm.set_track(track)

        assert sm.state.current_track_id == track_id
        assert sm.state.filename == "Test Song"
        assert sm.state.path == "/test.mp3"

        # Check DB state
        db_state = await temp_db.get_queue_state()
        assert db_state.current_track_id == track_id
        assert db_state.playback_status == "playing"

    @pytest.mark.asyncio
    async def test_pause_resume(self, temp_db: Database):
        """Test pause and resume."""
        sm = StateManager(temp_db)

        # Create and set a track
        track_id = await temp_db.add_track(path="/test.mp3", title="Test")
        track = await temp_db.get_track(track_id)
        await sm.set_track(track)

        # Pause
        await sm.pause()
        assert sm.state.pause is True

        # Resume
        await sm.resume()
        assert sm.state.pause is False

        # Toggle
        await sm.toggle_pause()
        assert sm.state.pause is True

    @pytest.mark.asyncio
    async def test_volume_control(self, temp_db: Database):
        """Test volume control."""
        sm = StateManager(temp_db)

        await sm.set_volume(50)
        assert sm.state.volume == 50

        # Clamp to max
        await sm.set_volume(150)
        assert sm.state.volume == 100

        # Clamp to min
        await sm.set_volume(-10)
        assert sm.state.volume == 0

    @pytest.mark.asyncio
    async def test_seek(self, temp_db: Database):
        """Test seeking."""
        sm = StateManager(temp_db)

        track_id = await temp_db.add_track(path="/test.mp3", title="Test")
        track = await temp_db.get_track(track_id)
        await sm.set_track(track)

        await sm.seek(60.0)
        assert sm.state.time_pos == 60.0


class TestQueueEngineInit:
    """Tests for QueueEngine initialization."""

    @pytest.mark.asyncio
    async def test_init(self, temp_db: Database):
        """Test QueueEngine initialization."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        assert qe._db == temp_db
        assert qe._state_manager == sm
        assert qe.get_length() == 0

    @pytest.mark.asyncio
    async def test_load(self, temp_db: Database):
        """Test loading queue from database."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        # Add some tracks to queue in DB
        track_id = await temp_db.add_track(path="/q.mp3", title="Queue Test")
        await temp_db.add_queue_item(track_id, position=0)

        await qe.load()

        assert qe.get_length() == 1


class TestQueueEngineOperations:
    """Tests for QueueEngine queue operations."""

    @pytest.mark.asyncio
    async def test_add_track(self, temp_db: Database):
        """Test adding tracks to queue."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        track_id = await temp_db.add_track(path="/t1.mp3", title="Track 1")

        pos = await qe.add_track(track_id)
        assert pos == 0
        assert qe.get_length() == 1

        # Add another
        track_id2 = await temp_db.add_track(path="/t2.mp3", title="Track 2")
        pos2 = await qe.add_track(track_id2)
        assert pos2 == 1
        assert qe.get_length() == 2

    @pytest.mark.asyncio
    async def test_add_tracks_batch(self, temp_db: Database):
        """Test adding multiple tracks at once."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        # Create tracks
        track_ids = []
        for i in range(3):
            tid = await temp_db.add_track(path=f"/b{i}.mp3", title=f"Batch {i}")
            track_ids.append(tid)

        pos = await qe.add_tracks(track_ids)
        assert pos == 0
        assert qe.get_length() == 3

    @pytest.mark.asyncio
    async def test_remove_track(self, temp_db: Database):
        """Test removing tracks from queue."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        track_id = await temp_db.add_track(path="/r.mp3", title="Remove Test")
        await qe.add_track(track_id)

        assert qe.get_length() == 1

        removed_id = await qe.remove_track(0)
        assert removed_id == track_id
        assert qe.get_length() == 0

    @pytest.mark.asyncio
    async def test_move_track(self, temp_db: Database):
        """Test moving tracks within queue."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        # Create and add tracks
        track_ids = []
        for i in range(3):
            tid = await temp_db.add_track(path=f"/m{i}.mp3", title=f"Move {i}")
            track_ids.append(tid)
        await qe.add_tracks(track_ids)

        # Move track 0 to position 2
        result = await qe.move_track(0, 2)
        assert result is True

        # Verify order changed
        assert qe.get_track_at(2).track_id == track_ids[0]

    @pytest.mark.asyncio
    async def test_clear(self, temp_db: Database):
        """Test clearing queue."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        track_ids = []
        for i in range(3):
            tid = await temp_db.add_track(path=f"/c{i}.mp3", title=f"Clear {i}")
            track_ids.append(tid)
        await qe.add_tracks(track_ids)

        assert qe.get_length() == 3

        await qe.clear()
        assert qe.get_length() == 0


class TestQueueEngineNavigation:
    """Tests for QueueEngine navigation."""

    @pytest.mark.asyncio
    async def test_goto(self, temp_db: Database):
        """Test going to a specific position."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        # Create and add tracks
        track_ids = []
        for i in range(3):
            tid = await temp_db.add_track(path=f"/g{i}.mp3", title=f"Goto {i}")
            track_ids.append(tid)
        await qe.add_tracks(track_ids)

        # Go to position 1
        track = await qe.goto(1)
        assert track is not None
        assert track.id == track_ids[1]
        assert qe.current_position == 1

    @pytest.mark.asyncio
    async def test_next(self, temp_db: Database):
        """Test going to next track."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        # Create and add tracks
        track_ids = []
        for i in range(3):
            tid = await temp_db.add_track(path=f"/n{i}.mp3", title=f"Next {i}")
            track_ids.append(tid)
        await qe.add_tracks(track_ids)

        # Start at position 0
        await qe.goto(0)

        # Next
        track = await qe.next()
        assert track is not None
        assert track.id == track_ids[1]
        assert qe.current_position == 1

    @pytest.mark.asyncio
    async def test_prev(self, temp_db: Database):
        """Test going to previous track."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        # Create and add tracks
        track_ids = []
        for i in range(3):
            tid = await temp_db.add_track(path=f"/p{i}.mp3", title=f"Prev {i}")
            track_ids.append(tid)
        await qe.add_tracks(track_ids)

        # Start at position 2
        await qe.goto(2)

        # Prev
        track = await qe.prev()
        assert track is not None
        assert track.id == track_ids[1]
        assert qe.current_position == 1

    @pytest.mark.asyncio
    async def test_next_at_end(self, temp_db: Database):
        """Test next at end of queue returns None."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        track_id = await temp_db.add_track(path="/e.mp3", title="End Test")
        await qe.add_track(track_id)
        await qe.goto(0)

        # At end, next should return None
        track = await qe.next()
        assert track is None


class TestQueueEngineRepeatMode:
    """Tests for repeat mode functionality."""

    @pytest.mark.asyncio
    async def test_repeat_single(self, temp_db: Database):
        """Test repeat single mode."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        track_id = await temp_db.add_track(path="/rs.mp3", title="Repeat Single")
        await qe.add_track(track_id)
        await qe.goto(0)

        # Set repeat single
        await qe.set_repeat_mode(RepeatMode.SINGLE)

        # Next should repeat same track
        track = await qe.next()
        assert track is not None
        assert track.id == track_id
        assert qe.current_position == 0

    @pytest.mark.asyncio
    async def test_repeat_all(self, temp_db: Database):
        """Test repeat all mode."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        track_ids = []
        for i in range(2):
            tid = await temp_db.add_track(path=f"/ra{i}.mp3", title=f"Repeat All {i}")
            track_ids.append(tid)
        await qe.add_tracks(track_ids)
        await qe.goto(1)  # At last position

        # Set repeat all
        await qe.set_repeat_mode(RepeatMode.ALL)

        # Next should wrap to first
        track = await qe.next()
        assert track is not None
        assert track.id == track_ids[0]
        assert qe.current_position == 0

    @pytest.mark.asyncio
    async def test_toggle_repeat(self, temp_db: Database):
        """Test cycling repeat modes."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        assert qe.repeat_mode == RepeatMode.OFF

        mode = await qe.toggle_repeat()
        assert mode == RepeatMode.SINGLE

        mode = await qe.toggle_repeat()
        assert mode == RepeatMode.ALL

        mode = await qe.toggle_repeat()
        assert mode == RepeatMode.OFF


class TestQueueEngineShuffle:
    """Tests for shuffle functionality."""

    @pytest.mark.asyncio
    async def test_shuffle(self, temp_db: Database):
        """Test shuffling queue."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        # Create and add tracks
        track_ids = []
        for i in range(10):
            tid = await temp_db.add_track(path=f"/sh{i}.mp3", title=f"Shuffle {i}")
            track_ids.append(tid)
        await qe.add_tracks(track_ids)

        original_order = [item.track_id for item in qe.state.items]

        # Shuffle
        await qe.shuffle()
        assert qe.shuffle_enabled is True

        # Order should be different (likely, but not guaranteed with random)
        # At least check that all tracks are still present
        new_order = [item.track_id for item in qe.state.items]
        assert set(new_order) == set(original_order)

    @pytest.mark.asyncio
    async def test_unshuffle(self, temp_db: Database):
        """Test unshuffling queue."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        # Create and add tracks
        track_ids = []
        for i in range(5):
            tid = await temp_db.add_track(path=f"/ush{i}.mp3", title=f"Unshuffle {i}")
            track_ids.append(tid)
        await qe.add_tracks(track_ids)

        original_order = [item.track_id for item in qe.state.items]

        # Shuffle then unshuffle
        await qe.shuffle()
        await qe.unshuffle()

        assert qe.shuffle_enabled is False

        # Should be back to original order
        restored_order = [item.track_id for item in qe.state.items]
        assert restored_order == original_order

    @pytest.mark.asyncio
    async def test_toggle_shuffle(self, temp_db: Database):
        """Test toggling shuffle."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        track_id = await temp_db.add_track(path="/ts.mp3", title="Toggle Shuffle")
        await qe.add_track(track_id)

        assert qe.shuffle_enabled is False

        state = await qe.toggle_shuffle()
        assert state is True

        state = await qe.toggle_shuffle()
        assert state is False


class TestQueueEngineEvents:
    """Tests for queue event callbacks."""

    @pytest.mark.asyncio
    async def test_track_added_event(self, temp_db: Database):
        """Test track added event."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        events = []
        qe.add_event_callback(lambda e: events.append(e))

        track_id = await temp_db.add_track(path="/ev.mp3", title="Event Test")
        await qe.add_track(track_id)

        assert len(events) == 1
        assert events[0].event == QueueEvent.TRACK_ADDED
        assert events[0].track_id == track_id

    @pytest.mark.asyncio
    async def test_track_removed_event(self, temp_db: Database):
        """Test track removed event."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        events = []
        qe.add_event_callback(lambda e: events.append(e))

        track_id = await temp_db.add_track(path="/evr.mp3", title="Event Remove")
        await qe.add_track(track_id)
        events.clear()

        await qe.remove_track(0)

        assert len(events) == 1
        assert events[0].event == QueueEvent.TRACK_REMOVED

    @pytest.mark.asyncio
    async def test_queue_cleared_event(self, temp_db: Database):
        """Test queue cleared event."""
        sm = StateManager(temp_db)
        qe = QueueEngine(temp_db, sm)

        events = []
        qe.add_event_callback(lambda e: events.append(e))

        track_id = await temp_db.add_track(path="/evc.mp3", title="Event Clear")
        await qe.add_track(track_id)
        events.clear()

        await qe.clear()

        assert len(events) == 1
        assert events[0].event == QueueEvent.QUEUE_CLEARED
