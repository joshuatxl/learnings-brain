"""Diff learnings/*.md against the entries table in D1 and apply the
difference. Each note is stored in Vectorize as chunks (see chunking.py): it is
(re)chunked and re-embedded when it is new, when its text changed, or when
CHUNK_CONFIG differs from the one it was last indexed with. Deleted files are
removed from D1 and Vectorize."""
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
        cf.d1_query(f"DELETE FROM entries WHERE path IN ({cf.placeholders(len(deleted))})", deleted)

    return {
        "inserted": len(inserted),
        "updated": len(edited),
        "reindexed": len(stale_index),
        "deleted": len(deleted),
        "chunks": chunks_written,
    }
