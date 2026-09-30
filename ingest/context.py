"""Dynamic, LLM-generated chunk context -- Anthropic's "Contextual Retrieval"
(https://www.anthropic.com/engineering/contextual-retrieval): before embedding
a chunk, prepend a short sentence explaining what it is and where it sits in
the note, so a chunk retrieved in isolation still carries context that a bare
heading trail wouldn't -- names, dates, numbers mentioned elsewhere in the
note that the chunk itself doesn't repeat.

One Gemini call per note, covering every one of its chunks at once, rather
than the one-call-per-chunk Anthropic describes (they lean on prompt caching
of the document instead; sending the note text once per note is the cheaper
option against a REST API with no caching set up). Falls back to each
chunk's own static title/heading context on any failure -- a missing key, a
quota error, a malformed response -- so ingestion is never blocked by this;
it just quietly ships the cheaper version for that note.
"""
from __future__ import annotations

import json
import re

from .chunking import Chunk
from .config import GEMINI_API_KEY, SUMMARY_MODEL

_PROMPT = """Below is a full note, then its chunks -- excerpts taken verbatim \
from it, numbered in order. For each chunk, write ONE short sentence (under \
30 words) that situates it within the note: what topic or section it's part \
of, plus any identifying detail from elsewhere in the note (names, dates, \
numbers) that the chunk alone doesn't carry. Do not quote the chunk itself \
back, and do not add a preamble.

Respond with ONLY a JSON object: {{"contexts": ["...", ...]}}, with exactly \
{n} strings, in the same order as the chunks.

## Full note
{note}

## Chunks
{chunks}"""


def generate(note_text: str, chunks: list[Chunk]) -> list[str]:
    """One context string per chunk, aligned by index, always exactly
    len(chunks) long. Falls back to each chunk's static context (from
    chunking.py) on any failure."""
    fallback = [c.context for c in chunks]
    if not GEMINI_API_KEY or not chunks:
        return fallback

    numbered = "\n\n".join(f"{i + 1}. {c.text}" for i, c in enumerate(chunks))
    prompt = _PROMPT.format(n=len(chunks), note=note_text, chunks=numbered)
    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(model=SUMMARY_MODEL, contents=prompt)
        raw = re.sub(r"^```(json)?|```$", "", (resp.text or "").strip(), flags=re.MULTILINE).strip()
        contexts = json.loads(raw)["contexts"]
        if not isinstance(contexts, list) or len(contexts) != len(chunks):
            raise ValueError(f"expected {len(chunks)} contexts, got {contexts!r}")
        return [str(c).strip() or fb for c, fb in zip(contexts, fallback)]
    except Exception as e:
        print(f"  context: Gemini call failed for this note, using static context ({e})")
        return fallback
