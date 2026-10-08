/** Adds the keyword (BM25) search table to a database created before it existed. Run once against the live database:
      npx wrangler d1 execute brain --remote --file=migrations/0003_lexical_search.sql
    (schema.sql already has this table for fresh installs.) The table starts empty; the next ingest run fills it,
    because the chunk settings version changed and every note is re-indexed. **/
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
