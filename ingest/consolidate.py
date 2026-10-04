"""The gate + summariser: turn pending episodic notes into semantic facts,
merging into what's already stored instead of appending duplicates.

Flow: gate checks pending count -> embed pending notes -> look up similar
existing facts -> ask Gemini for add/update/supersede/flag operations ->
apply them -> mark notes consolidated."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from . import cloudflare as cf
from .chunking import chunk_note
from .config import CONSOLIDATE_AFTER, FACT_SEARCH_K, FACTS_INDEX, GEMINI_API_KEY, SUMMARY_MODEL

_PROMPT = """You maintain a personal knowledge base of standalone facts, each
with a short topic tag. Below are new dated notes and the existing facts most
similar to them.

For each piece of new information, choose ONE operation:
- "add": a genuinely new fact not covered below. Omit "id".
- "update": merge new information into an existing fact. Set "id" to the
  fact's existing id and "text" to the full rewritten fact.
- "supersede": an existing fact is now outdated or wrong. Set "id" to the
  old fact's id and "text" to the corrected replacement fact.
- "flag": the new note contradicts an existing fact and you cannot tell
  which is right. Set "id" to the conflicting fact and "text" to a one-line
  description of the conflict. Do not guess.

Rules: standalone facts only (no "as mentioned above"), merge don't append,
keep names/numbers/specifics, short topic tag (1-3 words, reuse an existing
topic when it fits), no duplicate facts, no preamble.

Respond with ONLY a JSON object: {{"operations": [
  {{"op": "add"|"update"|"supersede"|"flag", "id": "<existing id or null>",
   "text": "<fact text or conflict description>", "topic": "<topic or null>"}}
]}}

## New notes
{notes}

## Existing similar facts
{facts}
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fact_id(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:16]


def _pending() -> list[dict]:
    return cf.d1_query("SELECT id, created_at, text FROM entries WHERE consolidated = 0")


def _lock_acquire() -> bool:
    rows = cf.d1_query("SELECT running FROM consolidation_lock WHERE id = 1")
    if rows and rows[0]["running"]:
        return False
    cf.d1_query("UPDATE consolidation_lock SET running = 1, started_at = ? WHERE id = 1", [_now()])
    return True


def _lock_release() -> None:
    cf.d1_query("UPDATE consolidation_lock SET running = 0 WHERE id = 1")


def _similar_facts(pending: list[dict]) -> list[dict]:
    # Search with every chunk of every pending note, not just the note's opening
    # (the embedding model only reads the first ~512 tokens of what it's given).
    passages = [c.text for p in pending for c in chunk_note(p["text"], "")]
    ids = {m["id"] for vec in cf.embed(passages) for m in cf.vectorize_query(FACTS_INDEX, vec, FACT_SEARCH_K)}
    if not ids:
        return []
    ids = list(ids)
    return cf.d1_query(
        f"SELECT id, text, topic FROM facts WHERE id IN ({cf.placeholders(len(ids))}) AND status = 'active'",
        ids,
    )


def _call_gemini(pending: list[dict], facts: list[dict]) -> list[dict]:
    from google import genai

    notes = "\n".join(f"- [{p['created_at'][:10]}] {p['text']}" for p in pending)
    fact_lines = "\n".join(f"- ({f['id']}) {f['text']} [{f['topic'] or 'untagged'}]" for f in facts) or "(none yet)"
    prompt = _PROMPT.format(notes=notes, facts=fact_lines)

    client = genai.Client(api_key=GEMINI_API_KEY)
    resp = client.models.generate_content(model=SUMMARY_MODEL, contents=prompt)
    raw = (resp.text or "").strip()
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(raw).get("operations", [])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"summariser returned invalid JSON: {e}\n{raw[:500]}")


def _write_fact(fid: str, text: str, topic: str, source_ids: str) -> None:
    cf.d1_query(
        "INSERT OR REPLACE INTO facts (id, text, topic, status, source_entry_ids, updated_at) "
        "VALUES (?, ?, ?, 'active', ?, ?)",
        [fid, text, topic, source_ids, _now()],
    )


def _apply(ops: list[dict], pending_ids: list[int]) -> dict[str, int]:
    counts = {"add": 0, "update": 0, "supersede": 0, "flag": 0}
    source_ids = ",".join(str(i) for i in pending_ids)
    to_embed: list[tuple[str, str, str]] = []  # (fact_id, text, topic)

    for op in ops:
        kind = op.get("op")
        text = str(op.get("text") or "").strip()
        if not text or kind not in counts:
            continue
        counts[kind] += 1
        topic = op.get("topic") or ""

        if kind == "add":
            fid = _fact_id(text)
            _write_fact(fid, text, topic, source_ids)
            to_embed.append((fid, text, topic))

        elif kind == "update":
            fid = op.get("id")
            if not fid:
                continue
            cf.d1_query(
                "UPDATE facts SET text = ?, topic = COALESCE(?, topic), source_entry_ids = ?, "
                "updated_at = ? WHERE id = ?",
                [text, op.get("topic"), source_ids, _now(), fid],
            )
            to_embed.append((fid, text, topic))

        elif kind == "supersede":
            old_id = op.get("id")
            new_id = _fact_id(text)
            if old_id:
                cf.d1_query(
                    "UPDATE facts SET status = 'superseded', superseded_by = ? WHERE id = ?",
                    [new_id, old_id],
                )
            _write_fact(new_id, text, topic, source_ids)
            to_embed.append((new_id, text, topic))

        elif kind == "flag":
            cf.d1_query(
                "INSERT INTO review_queue (created_at, detail, fact_ids) VALUES (?, ?, ?)",
                [_now(), text, str(op.get("id") or "")],
            )

    if to_embed:
        vectors = cf.embed([t for _, t, _ in to_embed])
        cf.vectorize_upsert(
            FACTS_INDEX,
            [
                {"id": fid, "values": vec, "metadata": {"topic": topic}}
                for (fid, _, topic), vec in zip(to_embed, vectors)
            ],
        )
    return counts


def run(force: bool = False) -> dict[str, int]:
    pending = _pending()
    if not pending or (len(pending) < CONSOLIDATE_AFTER and not force):
        return {"skipped": len(pending)}
    if not GEMINI_API_KEY:
        return {"skipped": len(pending), "reason": "GEMINI_API_KEY not set"}
    if not _lock_acquire():
        return {"skipped": len(pending), "reason": "already running"}

    try:
        facts = _similar_facts(pending)
        ops = _call_gemini(pending, facts)
        ids = [p["id"] for p in pending]
        counts = _apply(ops, ids)
        cf.d1_query(f"UPDATE entries SET consolidated = 1 WHERE id IN ({cf.placeholders(len(ids))})", ids)
        counts["notes_consolidated"] = len(pending)
        return counts
    finally:
        _lock_release()
