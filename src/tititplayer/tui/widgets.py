"""
Custom Textual widgets for the tititplayer TUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, ListItem, ListView, ProgressBar, Static


# ═══════════════════════════════════════════════════════════════════════════
# Track Item Widget
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class QueueTrack:
    """Data for a track in the queue."""
    id: int
    position: int
    title: str
    artist: str
    album: str
    duration: float
    is_current: bool = False
    
    @classmethod
    def from_api(cls, data: dict[str, Any], position: int, current_position: int | None = None) -> "QueueTrack":
        """Create from API response."""
        return cls(
            id=data.get("id", 0),
            position=position,
            title=data.get("title", "Unknown Title"),
            artist=data.get("artist", "Unknown Artist"),
            album=data.get("album", ""),
            duration=data.get("duration", 0.0),
            is_current=current_position is not None and position == current_position,
        )


class TrackListItem(ListItem):
    """A track item in the queue list."""
    
    track_data: reactive[QueueTrack | None] = reactive(None)
    
    def __init__(self, track: QueueTrack | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.track_data = track
    
    def compose(self) -> ComposeResult:
        if self.track_data:
            # Show current track with different style
            style = Style(bold=True, color="yellow") if self.track_data.is_current else Style()
            
            duration_str = self._format_duration(self.track_data.duration)
            track_text = f"{self.track_data.title}"
            if self.track_data.artist:
                track_text += f" — {self.track_data.artist}"
            
            yield Label(
                Text(f"{self.track_data.position + 1:3d}. {track_text}", style=style),
                classes="track-title"
            )
        else:
            yield Label("Empty", classes="track-title")
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as M:SS."""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}:{secs:02d}"
    
    def update_track(self, track: QueueTrack) -> None:
        """Update track data and refresh display."""
        self.track_data = track
        # Force re-compose
        self.remove_children()
        for child in self.compose():
            self.mount(child)


# ═══════════════════════════════════════════════════════════════════════════
# Now Playing Widget
# ═══════════════════════════════════════════════════════════════════════════

class NowPlayingWidget(Container):
    """Displays current track info and progress bar."""
    
    title: reactive[str] = reactive("Not Playing")
    artist: reactive[str] = reactive("")
    album: reactive[str] = reactive("")
    duration: reactive[float] = reactive(0.0)
    position: reactive[float] = reactive(0.0)
    status: reactive[str] = reactive("stopped")
    volume: reactive[int] = reactive(100)
    muted: reactive[bool] = reactive(False)
    repeat_mode: reactive[str] = reactive("none")
    shuffle_mode: reactive[bool] = reactive(False)
    
    def compose(self) -> ComposeResult:
        yield Label("♪ Now Playing", id="now-playing-header")
        yield Container(
            Label(self.title, id="track-title"),
            Label(self.artist or "—", id="track-artist"),
            Label(self.album or "—", id="track-album"),
            id="track-info"
        )
        yield Container(
            Label(self._format_time(self.position), id="position-label"),
            ProgressBar(total=100, id="progress-bar"),
            Label(self._format_time(self.duration), id="duration-label"),
            id="progress-container"
        )
        yield Container(
            Label(f"🔊 {self.volume}%", id="volume-display"),
            Label(self._status_text(), id="status-display"),
            Label(self._mode_text(), id="mode-display"),
            id="playback-info"
        )
    
    def _format_time(self, seconds: float) -> str:
        """Format time as M:SS or H:MM:SS."""
        if seconds <= 0:
            return "0:00"
        
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"
    
    def _status_text(self) -> str:
        """Get status display text."""
        if self.muted:
            return "🔇 Muted"
        
        status_map = {
            "playing": "▶ Playing",
            "paused": "⏸ Paused",
            "stopped": "⏹ Stopped",
        }
        return status_map.get(self.status, "⏹ Stopped")
    
    def _mode_text(self) -> str:
        """Get mode display text."""
        parts = []
        if self.shuffle_mode:
            parts.append("🔀 Shuffle")
        if self.repeat_mode == "single":
            parts.append("🔂 Single")
        elif self.repeat_mode == "all":
            parts.append("🔁 All")
        return " | ".join(parts) if parts else "—"
    
    def watch_position(self, position: float) -> None:
        """Update progress when position changes."""
        try:
            progress_bar = self.query_one("#progress-bar", ProgressBar)
            progress_bar.update(progress=int(position))
            
            position_label = self.query_one("#position-label", Label)
            position_label.update(self._format_time(position))
        except Exception:
            pass  # Widget not mounted yet
    
    def watch_duration(self, duration: float) -> None:
        """Update progress bar total when duration changes."""
        try:
            progress_bar = self.query_one("#progress-bar", ProgressBar)
            progress_bar.total = max(1, int(duration))
        except Exception:
            pass
    
    def watch_title(self, title: str) -> None:
        """Update title display."""
        try:
            label = self.query_one("#track-title", Label)
            label.update(title if title else "—")
        except Exception:
            pass
    
    def watch_artist(self, artist: str) -> None:
        """Update artist display."""
        try:
            label = self.query_one("#track-artist", Label)
            label.update(artist if artist else "—")
        except Exception:
            pass
    
    def watch_album(self, album: str) -> None:
        """Update album display."""
        try:
            label = self.query_one("#track-album", Label)
            label.update(album if album else "—")
        except Exception:
            pass
    
    def watch_volume(self, volume: int) -> None:
        """Update volume display."""
        try:
            label = self.query_one("#volume-display", Label)
            label.update(f"🔊 {volume}%")
        except Exception:
            pass
    
    def watch_muted(self, muted: bool) -> None:
        """Update status display when muted changes."""
        try:
            label = self.query_one("#status-display", Label)
            label.update(self._status_text())
        except Exception:
            pass
    
    def watch_status(self, status: str) -> None:
        """Update status display."""
        try:
            label = self.query_one("#status-display", Label)
            label.update(self._status_text())
        except Exception:
            pass
    
    def watch_repeat_mode(self, mode: str) -> None:
        """Update mode display."""
        try:
            label = self.query_one("#mode-display", Label)
            label.update(self._mode_text())
        except Exception:
            pass
    
    def watch_shuffle_mode(self, shuffle: bool) -> None:
        """Update mode display."""
        try:
            label = self.query_one("#mode-display", Label)
            label.update(self._mode_text())
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Queue List Widget
# ═══════════════════════════════════════════════════════════════════════════

