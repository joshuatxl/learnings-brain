"""Central configuration. Secrets come from the environment only, nothing is stored here.
GitHub Action injects them from encrypted repo secrets."""
from __future__ import annotations

import os

LEARNINGS_DIR = "learnings"

CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
D1_DATABASE_ID = os.environ.get("D1_DATABASE_ID", "")

FACTS_INDEX = "brain-facts"
EPISODES_INDEX = "brain-episodes"
EMBED_MODEL = "@cf/baai/bge-small-en-v1.5"
EMBED_BATCH = 32  # texts per Workers AI call

# Notes are split into chunks before embedding (see chunking.py). CHUNK_CONFIG
# is stored per note, so changing any of these re-embeds every note on the next
# sync without re-running consolidation. Bump the version when the splitting
# logic itself changes.
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
CHUNK_CONFIG = f"md-recursive-v3-llm-context-keyword:{CHUNK_SIZE}:{CHUNK_OVERLAP}"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUMMARY_MODEL = "gemini-3.6-flash"

# Consolidate once this many learnings are pending (also run unconditionally
# on the daily scheduled workflow run, see --force in sync.py).
CONSOLIDATE_AFTER = 5
FACT_SEARCH_K = 5
