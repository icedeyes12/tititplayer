"""
Async MPV IPC client for controlling MPV via Unix socket.

MPV uses JSON IPC protocol:
- Commands: {"command": ["cmd", "arg1", ...], "request_id": int}
- Responses: {"request_id": int, "data": ..., "error": "success"}
- Events: {"event": "property-change", "name": "...", "data": ...}
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from tititplayer.config import MPV_SOCKET_PATH


class MPVEventType(StrEnum):
    """MPV event types."""

    PROPERTY_CHANGE = "property-change"
    SEEK = "seek"
    END_FILE = "end-file"
    START_FILE = "start-file"
    PAUSE = "pause"
    UNPAUSE = "unpause"
    SHUTDOWN = "shutdown"
    LOG_MESSAGE = "log-message"


@dataclass
class MPVEvent:
    """An event from MPV."""

    event: str
    name: str | None = None
    data: Any = None
    id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            event=data.get("event", ""),
            name=data.get("name"),
            data=data.get("data"),
            id=data.get("id"),
        )


@dataclass
class MPVResponse:
    """A response to a command."""

    request_id: int
    data: Any = None
    error: str = "success"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            request_id=data.get("request_id", 0),
            data=data.get("data"),
            error=data.get("error", "success"),
        )


@dataclass
class MPVState:
    """Current MPV playback state."""

    filename: str = ""
    path: str = ""
    time_pos: float = 0.0
    duration: float = 0.0
    volume: int = 100
    pause: bool = True
    speed: float = 1.0
    mute: bool = False


# Property observers we want to track
OBSERVED_PROPERTIES: list[tuple[str, str | None]] = [
    ("filename", "no"),  # Current filename
    ("path", None),  # Full path
    ("time-pos", None),  # Current position in seconds
    ("duration", None),  # Total duration
    ("volume", None),  # Volume (0-100)
    ("pause", None),  # Paused state
    ("speed", None),  # Playback speed
    ("mute", None),  # Mute state
]


class MPVClient:
    """
    Async MPV IPC client for controlling MPV via Unix socket.

    Provides high-level methods for playback control and
    maintains an up-to-date state via property observation.
    """

    def __init__(self, socket_path: Path = MPV_SOCKET_PATH) -> None:
        self._socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id = 0
        self._pending_requests: dict[int, asyncio.Future[MPVResponse]] = {}
        self._event_callbacks: list[Callable[[MPVEvent], None]] = []
        self._state = MPVState()
        self._receive_task: asyncio.Task[None] | None = None
        self._running = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> MPVState:
        """Get the current MPV state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if connected to MPV."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Connect to MPV's Unix socket."""
        if self.is_connected:
            return

        try:
            self._reader, self._writer = await asyncio.open_unix_connection(
                str(self._socket_path)
            )
        except FileNotFoundError:
            raise ConnectionError(
                f"MPV socket not found at {self._socket_path}. "
                "Ensure MPV is running with --input-ipc-server={socket}"
            )
        except ConnectionRefusedError:
            raise ConnectionError(
                f"Could not connect to MPV socket at {self._socket_path}"
            )

        self._running = True
        self._receive_task = asyncio.create_task(self._receive_loop())

        # Observe properties
        await self._observe_properties()

    async def disconnect(self) -> None:
        """Disconnect from MPV."""
        self._running = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

        # Cancel pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

    async def _observe_properties(self) -> None:
        """Set up property observation for state tracking."""
        for prop, default in OBSERVED_PROPERTIES:
            await self._send_command("observe_property", self._request_id, prop)
            self._request_id += 1

    def _get_next_request_id(self) -> int:
        """Get the next request ID."""
        self._request_id += 1
        return self._request_id

    async def _send_command(self, *args: Any) -> MPVResponse:
        """
        Send a command to MPV and wait for the response.

        Args:
            *args: Command name followed by arguments

        Returns:
            MPVResponse with the result
        """
        if not self._writer:
            raise ConnectionError("Not connected to MPV")

        request_id = self._get_next_request_id()
        command = {"command": list(args), "request_id": request_id}

        # Create future for response
        future: asyncio.Future[MPVResponse] = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            # Send command
            data = json.dumps(command) + "\n"
            self._writer.write(data.encode())
            await self._writer.drain()

            # Wait for response
            return await asyncio.wait_for(future, timeout=10.0)

        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"MPV command timed out: {args[0]}")
        except Exception:
            self._pending_requests.pop(request_id, None)
            raise

    async def _receive_loop(self) -> None:
        """Background task to receive messages from MPV."""
        while self._running and self._reader:
            try:
                line = await self._reader.readline()
                if not line:
                    # Connection closed
                    break

                message = json.loads(line.decode())

                # Check if it's a response to a request
                if "request_id" in message:
                    response = MPVResponse.from_dict(message)
                    future = self._pending_requests.pop(response.request_id, None)
                    if future and not future.done():
                        future.set_result(response)

                # Check if it's an event
                elif "event" in message:
                    event = MPVEvent.from_dict(message)
                    await self._handle_event(event)

            except asyncio.CancelledError:
                break
            except json.JSONDecodeError:
                continue  # Ignore malformed messages
            except Exception:
                # Log but continue
                continue

    async def _handle_event(self, event: MPVEvent) -> None:
        """Handle an MPV event."""
        # Update state for property changes
        if event.event == MPVEventType.PROPERTY_CHANGE:
            if event.name == "filename":
                self._state.filename = event.data or ""
            elif event.name == "path":
                self._state.path = event.data or ""
            elif event.name == "time-pos":
                self._state.time_pos = event.data or 0.0
            elif event.name == "duration":
                self._state.duration = event.data or 0.0
            elif event.name == "volume":
                self._state.volume = int(event.data or 100)
            elif event.name == "pause":
                self._state.pause = bool(event.data)
            elif event.name == "speed":
                self._state.speed = event.data or 1.0
            elif event.name == "mute":
                self._state.mute = bool(event.data)

        # Notify callbacks
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception:
                pass  # Ignore callback errors

    def add_event_callback(self, callback: Callable[[MPVEvent], None]) -> None:
        """Add a callback to be called when MPV events occur."""
        self._event_callbacks.append(callback)

    def remove_event_callback(self, callback: Callable[[MPVEvent], None]) -> None:
        """Remove an event callback."""
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)

    # === High-level Playback Control ===

    async def play(self, path: str) -> None:
        """
        Play a file.

        Args:
            path: Path to the audio file
        """
        await self._send_command("loadfile", path, "replace")
        self._state.path = path

    async def append_to_playlist(self, path: str) -> None:
        """Append a file to the playlist."""
        await self._send_command("loadfile", path, "append")

    async def pause(self) -> None:
        """Pause playback."""
        await self._send_command("set_property", "pause", True)
        self._state.pause = True

    async def unpause(self) -> None:
        """Resume playback."""
        await self._send_command("set_property", "pause", False)
        self._state.pause = False

    async def toggle_pause(self) -> bool:
        """
        Toggle pause state.

        Returns:
            New pause state (True = paused)
        """
        new_pause = not self._state.pause
        await self._send_command("set_property", "pause", new_pause)
        self._state.pause = new_pause
        return new_pause

    async def stop(self) -> None:
        """Stop playback and clear the playlist."""
        await self._send_command("stop")

    async def seek(self, position: float, absolute: bool = True) -> None:
        """
        Seek to a position.

        Args:
            position: Position in seconds
            absolute: If True, seek to absolute position; else relative
        """
        mode = "absolute" if absolute else "relative"
        await self._send_command("seek", position, mode)
        self._state.time_pos = position

    async def seek_relative(self, seconds: float) -> None:
        """
        Seek relative to current position.

        Args:
            seconds: Seconds to seek (positive = forward, negative = backward)
        """
        await self._send_command("seek", seconds, "relative")

    async def set_volume(self, volume: int) -> None:
        """
        Set volume.

        Args:
            volume: Volume level (0-100+)
        """
        volume = max(0, min(130, volume))  # MPV allows up to 130%
        await self._send_command("set_property", "volume", volume)
        self._state.volume = volume

    async def get_volume(self) -> int:
        """Get current volume."""
        response = await self._send_command("get_property", "volume")
        if response.error == "success":
            return int(response.data or 100)
        return self._state.volume

    async def get_time_pos(self) -> float:
        """Get current playback position in seconds."""
        response = await self._send_command("get_property", "time-pos")
        if response.error == "success" and response.data is not None:
            self._state.time_pos = response.data
        return self._state.time_pos

    async def get_duration(self) -> float:
        """Get total duration in seconds."""
        response = await self._send_command("get_property", "duration")
        if response.error == "success" and response.data is not None:
            self._state.duration = response.data
        return self._state.duration

    async def set_speed(self, speed: float) -> None:
        """
        Set playback speed.

        Args:
            speed: Speed multiplier (0.25 - 4.0)
        """
        speed = max(0.25, min(4.0, speed))
        await self._send_command("set_property", "speed", speed)
        self._state.speed = speed

    async def mute(self, mute: bool = True) -> None:
        """Set mute state."""
        await self._send_command("set_property", "mute", mute)
        self._state.mute = mute

    async def toggle_mute(self) -> bool:
        """Toggle mute state."""
        new_mute = not self._state.mute
        await self.mute(new_mute)
        return new_mute

    # === Playlist Control ===

    async def playlist_next(self) -> None:
        """Play next item in playlist."""
        await self._send_command("playlist-next")

    async def playlist_prev(self) -> None:
        """Play previous item in playlist."""
        await self._send_command("playlist-prev")

    async def playlist_clear(self) -> None:
        """Clear the playlist (except current item)."""
        await self._send_command("playlist-clear")

    async def playlist_remove(self, index: int) -> None:
        """Remove item at index from playlist."""
        await self._send_command("playlist-remove", index)

    async def playlist_move(self, from_index: int, to_index: int) -> None:
        """Move playlist item from one position to another."""
        await self._send_command("playlist-move", from_index, to_index)

    async def playlist_shuffle(self) -> None:
        """Shuffle the playlist."""
        await self._send_command("playlist-shuffle")

    async def get_playlist_count(self) -> int:
        """Get number of items in playlist."""
        response = await self._send_command("get_property", "playlist-count")
        if response.error == "success":
            return int(response.data or 0)
        return 0

    async def get_playlist_current_pos(self) -> int:
        """Get current playlist position."""
        response = await self._send_command("get_property", "playlist-playing-pos")
        if response.error == "success":
            return int(response.data or -1)
        return -1

    # === Context Manager Support ===

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()
