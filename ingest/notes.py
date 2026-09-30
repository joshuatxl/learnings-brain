"""Read learning notes from LEARNINGS_DIR. Each note is a markdown file,
optionally with YAML frontmatter (date, tags). The file's repo-relative
path is its stable identity; editing a file re-ingests it, deleting it
removes it from episodic memory."""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import frontmatter

from .config import LEARNINGS_DIR

_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass
class Note:
    path: str          # repo-relative, e.g. learnings/2026-09-22-rag-basics.md
    title: str         # frontmatter title, else first "# " heading, else the file name
    text: str          # body, frontmatter stripped
    tags: str          # comma-separated
    created_at: str     # ISO date/time
    content_hash: str  # sha256 of text, to detect edits


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _title(post: frontmatter.Post, text: str, path: str) -> str:
    if post.get("title"):
        return str(post["title"]).strip()
    heading = _H1.search(text)
    if heading:
        return heading.group(1).strip()
    stem = os.path.splitext(os.path.basename(path))[0]
    return _DATE_PREFIX.sub("", stem).replace("-", " ").replace("_", " ").strip()


def load_notes() -> list[Note]:
    notes: list[Note] = []
    if not os.path.isdir(LEARNINGS_DIR):
        return notes
    for root, _dirs, files in os.walk(LEARNINGS_DIR):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.relpath(os.path.join(root, name)).replace(os.sep, "/")
            post = frontmatter.load(path)
            text = post.content.strip()
            if not text:
                continue
            tags = post.get("tags", "")
            tags = ",".join(tags) if isinstance(tags, list) else str(tags or "")
            date = post.get("date")
            created_at = f"{date}T00:00:00+00:00" if date else datetime.now(timezone.utc).isoformat()
            notes.append(Note(path=path, title=_title(post, text, path), text=text, tags=tags,
                               created_at=created_at, content_hash=_hash(text)))
    return notes
