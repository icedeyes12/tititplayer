"""
Modal dialogs for the TUI.

Provides:
- URL input dialog for streaming/YouTube URLs
- File browser for local music files
- Playlist management dialogs
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView

if TYPE_CHECKING:
    pass


class URLInputModal(ModalScreen[str | None]):
    """
    Modal dialog for entering streaming/YouTube URLs.

    Returns the URL string on success, None on cancel.
    """

    CSS = """
    URLInputModal {
        align: center middle;
    }

    #url-dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    #url-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #url-input {
        width: 1fr;
        margin-bottom: 1;
    }

    #url-buttons {
        align: center middle;
        height: 3;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="url-dialog"):
            yield Label("Enter URL (YouTube, Spotify, etc.)", id="url-title")
            yield Input(
                placeholder="https://music.youtube.com/watch?v=...",
                id="url-input",
            )
            with Horizontal(id="url-buttons"):
                yield Button("Import", variant="primary", id="import-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self) -> None:
        """Focus the input on mount."""
        self.query_one("#url-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "import-btn":
            self.action_submit()
        else:
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        self.action_submit()

    def action_submit(self) -> None:
        """Submit the URL."""
        url = self.query_one("#url-input", Input).value.strip()
        if url:
            self.dismiss(url)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)


class FileItem(ListItem):
    """A file or directory item in the file browser."""

    CSS = """
    FileItem {
        padding: 0 1;
    }

    .file-name {
        color: $text;
    }

    .directory-name {
        color: $accent;
        text-style: bold;
    }
    """

    def __init__(self, path: Path, is_dir: bool = False) -> None:
        super().__init__()
        self.path = path
        self.is_dir = is_dir

    def compose(self) -> ComposeResult:
        css_class = "directory-name" if self.is_dir else "file-name"
        icon = "📁" if self.is_dir else "🎵"
        yield Label(f"{icon} {self.path.name}", classes=css_class)


class FileBrowserModal(ModalScreen[Path | None]):
    """
    Modal dialog for browsing local files.

    Returns the selected file path on success, None on cancel.
    """

    CSS = """
    FileBrowserModal {
        align: center middle;
    }

    #browser-dialog {
        width: 80;
        height: 30;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    #browser-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #current-path {
        color: $text-muted;
        margin-bottom: 1;
        height: 1;
    }

    #file-list {
        height: 1fr;
        border: solid $surface-darken-1;
    }

    #browser-buttons {
        align: center middle;
        height: 3;
        margin-top: 1;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "select", "Select"),
        Binding("backspace", "parent_dir", "Up", show=False),
    ]

    def __init__(self, start_path: Path | None = None) -> None:
        super().__init__()
        self.current_path = start_path or Path.home()
        self.selected_path: Path | None = None

    def compose(self) -> ComposeResult:
        with Container(id="browser-dialog"):
            yield Label("Browse Music Files", id="browser-title")
            yield Label(str(self.current_path), id="current-path")
            yield ListView(id="file-list")
            with Horizontal(id="browser-buttons"):
                yield Button("Select", variant="primary", id="select-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    async def on_mount(self) -> None:
        """Load initial directory."""
        await self._load_directory()

    async def _load_directory(self) -> None:
        """Load the current directory contents."""
        file_list = self.query_one("#file-list", ListView)
        await file_list.clear()

        try:
            entries = sorted(
                self.current_path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )

            # Add parent directory option
            if self.current_path.parent != self.current_path:
                parent_item = FileItem(self.current_path.parent, is_dir=True)
                await file_list.append(parent_item)

            for entry in entries:
                if entry.is_dir() or entry.suffix.lower() in {
                    ".mp3",
                    ".flac",
                    ".wav",
                    ".ogg",
                    ".m4a",
                    ".aac",
                    ".opus",
                }:
                    item = FileItem(entry, is_dir=entry.is_dir())
                    await file_list.append(item)

        except PermissionError:
            pass

        # Update path display
        path_label = self.query_one("#current-path", Label)
        path_label.update(str(self.current_path))

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection."""
        item = event.item
        if isinstance(item, FileItem):
            if item.is_dir:
                self.current_path = item.path
                await self._load_directory()
            else:
                self.selected_path = item.path

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "select-btn":
            self.action_select()
        else:
            self.action_cancel()

    def action_select(self) -> None:
        """Select the current file."""
        if self.selected_path:
            self.dismiss(self.selected_path)
        else:
            # Try to get selected item from list
            file_list = self.query_one("#file-list", ListView)
            if file_list.index is not None and file_list.index < len(file_list.children):
                item = file_list.children[file_list.index]
                if isinstance(item, FileItem) and not item.is_dir:
                    self.dismiss(item.path)

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)

    def action_parent_dir(self) -> None:
        """Go to parent directory."""
        if self.current_path.parent != self.current_path:
            self.current_path = self.current_path.parent
            self._load_directory_sync()

    def _load_directory_sync(self) -> None:
        """Synchronously load directory (for key bindings)."""
        import asyncio

        asyncio.create_task(self._load_directory())


class PlaylistSelectModal(ModalScreen[int | None]):
    """
    Modal dialog for selecting a playlist.

    Returns the selected playlist ID on success, None on cancel.
    """

    CSS = """
    PlaylistSelectModal {
        align: center middle;
    }

    #playlist-dialog {
        width: 50;
        height: 20;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    #playlist-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #playlist-list {
        height: 1fr;
        border: solid $surface-darken-1;
    }

    #playlist-buttons {
        align: center middle;
        height: 3;
        margin-top: 1;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, playlists: list[dict]) -> None:
        super().__init__()
        self.playlists = playlists
        self.selected_id: int | None = None

    def compose(self) -> ComposeResult:
        with Container(id="playlist-dialog"):
            yield Label("Select Playlist", id="playlist-title")
            yield ListView(id="playlist-list")
            with Horizontal(id="playlist-buttons"):
                yield Button("Select", variant="primary", id="select-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    async def on_mount(self) -> None:
        """Load playlists."""
        playlist_list = self.query_one("#playlist-list", ListView)
        await playlist_list.clear()

        for pl in self.playlists:
            item = ListItem(Label(f"♫ {pl.get('name', 'Unknown')}"))
            item.playlist_id = pl.get("id")
            await playlist_list.append(item)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "select-btn":
            self.action_select()
        else:
            self.action_cancel()

    def action_select(self) -> None:
        """Select the current playlist."""
        playlist_list = self.query_one("#playlist-list", ListView)
        if playlist_list.index is not None:
            item = playlist_list.children[playlist_list.index]
            if hasattr(item, "playlist_id"):
                self.dismiss(item.playlist_id)
                return
        self.dismiss(None)

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)
