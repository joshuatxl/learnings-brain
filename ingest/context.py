"""LLM-generated chunk context inspired by Anthropic's 'Introducing Contextual
Retrieval' (https://www.anthropic.com/engineering/contextual-retrieval). Before
embedding a chunk, prepend a short sentence explaining what it is and where it sits in
the note, so a chunk retrieved in isolation still carries context that a bare
heading trail wouldn't such as names, dates, numbers mentioned elsewhere in the
note that the chunk itself doesn't repeat.

Calls Gemini once per note (to accommodate to Gemini free-tier limits, unlike Anthropic's 
one call per chunk), covering every one of its chunks at once. Sending the note text once per note
is also cheaper than a REST API with no caching set up. A failure a retry could
fix (a server error, a malformed response) is tried up to three times. Anything
still failing, or a missing key or quota error, falls back to each chunk's own
static title/heading context, so ingestion is never blocked by this, and it just quietly
ships the cheaper version for that note.
"""
from __future__ import annotations

import json
import re
import time

from .chunking import Chunk
from .config import GEMINI_API_KEY, SUMMARY_MODEL

_MAX_ATTEMPTS = 3  # total Gemini tries for one note before using the static context
_RETRY_DELAY_S = 2  # grows with each attempt: 2s, then 4s

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


def _request_contexts(client, prompt: str, n: int) -> list:
    """One Gemini call, parsed and checked to hold exactly n contexts. Raises
    on an API error, malformed JSON, or the wrong number of contexts."""
    resp = client.models.generate_content(model=SUMMARY_MODEL, contents=prompt)
    raw = re.sub(r"^```(json)?|```$", "", (resp.text or "").strip(), flags=re.MULTILINE).strip()
    contexts = json.loads(raw)["contexts"]
    if not isinstance(contexts, list) or len(contexts) != n:
        raise ValueError(f"expected {n} contexts, got {contexts!r}")
    return contexts


def generate(note_text: str, chunks: list[Chunk]) -> list[str]:
    """One context string per chunk, aligned by index, always exactly
    len(chunks) long. Tries Gemini up to _MAX_ATTEMPTS times, then falls back
    to each chunk's static context (from chunking.py)."""
    fallback = [c.context for c in chunks]
    if not GEMINI_API_KEY or not chunks:
        return fallback

    numbered = "\n\n".join(f"{i + 1}. {c.text}" for i, c in enumerate(chunks))
    prompt = _PROMPT.format(n=len(chunks), note=note_text, chunks=numbered)
    try:
        from google import genai
        from google.genai import errors

        client = genai.Client(api_key=GEMINI_API_KEY)
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                contexts = _request_contexts(client, prompt, len(chunks))
                return [str(c).strip() or fb for c, fb in zip(contexts, fallback)]
            except errors.ClientError:
                raise  # a 4xx (bad key, 429 quota) won't clear on a retry
            except Exception as e:
                if attempt == _MAX_ATTEMPTS:
                    raise
                print(f"  context: attempt {attempt}/{_MAX_ATTEMPTS} failed ({e}), retrying")
                time.sleep(_RETRY_DELAY_S * attempt)
    except Exception as e:
        print(f"  context: Gemini call failed for this note, using static context ({e})")
        return fallback
