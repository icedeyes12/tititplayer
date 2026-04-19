"""
Async database manager for tititplayer using aiosqlite.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Self

import aiosqlite

from tititplayer.config import DATABASE_PATH, DATABASE_SCHEMA_PATH


@dataclass
class Track:
    """Represents a track in the library."""

    id: int | None = None
    path: str = ""
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float = 0.0
    created_at: int = 0
    source: str = "local"
    kind: str = "unknown"

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Self:
        return cls(
            id=row["id"],
            path=row["path"],
            title=row["title"] or "",
            artist=row["artist"] or "",
            album=row["album"] or "",
            duration=row["duration"] or 0.0,
            created_at=row["created_at"],
            source=row["source"],
            kind=row["kind"],
        )


@dataclass
class QueueState:
    """Represents the current player state."""

    current_track_id: int | None = None
    current_position: int = 0
    playback_position: float = 0.0
    playback_status: str = "stopped"  # 'playing', 'paused', 'stopped'
    volume: int = 100
    repeat_mode: str = "none"  # 'none', 'single', 'all'
    shuffle_mode: bool = False
    updated_at: int = 0

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Self:
        return cls(
            current_track_id=row["current_track_id"],
            current_position=row["current_position"] or 0,
            playback_position=row["playback_position"] or 0.0,
            playback_status=row["playback_status"] or "stopped",
            volume=row["volume"] or 100,
            repeat_mode=row["repeat_mode"] or "none",
            shuffle_mode=bool(row["shuffle_mode"]),
            updated_at=row["updated_at"],
        )


@dataclass
class QueueItem:
    """Represents an item in the play queue."""

    id: int | None = None
    track_id: int = 0
    position: int = 0
    added_at: int = 0
    source: str = "manual"

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Self:
        return cls(
            id=row["id"],
            track_id=row["track_id"],
            position=row["position"],
            added_at=row["added_at"],
            source=row["source"],
        )


@dataclass
class HistoryEntry:
    """Represents a play history entry."""

    id: int | None = None
    track_id: int | None = None
    played_at: int = 0
    position: int = 0  # Playback position in seconds
    completed: bool = False
    title_snapshot: str = ""
    artist_snapshot: str = ""
    source_snapshot: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Self:
        return cls(
            id=row["id"],
            track_id=row["track_id"],
            played_at=row["played_at"],
            position=row["position"] or 0,
            completed=bool(row["completed"]),
            title_snapshot=row["title_snapshot"] or "",
            artist_snapshot=row["artist_snapshot"] or "",
            source_snapshot=row["source_snapshot"] or "",
        )


@dataclass
class Playlist:
    """Represents a user playlist."""

    id: int | None = None
    name: str = ""
    description: str = ""
    created_at: int = 0
    updated_at: int = 0
    tracks: list[Track] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Self:
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class Database:
    """
    Async database manager for tititplayer.

    Provides a clean async interface to SQLite via aiosqlite,
    with automatic schema initialization and high-level CRUD operations.
    """

    _instance: Database | None = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, db_path: Path = DATABASE_PATH) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @classmethod
    async def get_instance(cls) -> Self:
        """Get the singleton database instance."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance._initialize()
        return cls._instance

    async def _initialize(self) -> None:
        """Initialize the database connection and schema."""
        # Ensure directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

        # Enable foreign keys
        await self._conn.execute("PRAGMA foreign_keys = ON")

        # Load and execute schema
        schema_sql = DATABASE_SCHEMA_PATH.read_text()
        await self._conn.executescript(schema_sql)
        await self._conn.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            Database._instance = None

    async def __aenter__(self) -> Self:
        await self._initialize()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # === Track Operations ===

    async def add_track(
        self,
        path: str,
        title: str | None = None,
        artist: str | None = None,
        album: str | None = None,
        duration: float = 0.0,
        source: str = "local",
        kind: str = "unknown",
    ) -> int:
        """Add a track to the library, returning its ID."""
        now = int(datetime.now().timestamp())
        cursor = await self._conn.execute(
            """
            INSERT INTO tracks (path, title, artist, album, duration, created_at, source, kind)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                title = COALESCE(excluded.title, title),
                artist = COALESCE(excluded.artist, artist),
                album = COALESCE(excluded.album, album),
                duration = COALESCE(excluded.duration, duration),
                source = excluded.source,
                kind = excluded.kind
            RETURNING id
            """,
            (path, title, artist, album, duration, now, source, kind),
        )
        row = await cursor.fetchone()
        await self._conn.commit()
        return row["id"]

    async def get_track(self, track_id: int) -> Track | None:
        """Get a track by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM tracks WHERE id = ?", (track_id,)
        )
        row = await cursor.fetchone()
        return Track.from_row(dict(row)) if row else None

    async def get_track_by_path(self, path: str) -> Track | None:
        """Get a track by path."""
        cursor = await self._conn.execute(
            "SELECT * FROM tracks WHERE path = ?", (path,)
        )
        row = await cursor.fetchone()
        return Track.from_row(dict(row)) if row else None

    async def get_all_tracks(self) -> list[Track]:
        """Get all tracks in the library."""
        rows = await self._fetch_all(
            "SELECT id, path, title, artist, album, duration, "
            "created_at, source, kind FROM tracks ORDER BY created_at DESC"
        )
        return [Track.from_row(row) for row in rows]

    async def search_tracks(self, query: str, limit: int = 50) -> list[Track]:
        """Search tracks by title, artist, or album."""
        pattern = f"%{query}%"
        cursor = await self._conn.execute(
            """
            SELECT * FROM tracks
            WHERE title LIKE ? OR artist LIKE ? OR album LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (pattern, pattern, pattern, limit),
        )
        rows = await cursor.fetchall()
        return [Track.from_row(dict(row)) for row in rows]

    async def delete_track(self, track_id: int) -> bool:
        """Delete a track from the library."""
        cursor = await self._conn.execute(
            "DELETE FROM tracks WHERE id = ?", (track_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # === Queue State Operations ===

    async def get_queue_state(self) -> QueueState:
        """Get the current queue state."""
        cursor = await self._conn.execute("SELECT * FROM queue_state WHERE id = 1")
        row = await cursor.fetchone()
        if row:
            return QueueState.from_row(dict(row))
        return QueueState()

    async def update_queue_state(
        self,
        current_track_id: int | None = None,
        current_position: int | None = None,
        playback_position: float | None = None,
        playback_status: str | None = None,
        volume: int | None = None,
        repeat_mode: str | None = None,
        shuffle_mode: bool | None = None,
    ) -> QueueState:
        """Update queue state fields."""
        now = int(datetime.now().timestamp())
        updates: list[str] = ["updated_at = ?"]
        values: list[Any] = [now]

        if current_track_id is not None:
            updates.append("current_track_id = ?")
            values.append(current_track_id)
        if current_position is not None:
            updates.append("current_position = ?")
            values.append(current_position)
        if playback_position is not None:
            updates.append("playback_position = ?")
            values.append(playback_position)
        if playback_status is not None:
            updates.append("playback_status = ?")
            values.append(playback_status)
        if volume is not None:
            updates.append("volume = ?")
            values.append(volume)
        if repeat_mode is not None:
            updates.append("repeat_mode = ?")
            values.append(repeat_mode)
        if shuffle_mode is not None:
            updates.append("shuffle_mode = ?")
            values.append(int(shuffle_mode))

        values.append(1)  # WHERE id = 1
        await self._conn.execute(
            f"UPDATE queue_state SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        await self._conn.commit()
        return await self.get_queue_state()

    # === Internal Helpers ===

    async def _execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a SQL statement and commit."""
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor

    async def _fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute a query and return all rows as dicts."""
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # === Queue Item Operations ===

    async def get_queue_items(self) -> list[QueueItem]:
        """Get all queue items ordered by position."""
        rows = await self._fetch_all(
            "SELECT id, track_id, position, added_at, source FROM queue_items ORDER BY position"
        )
        return [QueueItem.from_row(row) for row in rows]

    async def add_queue_item(
        self, track_id: int, position: int | None = None, source: str = "manual"
    ) -> int:
        """Add an item to the queue."""
        now = int(datetime.now().timestamp())
        if position is None:
            # Get max position + 1
            cursor = await self._conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 as next_pos FROM queue_items"
            )
            row = await cursor.fetchone()
            position = row["next_pos"]

        cursor = await self._conn.execute(
            """
            INSERT INTO queue_items (track_id, position, added_at, source)
            VALUES (?, ?, ?, ?)
            RETURNING id
            """,
            (track_id, position, now, source),
        )
        row = await cursor.fetchone()
        await self._conn.commit()
        return row["id"]

    async def add_queue_items(
        self, track_ids: list[int], start_position: int = 0
    ) -> list[QueueItem]:
        """Add multiple tracks to the queue at once."""
        items = []
        for i, track_id in enumerate(track_ids):
            position = start_position + i
            cursor = await self._execute(
                "INSERT INTO queue_items (track_id, position) VALUES (?, ?)",
                (track_id, position),
            )
            item_id = cursor.lastrowid
            items.append(QueueItem(id=item_id, track_id=track_id, position=position))
        return items

    async def update_queue_item_position(self, item_id: int, position: int) -> None:
        """Update the position of a queue item."""
        await self._execute(
            "UPDATE queue_items SET position = ? WHERE id = ?",
            (position, item_id),
        )

    async def remove_queue_item(self, item_id: int) -> None:
        """Remove a specific item from the queue."""
        await self._execute("DELETE FROM queue_items WHERE id = ?", (item_id,))

    async def remove_queue_item_by_position(self, position: int) -> bool:
        """Remove a queue item by position."""
        cursor = await self._conn.execute(
            "DELETE FROM queue_items WHERE position = ?", (position,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def clear_queue(self) -> None:
        """Clear all items from the queue."""
        await self._execute("DELETE FROM queue_items")

    async def reorder_queue(self, new_positions: dict[int, int]) -> None:
        """Reorder queue items. new_positions maps item_id -> new_position."""
        for item_id, new_pos in new_positions.items():
            await self._conn.execute(
                "UPDATE queue_items SET position = ? WHERE id = ?",
                (new_pos, item_id),
            )
        await self._conn.commit()

    # === History Operations ===

    async def add_history_entry(
        self,
        track_id: int | None,
        title_snapshot: str,
        artist_snapshot: str = "",
        source_snapshot: str = "",
        position: int = 0,
        completed: bool = False,
    ) -> int:
        """Add a play history entry."""
        now = int(datetime.now().timestamp())
        cursor = await self._conn.execute(
            """
            INSERT INTO history (
                track_id, played_at, position, completed,
                title_snapshot, artist_snapshot, source_snapshot
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                track_id, now, position, int(completed),
                title_snapshot, artist_snapshot, source_snapshot
            ),
        )
        row = await cursor.fetchone()
        await self._conn.commit()
        return row["id"]

    async def get_history(
        self, limit: int = 100, offset: int = 0
    ) -> list[HistoryEntry]:
        """Get play history with pagination."""
        cursor = await self._conn.execute(
            "SELECT * FROM history ORDER BY played_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [HistoryEntry.from_row(dict(row)) for row in rows]

    async def get_recent_history(self, limit: int = 20) -> list[HistoryEntry]:
        """Get recent play history."""
        return await self.get_history(limit)

    # === Playlist Operations ===

    async def create_playlist(
        self, name: str, description: str = ""
    ) -> int:
        """Create a new playlist."""
        now = int(datetime.now().timestamp())
        cursor = await self._conn.execute(
            """
            INSERT INTO playlists (name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            RETURNING id
            """,
            (name, description, now, now),
        )
        row = await cursor.fetchone()
        await self._conn.commit()
        return row["id"]

    async def get_playlist(self, playlist_id: int) -> Playlist | None:
        """Get a playlist by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM playlists WHERE id = ?", (playlist_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        playlist = Playlist.from_row(dict(row))

        # Get tracks
        cursor = await self._conn.execute(
            """
            SELECT t.* FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position ASC
            """,
            (playlist_id,),
        )
        track_rows = await cursor.fetchall()
        playlist.tracks = [Track.from_row(dict(r)) for r in track_rows]
        return playlist

    async def get_all_playlists(self) -> list[Playlist]:
        """Get all playlists."""
        rows = await self._fetch_all(
            "SELECT id, name, description, created_at, updated_at "
            "FROM playlists ORDER BY updated_at DESC"
        )
        playlists = []
        for row in rows:
            playlist = Playlist.from_row(row)
            # Load tracks
            track_rows = await self._fetch_all(
                "SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
                (playlist.id,),
            )
            for tr in track_rows:
                track = await self.get_track(tr["track_id"])
                if track:
                    playlist.tracks.append(track)
            playlists.append(playlist)
        return playlists

    async def add_track_to_playlist(
        self, playlist_id: int, track_id: int, position: int | None = None
    ) -> None:
        """Add a track to a playlist."""
        now = int(datetime.now().timestamp())
        if position is None:
            cursor = await self._conn.execute(
                """
                SELECT COALESCE(MAX(position), -1) + 1 as next_pos
                FROM playlist_tracks
                WHERE playlist_id = ?
                """,
                (playlist_id,),
            )
            row = await cursor.fetchone()
            position = row["next_pos"]

        await self._conn.execute(
            """
            INSERT OR REPLACE INTO playlist_tracks (playlist_id, track_id, position, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (playlist_id, track_id, position, now),
        )
        await self._conn.execute(
            "UPDATE playlists SET updated_at = ? WHERE id = ?",
            (now, playlist_id),
        )
        await self._conn.commit()

    async def update_playlist(
        self,
        playlist_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> bool:
        """Update playlist metadata."""
        if name is None and description is None:
            return True

        updates: list[str] = []
        values: list[Any] = []

        if name is not None:
            updates.append("name = ?")
            values.append(name)
        if description is not None:
            updates.append("description = ?")
            values.append(description)

        values.append(playlist_id)

        cursor = await self._conn.execute(
            f"UPDATE playlists SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def remove_track_from_playlist(self, playlist_id: int, track_id: int) -> bool:
        """Remove a track from a playlist."""
        cursor = await self._conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def delete_playlist(self, playlist_id: int) -> bool:
        """Delete a playlist."""
        cursor = await self._conn.execute(
            "DELETE FROM playlists WHERE id = ?", (playlist_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0


# Convenience function for getting the singleton
async def get_database() -> Database:
    """Get the database singleton instance."""
    return await Database.get_instance()
