/** Episodic memory: one row per learning note (source of truth is the learnings/ folder, where episodic memory is derived from). **/
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  text TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL,
  consolidated INTEGER NOT NULL DEFAULT 0,
  /** Vectorize holds one vector per chunk; id "<entry id>:<n>". chunk_count is an upper bound on the n that may exist (0 = none yet).
      chunk_config records the chunking settings the note was last indexed with ('' = index missing or stale). Changing them triggers re-embedding. **/
  chunk_count INTEGER NOT NULL DEFAULT 0,
  chunk_config TEXT NOT NULL DEFAULT ''
);

/** Semantic memory: distilled and standalone facts with an optional topic tag. Re-adding an identical fact updates instead of duplicating. **/
CREATE TABLE IF NOT EXISTS facts (
  id TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  topic TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active', /**A note can be 'active' or 'superceded'**/
  superseded_by TEXT,
  source_entry_ids TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);

/**Contradictions that the summariser could not resolve on its own. **/
CREATE TABLE IF NOT EXISTS review_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  detail TEXT NOT NULL,
  fact_ids TEXT NOT NULL DEFAULT '',
  resolved INTEGER NOT NULL DEFAULT 0
);

/**Single-row lock so two GitHub Action runs cannot consolidate at once.**/
CREATE TABLE IF NOT EXISTS consolidation_lock (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  running INTEGER NOT NULL DEFAULT 0,
  started_at TEXT
);
INSERT OR IGNORE INTO consolidation_lock (id, running) VALUES (1, 0);

/** Keyword (BM25) search over note chunks: one row per chunk, with the same id as its Vectorize vector ("<entry id>:<n>").
    Only title, heading, context and text are searchable; the other columns just travel with the row.
    The porter tokenizer stems words, so "convolutions" also matches "convolution". **/
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  id UNINDEXED,
  entry_id UNINDEXED,
  created_at UNINDEXED,
  title,
  heading,
  context,
  text,
  tokenize = 'porter unicode61'
);
