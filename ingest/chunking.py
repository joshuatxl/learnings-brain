"""Split a learning note into passages worth embedding separately.

Two stages:
  1. Cut at markdown headings, so a passage never straddles two sections and
     each keeps its heading trail. (Hand-rolled rather than LangChain's
     MarkdownHeaderTextSplitter, which strips every line's indentation and so
     mangles Python in code blocks.)
  2. LangChain's RecursiveCharacterTextSplitter re-splits any section longer
     than CHUNK_SIZE on paragraph -> line -> sentence -> word boundaries,
     repeating CHUNK_OVERLAP characters between neighbours so boundary
     sentences keep their context.

A note shorter than CHUNK_SIZE with no headings comes back as one chunk, so
short notes behave exactly as they would without chunking.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import CHUNK_OVERLAP, CHUNK_SIZE

_HEADING = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass
class Chunk:
    text: str         # the passage itself, as shown in citations
    context: str      # static "title - heading" context, "" if neither applies
    heading: str      # "Section > Subsection", or "" when the passage has none


def embed_text(chunk: Chunk, context: str | None = None) -> str:
    """What actually gets embedded: a context sentence followed by the
    passage. Pass an LLM-generated context (see context.py) to use that
    instead of the chunk's own static title/heading context."""
    ctx = chunk.context if context is None else context
    return f"{ctx}\n\n{chunk.text}" if ctx else chunk.text


def _sections(text: str) -> list[tuple[list[str], str]]:
    """(heading trail, verbatim body) for each heading-delimited section.
    Lines inside code fences are never treated as headings (`# comment`)."""
    sections: list[tuple[list[str], str]] = []
    trail: list[tuple[int, str]] = []
    body: list[str] = []
    fenced = False

    def flush() -> None:
        joined = "\n".join(body).strip()
        if joined:
            sections.append(([t for _, t in trail], joined))
        body.clear()

    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        heading = None if fenced else _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            trail = [(lvl, t) for lvl, t in trail if lvl < level] + [(level, heading.group(2))]
        else:
            body.append(line)
    flush()
    return sections


def chunk_note(text: str, title: str) -> list[Chunk]:
    # keep_separator="end" keeps each sentence's full stop with that sentence;
    # the default attaches it to the start of the next chunk (". Next one...").
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        keep_separator="end",
    )
    chunks = []
    for trail, body in _sections(text):
        # The title often repeats the note's own H1; don't say it twice.
        heading = " > ".join(h for h in trail if h.strip().lower() != title.strip().lower())
        context = " - ".join(part for part in (title, heading) if part)
        for passage in splitter.split_text(body):
            passage = passage.strip()
            if passage:
                chunks.append(Chunk(text=passage, context=context, heading=heading))
    if not chunks and text.strip():  # e.g. a note that is only a heading line
        chunks.append(Chunk(text=text.strip(), context=title, heading=""))
    return chunks
