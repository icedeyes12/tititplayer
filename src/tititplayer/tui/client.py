"""
HTTP client for communicating with the tititplayer daemon.

This is the ONLY way the TUI communicates with the backend.
No direct database or MPV access allowed.
"""

from __future__ import annotations

from typing import Any

import httpx

from tititplayer.config import API_BASE_URL


class APIClientError(Exception):
    """Base exception for API client errors."""
    pass


class APIClient:
    """
    Async HTTP client for the tititplayer API.

    All methods communicate via HTTP to localhost:8765/api/v1/
    """

    def __init__(self, base_url: str = API_BASE_URL, timeout: float = 5.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Make an HTTP request and return the JSON response."""
        if not self._client:
            raise APIClientError("Client not connected")

        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise APIClientError(f"HTTP {e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise APIClientError(f"Request failed: {e}") from e

    # ═══════════════════════════════════════════════════════════════════════
    # Status Endpoints
    # ═══════════════════════════════════════════════════════════════════════

    async def get_status(self) -> dict[str, Any]:
        """Get server status."""
        return await self._request("GET", "/api/v1/status")

    async def get_progress(self) -> dict[str, Any]:
        """Get playback progress."""
        return await self._request("GET", "/api/v1/status/progress")

    async def health_check(self) -> bool:
        """Check if daemon is healthy."""
        try:
            await self._request("GET", "/api/v1/status/health")
            return True
        except APIClientError:
            return False

    # ═══════════════════════════════════════════════════════════════════════
    # Playback Endpoints
    # ═══════════════════════════════════════════════════════════════════════

    async def get_playback_state(self) -> dict[str, Any]:
        """Get current playback state."""
        return await self._request("GET", "/api/v1/playback")

    async def play(self, track_id: int | None = None) -> dict[str, Any]:
        """Start playback, optionally with a specific track."""
        data = {"track_id": track_id} if track_id else {}
        return await self._request("POST", "/api/v1/playback/play", json=data)

    async def pause(self) -> dict[str, Any]:
        """Pause playback."""
        return await self._request("POST", "/api/v1/playback/pause")

    async def resume(self) -> dict[str, Any]:
        """Resume playback."""
        return await self._request("POST", "/api/v1/playback/resume")

    async def toggle_pause(self) -> dict[str, Any]:
        """Toggle play/pause."""
        return await self._request("POST", "/api/v1/playback/toggle")

    async def stop(self) -> dict[str, Any]:
        """Stop playback."""
        return await self._request("POST", "/api/v1/playback/stop")

    async def seek(self, position: float) -> dict[str, Any]:
        """Seek to position (seconds)."""
        return await self._request("POST", "/api/v1/playback/seek", json={"position": position})

    async def set_volume(self, volume: int) -> dict[str, Any]:
        """Set volume (0-100)."""
        return await self._request("POST", "/api/v1/playback/volume", json={"volume": volume})

    async def set_speed(self, speed: float) -> dict[str, Any]:
        """Set playback speed (0.25-4.0)."""
        return await self._request("POST", "/api/v1/playback/speed", json={"speed": speed})

    async def toggle_mute(self) -> dict[str, Any]:
        """Toggle mute."""
        return await self._request("POST", "/api/v1/playback/mute")

    async def set_repeat(self, mode: str) -> dict[str, Any]:
        """Set repeat mode (none, single, all)."""
        return await self._request("POST", "/api/v1/playback/repeat", json={"mode": mode})

    async def next_track(self) -> dict[str, Any]:
        """Go to next track."""
        return await self._request("POST", "/api/v1/playback/next")

    async def prev_track(self) -> dict[str, Any]:
        """Go to previous track."""
        return await self._request("POST", "/api/v1/playback/prev")

    # ═══════════════════════════════════════════════════════════════════════
    # Queue Endpoints
    # ═══════════════════════════════════════════════════════════════════════

    async def get_queue(self) -> dict[str, Any]:
        """Get current queue state."""
        return await self._request("GET", "/api/v1/queue")

    async def add_to_queue(
        self, track_ids: list[int], position: int | None = None
    ) -> dict[str, Any]:
        """Add tracks to queue."""
        data: dict[str, Any] = {"track_ids": track_ids}
        if position is not None:
            data["position"] = position
        return await self._request("POST", "/api/v1/queue/add", json=data)

    async def remove_from_queue(self, position: int) -> dict[str, Any]:
        """Remove track at position from queue."""
        return await self._request("POST", f"/api/v1/queue/remove/{position}")

    async def move_in_queue(self, old_position: int, new_position: int) -> dict[str, Any]:
        """Move track within queue."""
        return await self._request(
            "POST",
            "/api/v1/queue/move",
            json={"old_position": old_position, "new_position": new_position},
        )

    async def clear_queue(self) -> dict[str, Any]:
        """Clear the queue."""
        return await self._request("POST", "/api/v1/queue/clear")

    async def goto_position(self, position: int) -> dict[str, Any]:
        """Go to position in queue."""
        return await self._request("POST", "/api/v1/queue/goto", json={"position": position})

    async def toggle_shuffle(self) -> dict[str, Any]:
        """Toggle shuffle mode."""
        return await self._request("POST", "/api/v1/queue/shuffle")

    async def cycle_repeat(self) -> dict[str, Any]:
        """Cycle repeat mode."""
        return await self._request("POST", "/api/v1/queue/repeat")

    async def get_queue_item(self, position: int) -> dict[str, Any]:
        """Get queue item at position."""
        return await self._request("GET", f"/api/v1/queue/{position}")

    # ═══════════════════════════════════════════════════════════════════════
    # Tracks Endpoints
    # ═══════════════════════════════════════════════════════════════════════

    async def get_tracks(
        self,
        search: str | None = None,
        artist: str | None = None,
        album: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search/list tracks."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if search:
            params["search"] = search
        if artist:
            params["artist"] = artist
        if album:
            params["album"] = album
        return await self._request("GET", "/api/v1/tracks", params=params)

    async def get_track(self, track_id: int) -> dict[str, Any]:
        """Get track by ID."""
        return await self._request("GET", f"/api/v1/tracks/{track_id}")

    # ═══════════════════════════════════════════════════════════════════════
    # Playlists Endpoints
    # ═══════════════════════════════════════════════════════════════════════

    async def get_playlists(self) -> dict[str, Any]:
        """Get all playlists."""
        return await self._request("GET", "/api/v1/playlists")

    async def get_playlist(self, playlist_id: int) -> dict[str, Any]:
        """Get playlist by ID."""
        return await self._request("GET", f"/api/v1/playlists/{playlist_id}")

    async def play_playlist(self, playlist_id: int) -> dict[str, Any]:
        """Play a playlist."""
        return await self._request("POST", f"/api/v1/playlists/{playlist_id}/play")


# Singleton client instance
_client: APIClient | None = None


async def get_client() -> APIClient:
    """Get the API client singleton."""
    global _client
    if _client is None:
        _client = APIClient()
        await _client.connect()
    return _client


async def close_client() -> None:
    """Close the API client singleton."""
    global _client
    if _client:
        await _client.disconnect()
        _client = None