class QueueListWidget(Container):
    """Queue list with navigation."""
    
    tracks: reactive[list[QueueTrack]] = reactive(list)
    current_position: reactive[int | None] = reactive(None)
    
    class TrackSelected(Message):
        """Emitted when a track is selected."""
        def __init__(self, position: int) -> None:
            super().__init__()
            self.position = position
    
    def compose(self) -> ComposeResult:
        yield Label("♫ Queue", id="queue-header")
        yield ListView(id="queue-list")
    
    def watch_tracks(self, tracks: list[QueueTrack]) -> None:
        """Update list when tracks change."""
        try:
            list_view = self.query_one("#queue-list", ListView)
            list_view.clear()
            
            for track in tracks:
                track.is_current = (self.current_position is not None and 
                                   track.position == self.current_position)
                list_view.append(TrackListItem(track))
        except Exception:
            pass
    
    def watch_current_position(self, position: int | None) -> None:
        """Highlight current track."""
        try:
            list_view = self.query_one("#queue-list", ListView)
            for i, item in enumerate(list_view.children):
                if isinstance(item, TrackListItem) and item.track_data:
                    item.track_data.is_current = (item.track_data.position == position)
                    item.update_track(item.track_data)
        except Exception:
            pass
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle track selection."""
        if isinstance(event.item, TrackListItem) and event.item.track_data:
            self.post_message(self.TrackSelected(event.item.track_data.position))


# ═══════════════════════════════════════════════════════════════════════════
# Connection Status Widget
# ═══════════════════════════════════════════════════════════════════════════

class ConnectionStatus(Static):
    """Displays daemon connection status."""
    
    connected: reactive[bool] = reactive(False)
    
    def compose(self) -> ComposeResult:
        yield Label(self._status_text(), id="connection-status-label")
    
    def _status_text(self) -> str:
        if self.connected:
            return "🟢 Daemon Online"
        return "🔴 Daemon Offline"
    
    def watch_connected(self, connected: bool) -> None:
        """Update status display."""
        try:
            label = self.query_one("#connection-status-label", Label)
            label.update(self._status_text())
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Key Bindings Footer
# ═══════════════════════════════════════════════════════════════════════════

class KeyBindingsFooter(Static):
    """Displays key bindings help."""
    
    def compose(self) -> ComposeResult:
        yield Label(
            "[Space] Play/Pause │ [j/k] Navigate │ [Ctrl+n/Ctrl+p] Next/Prev │ "
            "[+/-] Volume │ [s] Shuffle │ [r] Repeat │ [q] Quit",
            id="keybindings-label"
        )
