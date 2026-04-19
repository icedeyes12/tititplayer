"""
Main Textual TUI application for tititplayer.

This is a strict HTTP client that communicates exclusively with the daemon
via the REST API. No direct database or MPV access.
"""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Label

from tititplayer.tui.client import APIClient, APIClientError, close_client, get_client
from tititplayer.tui.widgets import (
    ConnectionStatus,
    KeyBindingsFooter,
    NowPlayingWidget,
    QueueListWidget,
    QueueTrack,
)


class TititApp(App):
    """
    Tititplayer TUI - Terminal music player interface.

    Communicates with the daemon via HTTP API.
    """

    CSS = """
    /* Main layout */
    Screen {
        layout: vertical;
        background: transparent;
    }

    #main-header {
        height: 2;
        dock: top;
        background: $primary;
        padding: 0 1;
        layout: horizontal;
    }

    #app-title {
        color: $text-primary;
        content-align: left middle;
        text-style: bold;
    }

    #connection-status-label {
        color: $text-primary;
        content-align: right middle;
    }

    #connection-status {
        text-align: right;
    }

    #main-content {
        layout: horizontal;
        height: 1fr;
    }

    #queue-panel {
        width: 1fr;
        border-right: solid $primary;
        layout: vertical;
    }

    #now-playing-panel {
        width: 1fr;
        layout: vertical;
    }

    #queue-header {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
        content-align: center middle;
        text-style: bold;
    }

    #queue-list {
        height: 1fr;
        padding: 0;
    }

    .track-title {
        padding: 0 1;
    }

    #now-playing-header {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
        content-align: center middle;
        text-style: bold;
    }

    #track-info {
        height: auto;
        padding: 1;
        layout: vertical;
    }

    #track-title {
        color: $text;
        text-style: bold;
        margin-bottom: 1;
    }

    #track-artist {
        color: $text-muted;
    }

    #track-album {
        color: $text-muted;
    }

    #progress-container {
        height: 2;
        layout: horizontal;
        padding: 0 1;
        align: center middle;
    }

    #position-label, #duration-label {
        width: 6;
        color: $text-muted;
        content-align: center middle;
    }

    #progress-bar {
        width: 1fr;
    }

    #playback-info {
        height: auto;
        layout: horizontal;
        padding: 1;
    }

    #volume-display {
        color: $text;
    }

    #status-display {
        width: 1fr;
        color: $accent;
        content-align: center middle;
    }

    #mode-display {
        color: $text-muted;
    }

    #keybindings-label {
        height: 1;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 1;
        content-align: center middle;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_pause", "Play/Pause"),
        Binding("j", "navigate_down", "Down"),
        Binding("k", "navigate_up", "Up"),
        Binding("ctrl+n", "next_track", "Next"),
        Binding("ctrl+p", "prev_track", "Prev"),
        Binding("bracketright", "next_track_alt", "Next", show=False),
        Binding("bracketleft", "prev_track_alt", "Prev", show=False),
        Binding("plus,equal", "volume_up", "Vol+"),
        Binding("minus,underscore", "volume_down", "Vol-"),
        Binding("s", "toggle_shuffle", "Shuffle"),
        Binding("r", "cycle_repeat", "Repeat"),
        Binding("enter", "play_selected", "Play"),
        Binding("u", "import_url", "URL"),
        Binding("f", "browse_files", "Files"),
        Binding("p", "select_playlist", "Playlist"),
        Binding("q", "quit", "Quit"),
    ]

    daemon_connected: bool = False
    current_position: int | None = None

    def __init__(self) -> None:
        super().__init__()
        self._client: APIClient | None = None
        self._poll_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        with Container(id="main-header"):
            yield Label("♪ tititplayer", id="app-title")
            yield ConnectionStatus(id="connection-status")

        with Container(id="main-content"):
            with Container(id="queue-panel"):
                yield QueueListWidget()

            with Container(id="now-playing-panel"):
                yield NowPlayingWidget()

        yield KeyBindingsFooter()

    async def on_mount(self) -> None:
        """Initialize when app mounts."""
        await self._connect_client()
        self._start_polling()

    async def on_unmount(self) -> None:
        """Cleanup when app unmounts."""
        self._stop_polling()
        await close_client()

    async def _connect_client(self) -> None:
        """Connect to the API daemon."""
        try:
            self._client = await get_client()
            if await self._client.health_check():
                self.daemon_connected = True
                self._update_connection_status(True)
            else:
                self.daemon_connected = False
                self._update_connection_status(False)
        except Exception:
            self.daemon_connected = False
            self._update_connection_status(False)

    def _update_connection_status(self, connected: bool) -> None:
        """Update connection status widget."""
        try:
            status_widget = self.query_one("#connection-status", ConnectionStatus)
            status_widget.connected = connected
        except Exception:
            pass

    def _start_polling(self) -> None:
        """Start periodic polling."""
        self._poll_task = asyncio.create_task(self._poll_loop())

    def _stop_polling(self) -> None:
        """Stop polling."""
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

    async def _poll_loop(self) -> None:
        """Poll daemon for updates every second."""
        while True:
            try:
                await self._poll_status()
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(2.0)

    async def _poll_status(self) -> None:
        """Poll status and progress endpoints."""
        if not self._client:
            return

        try:
            if not await self._client.health_check():
                self.daemon_connected = False
                self._update_connection_status(False)
                return

            self.daemon_connected = True
            self._update_connection_status(True)

            playback = await self._client.get_playback_state()
            self._update_now_playing(playback)

            queue = await self._client.get_queue()
            self._update_queue(queue)

        except APIClientError:
            self.daemon_connected = False
            self._update_connection_status(False)

    def _update_now_playing(self, playback: dict[str, Any]) -> None:
        """Update now playing widget."""
        try:
            now_playing = self.query_one(NowPlayingWidget)

            if playback.get("current_track"):
                track = playback["current_track"]
                now_playing.title = track.get("title", "Unknown")
                now_playing.artist = track.get("artist", "")
                now_playing.album = track.get("album", "")
                now_playing.duration = track.get("duration", 0.0)
            else:
                now_playing.title = "Not Playing"
                now_playing.artist = ""
                now_playing.album = ""
                now_playing.duration = 0.0

            now_playing.position = playback.get("position", 0.0)
            now_playing.status = playback.get("status", "stopped")
            now_playing.volume = playback.get("volume", 100)
            now_playing.muted = playback.get("muted", False)
            now_playing.repeat_mode = playback.get("repeat_mode", "none")
            now_playing.shuffle_mode = playback.get("shuffle_mode", False)

            self.current_position = playback.get("queue_position")

        except Exception:
            pass

    def _update_queue(self, queue: dict[str, Any]) -> None:
        """Update queue list."""
        try:
            queue_widget = self.query_one(QueueListWidget)

            items = queue.get("items", [])
            tracks = []

            for i, item in enumerate(items):
                track = item.get("track", {})
                tracks.append(
                    QueueTrack.from_api(
                        track, position=i, current_position=self.current_position
                    )
                )

            queue_widget.tracks = tracks
            queue_widget.current_position = self.current_position

        except Exception:
            pass

    async def action_toggle_pause(self) -> None:
        """Toggle play/pause."""
        if self._client:
            try:
                await self._client.toggle_pause()
            except APIClientError:
                pass

    async def action_navigate_down(self) -> None:
        """Navigate down in queue."""
        try:
            queue_widget = self.query_one(QueueListWidget)
            queue_list = queue_widget.query_one("#queue-list")
            queue_list.action_cursor_down()
        except Exception:
            pass

    async def action_navigate_up(self) -> None:
        """Navigate up in queue."""
        try:
            queue_widget = self.query_one(QueueListWidget)
            queue_list = queue_widget.query_one("#queue-list")
            queue_list.action_cursor_up()
        except Exception:
            pass

    async def action_next_track(self) -> None:
        """Next track."""
        if self._client:
            try:
                await self._client.next_track()
            except APIClientError:
                pass

    async def action_prev_track(self) -> None:
        """Previous track."""
        if self._client:
            try:
                await self._client.prev_track()
            except APIClientError:
                pass

    async def action_next_track_alt(self) -> None:
        """Alternative next track binding (])."""
        await self.action_next_track()

    async def action_prev_track_alt(self) -> None:
        """Alternative prev track binding ([)."""
        await self.action_prev_track()

    async def action_volume_up(self) -> None:
        """Increase volume by 5."""
        if self._client:
            try:
                playback = await self._client.get_playback_state()
                current = playback.get("volume", 100)
                new_volume = min(100, current + 5)
                await self._client.set_volume(new_volume)
            except APIClientError:
                pass

    async def action_volume_down(self) -> None:
        """Decrease volume by 5."""
        if self._client:
            try:
                playback = await self._client.get_playback_state()
                current = playback.get("volume", 100)
                new_volume = max(0, current - 5)
                await self._client.set_volume(new_volume)
            except APIClientError:
                pass

    async def action_toggle_shuffle(self) -> None:
        """Toggle shuffle mode."""
        if self._client:
            try:
                await self._client.toggle_shuffle()
            except APIClientError:
                pass

    async def action_cycle_repeat(self) -> None:
        """Cycle repeat mode."""
        if self._client:
            try:
                await self._client.cycle_repeat()
            except APIClientError:
                pass

    async def action_play_selected(self) -> None:
        """Play selected track in queue."""
        if self._client:
            try:
                queue_widget = self.query_one(QueueListWidget)
                queue_list = queue_widget.query_one("#queue-list")

                if queue_list.index is not None:
                    await self._client.goto_position(queue_list.index)
            except APIClientError:
                pass

    async def action_import_url(self) -> None:
        """Open URL import dialog."""
        from tititplayer.tui.dialogs import URLInputModal

        url = await self.push_screen_wait(URLInputModal())
        if url and self._client:
            try:
                # Import via API
                result = await self._client._request(
                    "POST", "/api/v1/tracks/import/url", json={"url": url}
                )
                # Add to queue
                if result.get("track_id"):
                    await self._client.add_to_queue([result["track_id"]])
            except APIClientError:
                pass

    async def action_browse_files(self) -> None:
        """Open file browser dialog."""

        from tititplayer.tui.dialogs import FileBrowserModal

        selected_path = await self.push_screen_wait(FileBrowserModal())
        if selected_path and self._client:
            try:
                # Import via API
                result = await self._client._request(
                    "POST",
                    "/api/v1/tracks/import/m3u",
                    json={"path": str(selected_path), "create_playlist": False},
                )
                # Add tracks to queue
                track_ids = result.get("track_ids", [])
                if track_ids:
                    await self._client.add_to_queue(track_ids)
            except APIClientError:
                pass

    async def action_select_playlist(self) -> None:
        """Open playlist selection dialog."""
        from tititplayer.tui.dialogs import PlaylistSelectModal

        if not self._client:
            return

        try:
            # Get playlists
            result = await self._client._request("GET", "/api/v1/playlists")
            playlists = result.get("playlists", [])

            if not playlists:
                return

            playlist_id = await self.push_screen_wait(PlaylistSelectModal(playlists))
            if playlist_id:
                # Play the playlist
                await self._client._request(
                    "POST", f"/api/v1/playlists/{playlist_id}/play"
                )
        except APIClientError:
            pass

    def action_quit(self) -> None:
        """Quit the TUI (daemon keeps running)."""
        self.exit()

    async def on_queue_list_widget_track_selected(
        self, event: QueueListWidget.TrackSelected
    ) -> None:
        """Handle track selection in queue."""
        if self._client:
            try:
                await self._client.goto_position(event.position)
            except APIClientError:
                pass


def run_tui() -> None:
    """Entry point for running the TUI."""
    app = TititApp()
    app.run()


if __name__ == "__main__":
    run_tui()
