"""
State Manager - Bridge between MPV client and database.

Responsibilities:
- Subscribe to MPV property changes
- Debounce position updates to DB
- Handle end-file events (track finished)
- Sync playback state to queue_state table
- Graceful handling of MPV disconnection
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from tititplayer.config import MPV_SOCKET_PATH
from tititplayer.db.manager import Database, Track
from tititplayer.mpv.client import MPVClient, MPVEvent, MPVEventType

if TYPE_CHECKING:
    from collections.abc import Callable


class RepeatMode(StrEnum):
    """Repeat modes for playback."""

    OFF = "off"
    SINGLE = "single"
    ALL = "all"


@dataclass
class PlaybackState:
    """Current playback state, synced from MPV."""

    filename: str = ""
    path: str = ""
    time_pos: float = 0.0
    duration: float = 0.0
    pause: bool = True
    volume: int = 100
    speed: float = 1.0
    mute: bool = False
    # Derived state
    current_track_id: int | None = None
    current_track: Track | None = None
    repeat_mode: RepeatMode = RepeatMode.OFF
    shuffle_enabled: bool = False


class StateManager:
    """
    Manages playback state synchronization between MPV and database.

    This is the central coordinator that:
    1. Listens to MPV events
    2. Updates DB state (debounced position writes)
    3. Notifies listeners of state changes
    4. Handles MPV disconnection gracefully
    """

    def __init__(
        self,
        db: Database,
        mpv_socket_path: str = str(MPV_SOCKET_PATH),
        position_debounce_ms: int = 1000,
    ):
        self._db = db
        self._mpv_socket_path = mpv_socket_path
        self._mpv: MPVClient = MPVClient(socket_path=mpv_socket_path)

        # State
        self._state = PlaybackState()
        self._state_lock = asyncio.Lock()

        # Debounce for position writes
        self._position_debounce_ms = position_debounce_ms
        self._last_position_write: float = 0.0
        self._position_write_task: asyncio.Task | None = None

        # State change callbacks
        self._state_callbacks: list[Callable[[PlaybackState], None]] = []

        # Connection state
        self._connected = False
        self._connection_lost_callbacks: list[Callable[[], None]] = []

        # Background tasks
        self._sync_task: asyncio.Task | None = None
        self._running = False

    @property
    def state(self) -> PlaybackState:
        """Return a copy of current playback state."""
        return self._state

    @property
    def mpv(self) -> MPVClient:
        """Return the MPV client instance."""
        return self._mpv

    @property
    def is_connected(self) -> bool:
        """Check if MPV is connected."""
        return self._connected

    def add_state_callback(self, callback: Callable[[PlaybackState], None]) -> None:
        """Add a callback for state changes."""
        self._state_callbacks.append(callback)

    def remove_state_callback(self, callback: Callable[[PlaybackState], None]) -> None:
        """Remove a state change callback."""
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)

    def add_connection_lost_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback for MPV disconnection."""
        self._connection_lost_callbacks.append(callback)

    async def start(self) -> None:
        """Start the state manager."""
        if self._running:
            return

        self._running = True

        # Load initial state from DB
        await self._load_state_from_db()

        # Start MPV connection loop
        self._sync_task = asyncio.create_task(self._sync_loop())

    async def stop(self) -> None:
        """Stop the state manager."""
        self._running = False

        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        if self._position_write_task:
            self._position_write_task.cancel()
            try:
                await self._position_write_task
            except asyncio.CancelledError:
                pass

        await self._mpv.disconnect()
        self._connected = False

    async def _load_state_from_db(self) -> None:
        """Load persisted state from database."""
        queue_state = await self._db.get_queue_state()

        if queue_state:
            async with self._state_lock:
                self._state.current_track_id = queue_state.current_track_id
                self._state.time_pos = queue_state.playback_position or 0.0
                self._state.pause = queue_state.playback_status == "paused"

            # Load track info if exists
            if queue_state.current_track_id:
                track = await self._db.get_track(queue_state.current_track_id)
                if track:
                    self._state.current_track = track
                    self._state.path = track.path
                    self._state.filename = track.title or track.path.split("/")[-1]

    async def _sync_loop(self) -> None:
        """Main sync loop: maintain MPV connection and process events."""
        while self._running:
            try:
                await self._connect_and_sync()
            except Exception as e:
                # Log error but keep trying
                print(f"[StateManager] Sync error: {e}")

            if self._running:
                # Wait before reconnecting
                await asyncio.sleep(2.0)

    async def _connect_and_sync(self) -> None:
        """Connect to MPV and sync state."""
        try:
            await self._mpv.connect()
            self._connected = True
            print("[StateManager] Connected to MPV")

            # Set up event callback
            self._mpv.add_event_callback(self._handle_mpv_event)

            # Request property observations
            await self._mpv.observe_properties()

            # Restore state if we have a track
            if self._state.current_track:
                await self._restore_playback_state()

            # Listen for events (blocking)
            await self._mpv.listen()

        except ConnectionError:
            self._connected = False
            raise
        except Exception:
            self._connected = False
            raise
        finally:
            self._connected = False
            self._mpv.remove_event_callback(self._handle_mpv_event)

            # Notify connection lost
            for callback in self._connection_lost_callbacks:
                try:
                    callback()
                except Exception as e:
                    print(f"[StateManager] Connection lost callback error: {e}")

    async def _restore_playback_state(self) -> None:
        """Restore playback state from DB after reconnecting to MPV."""
        if not self._state.current_track:
            return

        # Load the track into MPV
        await self._mpv.loadfile(self._state.path)

        # Set position if we had one
        if self._state.time_pos > 0:
            await asyncio.sleep(0.5)  # Wait for file to load
            await self._mpv.seek_absolute(self._state.time_pos)

        # Set pause state
        if self._state.pause:
            await self._mpv.pause()
        else:
            await self._mpv.resume()

    async def _handle_mpv_event(self, event: MPVEvent) -> None:
        """Handle MPV events and update state."""
        try:
            if event.event == MPVEventType.PROPERTY_CHANGE:
                await self._handle_property_change(event)
            elif event.event == MPVEventType.END_FILE:
                await self._handle_end_file(event)
            elif event.event == MPVEventType.SEEK:
                # Force position write on seek
                await self._write_position_to_db(force=True)
        except Exception as e:
            print(f"[StateManager] Error handling event {event.event}: {e}")

    async def _handle_property_change(self, event: MPVEvent) -> None:
        """Handle MPV property-change events."""
        if event.name is None:
            return

        changed = False
        async with self._state_lock:
            match event.name:
                case "filename":
                    self._state.filename = str(event.data) if event.data else ""
                    changed = True
                case "path":
                    self._state.path = str(event.data) if event.data else ""
                    changed = True
                case "time-pos":
                    if isinstance(event.data, (int, float)):
                        self._state.time_pos = float(event.data)
                        # Debounce DB write
                        await self._schedule_position_write()
                case "duration":
                    if isinstance(event.data, (int, float)):
                        self._state.duration = float(event.data)
                        changed = True
                case "pause":
                    self._state.pause = bool(event.data)
                    changed = True
                case "volume":
                    if isinstance(event.data, (int, float)):
                        self._state.volume = int(event.data)
                        changed = True
                case "speed":
                    if isinstance(event.data, (int, float)):
                        self._state.speed = float(event.data)
                        changed = True
                case "mute":
                    self._state.mute = bool(event.data)
                    changed = True

        if changed:
            self._notify_state_change()

    async def _handle_end_file(self, event: MPVEvent) -> None:
        """Handle end-file event (track finished playing)."""
        # Add to history
        if self._state.current_track_id:
            await self._db.add_history_entry(
                track_id=self._state.current_track_id,
                position=int(self._state.time_pos),
                source_snapshot=self._state.path,
            )

        # Update state
        async with self._state_lock:
            self._state.current_track_id = None
            self._state.current_track = None
            self._state.filename = ""
            self._state.path = ""
            self._state.time_pos = 0.0
            self._state.duration = 0.0

        self._notify_state_change()

    async def _schedule_position_write(self) -> None:
        """Schedule a debounced position write to DB."""
        now = time.monotonic()
        elapsed = (now - self._last_position_write) * 1000

        if elapsed >= self._position_debounce_ms:
            # Write immediately if enough time has passed
            await self._write_position_to_db()
        # Otherwise, the next write will happen after debounce period

    async def _write_position_to_db(self, force: bool = False) -> None:
        """Write current position to database."""
        if not self._state.current_track_id:
            return

        now = time.monotonic()
        elapsed = (now - self._last_position_write) * 1000

        if not force and elapsed < self._position_debounce_ms:
            return

        status = "paused" if self._state.pause else "playing"
        await self._db.update_queue_state(
            current_track_id=self._state.current_track_id,
            current_position=0,  # Queue position, not playback
            playback_position=self._state.time_pos,
            playback_status=status,
            volume=self._state.volume,
        )
        self._last_position_write = now

    def _notify_state_change(self) -> None:
        """Notify all registered callbacks of state change."""
        for callback in self._state_callbacks:
            try:
                callback(self._state)
            except Exception as e:
                print(f"[StateManager] State callback error: {e}")

    # Public API for external control

    async def set_track(self, track: Track, position: float = 0.0) -> None:
        """Set the current track and start playback."""
        async with self._state_lock:
            self._state.current_track = track
            self._state.current_track_id = track.id
            self._state.path = track.path
            self._state.filename = track.title or track.path.split("/")[-1]
            self._state.time_pos = position
            self._state.duration = track.duration

        if self._connected:
            await self._mpv.loadfile(track.path)
            if position > 0:
                await asyncio.sleep(0.5)
                await self._mpv.seek_absolute(position)

        await self._db.update_queue_state(
            current_track_id=track.id,
            current_position=0,
            playback_position=position,
            playback_status="playing",
            volume=self._state.volume,
        )

        self._notify_state_change()

    async def pause(self) -> None:
        """Pause playback."""
        if self._connected:
            await self._mpv.pause()
        async with self._state_lock:
            self._state.pause = True
        self._notify_state_change()

    async def resume(self) -> None:
        """Resume playback."""
        if self._connected:
            await self._mpv.resume()
        async with self._state_lock:
            self._state.pause = False
        self._notify_state_change()

    async def toggle_pause(self) -> None:
        """Toggle pause state."""
        if self._connected:
            await self._mpv.toggle_pause()
        async with self._state_lock:
            self._state.pause = not self._state.pause
        self._notify_state_change()

    async def seek(self, position: float) -> None:
        """Seek to absolute position in seconds."""
        if self._connected:
            await self._mpv.seek_absolute(position)
        async with self._state_lock:
            self._state.time_pos = position
        await self._write_position_to_db(force=True)
        self._notify_state_change()

    async def set_volume(self, volume: int) -> None:
        """Set volume (0-100)."""
        if self._connected:
            await self._mpv.set_volume(volume)
        async with self._state_lock:
            self._state.volume = max(0, min(100, volume))
        self._notify_state_change()

    async def set_speed(self, speed: float) -> None:
        """Set playback speed (0.5-2.0)."""
        speed = max(0.25, min(4.0, speed))
        if self._connected:
            await self._mpv.set_speed(speed)
        async with self._state_lock:
            self._state.speed = speed
        self._notify_state_change()

    async def stop_playback(self) -> None:
        """Stop playback."""
        if self._connected:
            await self._mpv.stop()

        # Write final position
        await self._write_position_to_db(force=True)

        async with self._state_lock:
            self._state.current_track = None
            self._state.time_pos = 0.0
            self._state.duration = 0.0
            self._state.playback_status = "stopped"
            self._state.pause = True

        self._notify_state_change()
