"""SQLite storage. One file, no server."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    post_id         TEXT PRIMARY KEY,
    subreddit       TEXT NOT NULL,
    created_utc     INTEGER NOT NULL,
    title           TEXT,
    selftext        TEXT,
    is_self         INTEGER,
    domain          TEXT,
    link_flair      TEXT,
    score           INTEGER,
    upvote_ratio    REAL,
    num_comments    INTEGER,
    edited          INTEGER,
    matched_terms   TEXT,
    filter_version  TEXT,
    first_seen_utc  INTEGER NOT NULL,
    last_synced_utc INTEGER NOT NULL,
    text_purged     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS posts_sub_time ON posts (subreddit, created_utc);
CREATE INDEX IF NOT EXISTS posts_sync ON posts (last_synced_utc);

-- One row per subreddit per collection run.
CREATE TABLE IF NOT EXISTS runs (
    run_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    subreddit          TEXT NOT NULL,
    mode               TEXT NOT NULL,     -- full or filtered
    filter_version     TEXT,
    started_utc        INTEGER NOT NULL,
    finished_utc       INTEGER,
    status             TEXT NOT NULL,     -- ok or error
    error              TEXT,
    watermark_utc      INTEGER,           -- newest post seen before this run
    oldest_scanned_utc INTEGER,
    newest_scanned_utc INTEGER,
    scanned            INTEGER DEFAULT 0, -- every post read, including overlap
    new_posts          INTEGER DEFAULT 0, -- rows added to posts
    excluded           TEXT,              -- JSON counts by reason
    backfill           INTEGER DEFAULT 0, -- first run for this subreddit
    gap                INTEGER DEFAULT 0  -- 1 if posts may have been missed
);

-- Posts seen per day, counted once each. The denominator for rates such as
-- the share of r/teenagers posts that mention screen time.
CREATE TABLE IF NOT EXISTS daily_counts (
    subreddit TEXT NOT NULL,
    day       TEXT NOT NULL,             -- UTC date, YYYY-MM-DD
    scanned   INTEGER NOT NULL DEFAULT 0,
    eligible  INTEGER NOT NULL DEFAULT 0, -- after exclusions
    kept      INTEGER NOT NULL DEFAULT 0, -- after topic filter
    complete  INTEGER NOT NULL DEFAULT 1, -- 0 if some posts that day were never seen
    PRIMARY KEY (subreddit, day)
);

-- Deletion and refresh activity, aggregate only.
CREATE TABLE IF NOT EXISTS sync_log (
    sync_utc  INTEGER NOT NULL,
    subreddit TEXT NOT NULL,
    checked   INTEGER NOT NULL,
    deleted   INTEGER NOT NULL,
    removed   INTEGER NOT NULL,
    missing   INTEGER NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA user_version = 1")
    return conn
