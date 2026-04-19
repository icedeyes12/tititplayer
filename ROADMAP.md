# Tititplayer Roadmap

## v0.2.0 - Current Sprint

### Features to Add:

#### 1. Transparent Background (Termux-friendly)
- [ ] Remove hardcoded background colors
- [ ] Use transparent/system colors

#### 2. File/URL Input
- [ ] Add file browser widget
- [ ] Support direct URL input (YouTube, YT Music, etc.)
- [ ] Drag-and-drop support (if terminal supports it)

#### 3. M3U Playlist Support
- [ ] Parse m3u/m3u8 files
- [ ] Import to database
- [ ] Export playlists to m3u

#### 4. Playlist Management in TUI
- [ ] Create new playlists
- [ ] Add tracks to playlists
- [ ] Remove tracks from playlists
- [ ] Delete playlists

#### 5. YouTube Music Integration
- [ ] Extract metadata via yt-dlp
- [ ] Support YT Music URLs directly
- [ ] Import YT Music playlists
- [ ] Cache metadata locally

## Architecture Notes

### MPV Already Supports:
- YouTube URLs (via yt-dlp)
- Metadata extraction
- Streaming without download

### What We Need:
1. URL input interface (not just local files)
2. Metadata extraction before adding to DB
3. M3U parser
4. Playlist management UI

## Implementation Priority

1. **Transparent background** - Quick fix
2. **URL input** - Add command to add by URL
3. **M3U import** - Parse and import
4. **Playlist UI** - Create/manage playlists
5. **YT metadata** - Extract via yt-dlp
