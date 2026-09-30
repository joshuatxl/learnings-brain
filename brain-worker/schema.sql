-- Episodic memory: one row per learning note (source of truth is the
-- markdown file in ../learnings/, identified by its repo path).
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  text TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL,
  consolidated INTEGER NOT NULL DEFAULT 0,
  -- Vectorize holds one vector per chunk, id "<entry id>:<n>". chunk_count is an
  -- upper bound on the n that may exist (0 = none yet). chunk_config records the
  -- chunking settings the note was last indexed with ('' = index missing or
  -- stale), so changing them triggers a re-embed.
  chunk_count INTEGER NOT NULL DEFAULT 0,
  chunk_config TEXT NOT NULL DEFAULT ''
);

-- Semantic memory: distilled, standalone facts with an optional topic tag.
-- id is a stable hash of the fact text so re-adding an identical fact
-- upserts instead of duplicating.
CREATE TABLE IF NOT EXISTS facts (
  id TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  topic TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',   -- active | superseded
  superseded_by TEXT,
  source_entry_ids TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);

-- Contradictions the summariser couldn't resolve on its own.
CREATE TABLE IF NOT EXISTS review_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  detail TEXT NOT NULL,
  fact_ids TEXT NOT NULL DEFAULT '',
  resolved INTEGER NOT NULL DEFAULT 0
);

-- Single-row lock so two Action runs can't consolidate at once.
CREATE TABLE IF NOT EXISTS consolidation_lock (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  running INTEGER NOT NULL DEFAULT 0,
  started_at TEXT
);
INSERT OR IGNORE INTO consolidation_lock (id, running) VALUES (1, 0);
