"""Thin REST client for the Cloudflare services the ingest pipeline writes
to: D1 (SQL), Vectorize (vectors) and Workers AI (embeddings).

Uses plain HTTP + CLOUDFLARE_API_TOKEN, not wrangler, so the Action doesn't
need Node. The token must be scoped to D1 Edit, Vectorize Edit and Workers
AI Read only (see README.md Phase 4)."""
from __future__ import annotations

import json
from typing import Any

import requests

from .config import CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, D1_DATABASE_ID, EMBED_BATCH, EMBED_MODEL

_BASE = "https://api.cloudflare.com/client/v4"


def _account_url(path: str) -> str:
    return f"{_BASE}/accounts/{CLOUDFLARE_ACCOUNT_ID}/{path}"


def _headers(content_type: str = "application/json") -> dict:
    return {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}", "Content-Type": content_type}


def _check(resp: requests.Response, what: str) -> dict:
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success", False):
        raise RuntimeError(f"{what} failed: {data.get('errors')}")
    return data


def placeholders(n: int) -> str:
    """'?,?,?' for an n-item SQL IN (...) clause."""
    return ",".join("?" * n)


# --- D1 --------------------------------------------------------------
def d1_query(sql: str, params: list | None = None) -> list[dict]:
    url = _account_url(f"d1/database/{D1_DATABASE_ID}/query")
    resp = requests.post(url, headers=_headers(), json={"sql": sql, "params": params or []})
    data = _check(resp, "D1 query")
    # D1's HTTP API returns a list of statement results; we only ever send one.
    result = data["result"][0]
    return result.get("results", [])


# --- Workers AI (embeddings) -----------------------------------------
def embed(texts: list[str]) -> list[list[float]]:
    """One vector per text, in order. Sent in EMBED_BATCH-sized calls."""
    url = _account_url(f"ai/run/{EMBED_MODEL}")
    vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        resp = requests.post(url, headers=_headers(), json={"text": texts[i:i + EMBED_BATCH]})
        vectors += _check(resp, "Workers AI embed")["result"]["data"]
    return vectors


# --- Vectorize ---------------------------------------------------------
def vectorize_upsert(index: str, vectors: list[dict[str, Any]]) -> None:
    """vectors: [{id, values, metadata?}, ...]"""
    if not vectors:
        return
    url = _account_url(f"vectorize/v2/indexes/{index}/upsert")
    body = "\n".join(json.dumps(v) for v in vectors)
    resp = requests.post(url, headers=_headers("application/x-ndjson"), data=body)
    _check(resp, f"Vectorize upsert ({index})")


def vectorize_delete(index: str, ids: list[str]) -> None:
    if not ids:
        return
    url = _account_url(f"vectorize/v2/indexes/{index}/delete_by_ids")
    resp = requests.post(url, headers=_headers(), json={"ids": ids})
    _check(resp, f"Vectorize delete ({index})")


def vectorize_query(index: str, vector: list[float], top_k: int) -> list[dict]:
    url = _account_url(f"vectorize/v2/indexes/{index}/query")
    resp = requests.post(
        url, headers=_headers(), json={"vector": vector, "topK": top_k, "returnMetadata": "all"}
    )
    data = _check(resp, f"Vectorize query ({index})")
    return data["result"]["matches"]
