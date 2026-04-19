-- Tititplayer Database Schema
-- SQLite 3.x with async access via aiosqlite

-- Music library tracks
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    title TEXT,
    artist TEXT,
    album TEXT,
    duration REAL DEFAULT 0,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    source TEXT NOT NULL DEFAULT 'local',
    kind TEXT NOT NULL DEFAULT 'unknown'
);

-- User-created playlists
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

-- Playlist-track junction (many-to-many with position)
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL,
    track_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    added_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (playlist_id, track_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
);

-- Play history (snapshots handle deleted tracks)
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    played_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    position INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 0,
    title_snapshot TEXT NOT NULL DEFAULT '',
    artist_snapshot TEXT NOT NULL DEFAULT '',
    source_snapshot TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE SET NULL
);

-- Queue items (current session playlist)
CREATE TABLE IF NOT EXISTS queue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    added_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    source TEXT NOT NULL DEFAULT 'manual',
    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
);

-- Persistent Queue State (Singleton)
CREATE TABLE IF NOT EXISTS queue_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_track_id INTEGER,
    current_position INTEGER DEFAULT 0,
    playback_position REAL DEFAULT 0.0,
    playback_status TEXT DEFAULT 'stopped',
    volume INTEGER DEFAULT 100,
    repeat_mode TEXT DEFAULT 'none',
    shuffle_mode INTEGER DEFAULT 0,
    updated_at INTEGER DEFAULT (strftime('%s','now')),
    FOREIGN KEY(current_track_id) REFERENCES tracks(id) ON DELETE SET NULL
);

-- Initialize queue_state singleton row
INSERT OR IGNORE INTO queue_state (id) VALUES (1);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist);
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album);
CREATE INDEX IF NOT EXISTS idx_history_played_at ON history(played_at DESC);
CREATE INDEX IF NOT EXISTS idx_queue_items_position ON queue_items(position);
