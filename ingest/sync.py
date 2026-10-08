"""Diff learnings/*.md against the entries table in D1 and resolve differences. Each
note is stored in Vectorize as chunks (chunking.py), and in D1's chunks_fts table for keyword search. Notes  are (re)chunked and re-embedded
when it is new, when its text changed, or when CHUNK_CONFIG differs from the one it was last
indexed with. Deleted files are removed from D1 and Vectorize."""
from __future__ import annotations

from . import cloudflare as cf
from . import context as ctx
from .chunking import chunk_note, embed_text
from .config import CHUNK_CONFIG, EPISODES_INDEX
from .notes import Note, load_notes


def _existing() -> dict[str, dict]:
    rows = cf.d1_query("SELECT id, path, content_hash, chunk_count, chunk_config FROM entries")
    return {r["path"]: r for r in rows}


def _chunk_ids(entry_id: int, start: int, stop: int) -> list[str]:
    return [f"{entry_id}:{i}" for i in range(start, stop)]


_FTS_COLUMNS = 7  # id, entry_id, created_at, title, heading, context, text
_FTS_ROWS_PER_INSERT = 12  # 12 x 7 = 84 bound parameters, under D1's limit of 100 per query


def _write_keyword_rows(entry_id: int, note: Note, chunks: list, contexts: list[str]) -> None:
    """Replace the note's rows in the keyword (BM25) table, one per chunk. Deleting
    first means a shorter re-chunking leaves no stale rows behind."""
    cf.d1_query("DELETE FROM chunks_fts WHERE entry_id = ?", [entry_id])
    rows = [
        (f"{entry_id}:{i}", entry_id, note.created_at[:10], note.title, chunk.heading, context, chunk.text)
        for i, (chunk, context) in enumerate(zip(chunks, contexts))
    ]
    one_row = "(" + ",".join("?" * _FTS_COLUMNS) + ")"
    for start in range(0, len(rows), _FTS_ROWS_PER_INSERT):
        batch = rows[start:start + _FTS_ROWS_PER_INSERT]
        cf.d1_query(
            "INSERT INTO chunks_fts (id, entry_id, created_at, title, heading, context, text) VALUES "
            + ",".join([one_row] * len(batch)),
            [value for row in batch for value in row],
        )


def _index(entry_id: int, note: Note, previous: dict | None) -> int:
    """Chunk, embed and upsert one note. Returns its chunk count.

    entries.chunk_count is kept as an upper bound on the vectors that may exist
    for the note (raised *before* upserting), so whatever step fails, a later
    run still knows exactly which ids could need deleting."""
    chunks = chunk_note(note.text, note.title)
    contexts = ctx.generate(note.text, chunks)  # LLM context per chunk, or the static fallback
    embeddings = cf.embed([embed_text(c, llm_ctx) for c, llm_ctx in zip(chunks, contexts)])
    cf.d1_query("UPDATE entries SET chunk_count = MAX(chunk_count, ?) WHERE id = ?", [len(chunks), entry_id])
    cf.vectorize_upsert(
        EPISODES_INDEX,
        [
            {
                "id": f"{entry_id}:{i}",
                "values": values,
                "metadata": {
                    "entry_id": entry_id,
                    "chunk_index": i,
                    "created_at": note.created_at[:10],
                    "title": note.title,
                    "heading": chunk.heading,
                    "text": chunk.text,
                },
            }
            for i, (chunk, values) in enumerate(zip(chunks, embeddings))
        ],
    )
    # A shorter re-chunking leaves the old tail chunks behind; remove them.
    if previous and previous["chunk_count"] > len(chunks):
        cf.vectorize_delete(EPISODES_INDEX, _chunk_ids(entry_id, len(chunks), previous["chunk_count"]))
    # Written before chunk_config is updated below, so a failure here leaves the note
    # marked stale and the next run retries it.
    _write_keyword_rows(entry_id, note, chunks, contexts)
    cf.d1_query(
        "UPDATE entries SET chunk_count = ?, chunk_config = ? WHERE id = ?",
        [len(chunks), CHUNK_CONFIG, entry_id],
    )
    return len(chunks)


def sync() -> dict[str, int]:
    notes = load_notes()
    note_paths = {n.path for n in notes}
    existing = _existing()

    inserted = [n for n in notes if n.path not in existing]
    edited = [n for n in notes if n.path in existing and existing[n.path]["content_hash"] != n.content_hash]
    edited_paths = {n.path for n in edited}
    # Text unchanged, but indexed under different chunking settings (or never
    # finished indexing): re-embed only, leave consolidation alone.
    stale_index = [
        n for n in notes
        if n.path in existing and n.path not in edited_paths and existing[n.path]["chunk_config"] != CHUNK_CONFIG
    ]
    deleted = [p for p in existing if p not in note_paths]

    for n in inserted:
        cf.d1_query(
            "INSERT INTO entries (path, created_at, text, tags, content_hash, consolidated) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            [n.path, n.created_at, n.text, n.tags, n.content_hash],
        )
    for n in edited:
        # chunk_config = '' marks the index stale until _index() succeeds, so a
        # failure part-way is retried on the next run instead of going unnoticed.
        cf.d1_query(
            "UPDATE entries SET text = ?, tags = ?, content_hash = ?, consolidated = 0, chunk_config = '' "
            "WHERE path = ?",
            [n.text, n.tags, n.content_hash, n.path],
        )

    ids = {path: row["id"] for path, row in existing.items()}
    if inserted:  # new rows only get their id once inserted
        rows = cf.d1_query(
            f"SELECT id, path FROM entries WHERE path IN ({cf.placeholders(len(inserted))})",
            [n.path for n in inserted],
        )
        ids.update({r["path"]: r["id"] for r in rows})

    chunks_written = sum(
        _index(ids[n.path], n, existing.get(n.path)) for n in inserted + edited + stale_index
    )

    if deleted:
        vector_ids = [
            vid for path in deleted for vid in _chunk_ids(existing[path]["id"], 0, existing[path]["chunk_count"])
        ]
        cf.vectorize_delete(EPISODES_INDEX, vector_ids)
        cf.d1_query(
            f"DELETE FROM chunks_fts WHERE entry_id IN ({cf.placeholders(len(deleted))})",
            [existing[path]["id"] for path in deleted],
        )
        cf.d1_query(f"DELETE FROM entries WHERE path IN ({cf.placeholders(len(deleted))})", deleted)

    return {
        "inserted": len(inserted),
        "updated": len(edited),
        "reindexed": len(stale_index),
        "deleted": len(deleted),
        "chunks": chunks_written,
    }
