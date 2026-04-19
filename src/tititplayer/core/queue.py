"""
Queue Engine - Manages playback queue and playlist logic.

Responsibilities:
- Manage queue_items table (add, remove, reorder, clear)
- Navigate: next/prev/goto with repeat modes
- Shuffle: reorder items in-place
- Expose clear async API for Phase 3
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from tititplayer.core.state import RepeatMode
from tititplayer.db.manager import Database, QueueItem, Track

if TYPE_CHECKING:
    from collections.abc import Callable

    from tititplayer.core.state import StateManager


class QueueEvent(StrEnum):
    """Events emitted by QueueEngine."""

    TRACK_ADDED = "track_added"
    TRACK_REMOVED = "track_removed"
    TRACK_MOVED = "track_moved"
    QUEUE_CLEARED = "queue_cleared"
    QUEUE_SHUFFLED = "queue_shuffled"
    CURRENT_CHANGED = "current_changed"


@dataclass
class QueueEventData:
    """Data passed in queue events."""

    event: QueueEvent
    track_id: int | None = None
    position: int | None = None
    old_position: int | None = None
    new_position: int | None = None


@dataclass
class QueueState:
    """Current queue state."""

    items: list[QueueItem] = field(default_factory=list)
    current_position: int = -1
    current_track_id: int | None = None
    repeat_mode: RepeatMode = RepeatMode.OFF
    shuffle_enabled: bool = False
    # For shuffle: keep track of original order
    original_order: list[int] = field(default_factory=list)


class QueueEngine:
    """
    Manages the playback queue.

    The queue is a list of tracks with a current position.
    Supports: add, remove, reorder, clear, shuffle, repeat modes.
    """

    def __init__(self, db: Database, state_manager: StateManager):
        self._db = db
        self._state_manager = state_manager
        self._state = QueueState()
        self._state_lock = asyncio.Lock()

        # Event callbacks
        self._event_callbacks: list[Callable[[QueueEventData], None]] = []

        # Loaded flag
        self._loaded = False

    @property
    def state(self) -> QueueState:
        """Return current queue state."""
        return self._state

    @property
    def current_position(self) -> int:
        """Return current position in queue."""
        return self._state.current_position

    @property
    def current_track(self) -> Track | None:
        """Return current track."""
        return self._state_manager.state.current_track

    @property
    def repeat_mode(self) -> RepeatMode:
        """Return current repeat mode."""
        return self._state.repeat_mode

    @property
    def shuffle_enabled(self) -> bool:
        """Return whether shuffle is enabled."""
        return self._state.shuffle_enabled

    def add_event_callback(self, callback: Callable[[QueueEventData], None]) -> None:
        """Add a callback for queue events."""
        self._event_callbacks.append(callback)

    def remove_event_callback(self, callback: Callable[[QueueEventData], None]) -> None:
        """Remove an event callback."""
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)

    async def load(self) -> None:
        """Load queue state from database."""
        if self._loaded:
            return

        async with self._state_lock:
            # Load queue items
            items = await self._db.get_queue_items()
            self._state.items = items

            # Store original order for unshuffle
            self._state.original_order = [item.track_id for item in items]

            # Load queue state
            queue_state = await self._db.get_queue_state()
            if queue_state:
                self._state.current_position = queue_state.current_position or -1
                self._state.current_track_id = queue_state.current_track_id
                # TODO: Load repeat_mode and shuffle from metadata

        self._loaded = True

    async def save(self) -> None:
        """Save current queue state to database."""
        async with self._state_lock:
            # Update queue state
            await self._db.update_queue_state(
                current_track_id=self._state.current_track_id,
                current_position=self._state.current_position,
            )

    # Queue manipulation

    async def add_track(self, track_id: int, position: int | None = None) -> int:
        """
        Add a track to the queue.

        Args:
            track_id: ID of track to add
            position: Optional position to insert at (default: end)

        Returns:
            Position where track was added
        """
        async with self._state_lock:
            # Determine position
            if position is None:
                position = len(self._state.items)
            else:
                position = max(0, min(position, len(self._state.items)))

            # Add to DB and get the item
            item_id = await self._db.add_queue_item(track_id, position)

            # Create QueueItem
            import time
            now = int(time.time())
            item = QueueItem(
                id=item_id,
                track_id=track_id,
                position=position,
                added_at=now,
                source="manual",
            )

            # Update state
            if position < len(self._state.items):
                # Insert at position
                self._state.items.insert(position, item)
                # Update positions in DB for items after
                await self._reindex_queue_items()
            else:
                # Append to end
                self._state.items.append(item)

            # Update original order
            self._state.original_order.insert(position, track_id)

        # Notify
        self._notify_event(QueueEventData(
            event=QueueEvent.TRACK_ADDED,
            track_id=track_id,
            position=position,
        ))

        return position

    async def add_tracks(self, track_ids: list[int], position: int | None = None) -> int:
        """
        Add multiple tracks to the queue.

        Args:
            track_ids: List of track IDs to add
            position: Optional position to insert at (default: end)

        Returns:
            Position where first track was added
        """
        if not track_ids:
            return -1

        async with self._state_lock:
            if position is None:
                position = len(self._state.items)
            else:
                position = max(0, min(position, len(self._state.items)))

            # Add all tracks in batch
            items = await self._db.add_queue_items(track_ids, position)

            # Update state
            for i, item in enumerate(items):
                if position + i < len(self._state.items):
                    self._state.items.insert(position + i, item)
                else:
                    self._state.items.append(item)

            # Reindex
            await self._reindex_queue_items()

            # Update original order
            for i, track_id in enumerate(track_ids):
                self._state.original_order.insert(position + i, track_id)

        return position

    async def remove_track(self, position: int) -> int | None:
        """
        Remove a track from the queue.

        Args:
            position: Position of track to remove

        Returns:
            Track ID that was removed, or None if position invalid
        """
        async with self._state_lock:
            if position < 0 or position >= len(self._state.items):
                return None

            item = self._state.items[position]
            track_id = item.track_id

            # Remove from DB
            await self._db.remove_queue_item(item.id)

            # Update state
            self._state.items.pop(position)
            self._state.original_order.pop(position)

            # Reindex
            await self._reindex_queue_items()

            # Adjust current position if needed
            if self._state.current_position == position:
                # Current track removed
                self._state.current_position = -1
                self._state.current_track_id = None
            elif self._state.current_position > position:
                # Shift current position back
                self._state.current_position -= 1

        # Notify
        self._notify_event(QueueEventData(
            event=QueueEvent.TRACK_REMOVED,
            track_id=track_id,
            position=position,
        ))

        return track_id

    async def move_track(self, old_position: int, new_position: int) -> bool:
        """
        Move a track within the queue.

        Args:
            old_position: Current position of track
            new_position: New position for track

        Returns:
            True if move was successful
        """
        async with self._state_lock:
            if old_position < 0 or old_position >= len(self._state.items):
                return False
            if new_position < 0 or new_position >= len(self._state.items):
                return False

            # Move in state
            item = self._state.items.pop(old_position)
            self._state.items.insert(new_position, item)

            # Reindex in DB
            await self._reindex_queue_items()

            # Adjust current position if needed
            if self._state.current_position == old_position:
                self._state.current_position = new_position
            elif old_position < new_position:
                if (
                    self._state.current_position > old_position
                    and self._state.current_position <= new_position
                ):
                    self._state.current_position -= 1
            else:
                if (
                    self._state.current_position >= new_position
                    and self._state.current_position < old_position
                ):
                    self._state.current_position += 1

        # Notify
        self._notify_event(QueueEventData(
            event=QueueEvent.TRACK_MOVED,
            track_id=item.track_id,
            old_position=old_position,
            new_position=new_position,
        ))

        return True

    async def clear(self) -> None:
        """Clear the entire queue."""
        async with self._state_lock:
            # Clear DB
            await self._db.clear_queue()

            # Clear state
            self._state.items.clear()
            self._state.original_order.clear()
            self._state.current_position = -1
            self._state.current_track_id = None

        # Notify
        self._notify_event(QueueEventData(event=QueueEvent.QUEUE_CLEARED))

    # Navigation

    async def goto(self, position: int) -> Track | None:
        """
        Go to a specific position in the queue.

        Args:
            position: Position to go to

        Returns:
            Track at position, or None if invalid
        """
        async with self._state_lock:
            if position < 0 or position >= len(self._state.items):
                return None

            item = self._state.items[position]
            track = await self._db.get_track(item.track_id)

            if not track:
                return None

            self._state.current_position = position
            self._state.current_track_id = track.id

        # Update state manager
        await self._state_manager.set_track(track)

        # Notify
        self._notify_event(QueueEventData(
            event=QueueEvent.CURRENT_CHANGED,
            track_id=track.id,
            position=position,
        ))

        return track

    async def next(self) -> Track | None:
        """
        Go to next track in queue.

        Returns:
            Next track, or None if at end
        """
        async with self._state_lock:
            if not self._state.items:
                return None

            current = self._state.current_position

            # Handle repeat modes
            if self._state.repeat_mode == RepeatMode.SINGLE:
                # Repeat same track
                if current >= 0 and current < len(self._state.items):
                    track = await self._db.get_track(self._state.items[current].track_id)
                    if track:
                        await self._state_manager.set_track(track, position=0.0)
                        return track
                return None

            next_pos = current + 1

            if next_pos >= len(self._state.items):
                # At end of queue
                if self._state.repeat_mode == RepeatMode.ALL:
                    next_pos = 0
                else:
                    return None

            item = self._state.items[next_pos]
            track = await self._db.get_track(item.track_id)

            if not track:
                return None

            self._state.current_position = next_pos
            self._state.current_track_id = track.id

        # Update state manager
        await self._state_manager.set_track(track)

        # Notify
        self._notify_event(QueueEventData(
            event=QueueEvent.CURRENT_CHANGED,
            track_id=track.id,
            position=next_pos,
        ))

        return track

    async def prev(self) -> Track | None:
        """
        Go to previous track in queue.

        Returns:
            Previous track, or None if at beginning
        """
        async with self._state_lock:
            if not self._state.items:
                return None

            # If more than 3 seconds into track, restart current track
            if self._state_manager.state.time_pos > 3.0:
                track = self._state_manager.state.current_track
                if track:
                    await self._state_manager.seek(0.0)
                    return track

            current = self._state.current_position
            prev_pos = current - 1

            if prev_pos < 0:
                # At beginning of queue
                if self._state.repeat_mode == RepeatMode.ALL:
                    prev_pos = len(self._state.items) - 1
                else:
                    return None

            item = self._state.items[prev_pos]
            track = await self._db.get_track(item.track_id)

            if not track:
                return None

            self._state.current_position = prev_pos
            self._state.current_track_id = track.id

        # Update state manager
        await self._state_manager.set_track(track)

        # Notify
        self._notify_event(QueueEventData(
            event=QueueEvent.CURRENT_CHANGED,
            track_id=track.id,
            position=prev_pos,
        ))

        return track

    # Shuffle and repeat

    async def shuffle(self) -> None:
        """Shuffle the queue."""
        async with self._state_lock:
            if not self._state.items:
                return

            # Remember current track
            current_track_id = self._state.current_track_id

            # Fisher-Yates shuffle
            items = self._state.items[:]
            for i in range(len(items) - 1, 0, -1):
                j = random.randint(0, i)
                items[i], items[j] = items[j], items[i]

            self._state.items = items

            # Reindex in DB
            await self._reindex_queue_items()

            # Update current position (track may have moved)
            if current_track_id:
                for i, item in enumerate(self._state.items):
                    if item.track_id == current_track_id:
                        self._state.current_position = i
                        break
            else:
                self._state.current_position = -1

            self._state.shuffle_enabled = True

        # Notify
        self._notify_event(QueueEventData(event=QueueEvent.QUEUE_SHUFFLED))

    async def unshuffle(self) -> None:
        """Restore original queue order."""
        async with self._state_lock:
            if not self._state.original_order:
                return

            # Remember current track
            current_track_id = self._state.current_track_id

            # Rebuild queue from original order
            items = []
            for track_id in self._state.original_order:
                # Find existing item with this track_id
                for item in self._state.items:
                    if item.track_id == track_id:
                        items.append(item)
                        break

            self._state.items = items

            # Reindex in DB
            await self._reindex_queue_items()

            # Update current position
            if current_track_id:
                for i, item in enumerate(self._state.items):
                    if item.track_id == current_track_id:
                        self._state.current_position = i
                        break
            else:
                self._state.current_position = -1

            self._state.shuffle_enabled = False

        # Notify
        self._notify_event(QueueEventData(event=QueueEvent.QUEUE_SHUFFLED))

    async def set_repeat_mode(self, mode: RepeatMode) -> None:
        """Set repeat mode."""
        async with self._state_lock:
            self._state.repeat_mode = mode

    async def toggle_shuffle(self) -> bool:
        """Toggle shuffle on/off. Returns new state."""
        if self._state.shuffle_enabled:
            await self.unshuffle()
        else:
            await self.shuffle()
        return self._state.shuffle_enabled

    async def toggle_repeat(self) -> RepeatMode:
        """Cycle through repeat modes. Returns new mode."""
        modes = [RepeatMode.OFF, RepeatMode.SINGLE, RepeatMode.ALL]
        current_idx = modes.index(self._state.repeat_mode)
        next_idx = (current_idx + 1) % len(modes)
        await self.set_repeat_mode(modes[next_idx])
        return self._state.repeat_mode

    # Helpers

    async def _reindex_queue_items(self) -> None:
        """Reindex queue items after modification."""
        for i, item in enumerate(self._state.items):
            if item.position != i:
                await self._db.update_queue_item_position(item.id, i)
                item.position = i

    def _notify_event(self, data: QueueEventData) -> None:
        """Notify all registered callbacks of an event."""
        for callback in self._event_callbacks:
            try:
                callback(data)
            except Exception as e:
                print(f"[QueueEngine] Event callback error: {e}")

    # Query methods

    def get_length(self) -> int:
        """Return number of items in queue."""
        return len(self._state.items)

    def get_track_at(self, position: int) -> QueueItem | None:
        """Get track at position without playing it."""
        if position < 0 or position >= len(self._state.items):
            return None
        return self._state.items[position]

    async def get_tracks(self) -> list[Track]:
        """Get all tracks in queue with full metadata."""
        tracks = []
        for item in self._state.items:
            track = await self._db.get_track(item.track_id)
            if track:
                tracks.append(track)
        return tracks
