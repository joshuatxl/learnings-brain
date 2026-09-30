-- Adds chunking bookkeeping to an entries table created from the original
-- schema.sql. Run once against the live database:
--   npx wrangler d1 execute brain --remote --file=migrations/0002_chunking.sql
-- (schema.sql already has these columns for fresh installs.)
ALTER TABLE entries ADD COLUMN chunk_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE entries ADD COLUMN chunk_config TEXT NOT NULL DEFAULT '';
