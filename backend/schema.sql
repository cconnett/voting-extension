CREATE TABLE polls (
    id TEXT PRIMARY KEY,
    salt INTEGER,
    channel_id TEXT NOT NULL,
    title TEXT,
    candidates TEXT NOT NULL,  -- JSON array
    open INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE ballots (
    poll_id INTEGER NOT NULL REFERENCES polls(id),
    opaque_user_id TEXT NOT NULL,
    ranking TEXT NOT NULL, -- flat JSON array of ranked candidates
    cast_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (poll_id, opaque_user_id)
) WITHOUT ROWID;
PRAGMA journal_mode=WAL;
