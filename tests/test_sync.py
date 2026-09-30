"""sync() against a fake Cloudflare: D1 is real SQLite (loaded from the actual
schema.sql, since D1 *is* SQLite), Vectorize is a dict, embeddings are fake."""
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from ingest import cloudflare as cf
from ingest import context
from ingest import sync
from ingest.config import CHUNK_CONFIG
from ingest.notes import load_notes

SCHEMA = os.path.join(os.path.dirname(__file__), "..", "brain-worker", "schema.sql")


def sentences(n: int) -> str:
    return " ".join(f"Sentence number {i} explains a distinct idea about topic {i}." for i in range(n))


LONG_NOTE = "# Long note\n\n## Part one\n\n" + sentences(40) + "\n\n## Part two\n\n" + sentences(40)


class FakeCloudflare:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        with open(SCHEMA, encoding="utf-8") as f:
            self.db.executescript(f.read())
        self.vectors: dict[str, dict] = {}
        self.embed_calls = 0
        self.embedded_texts: list[list[str]] = []  # what was actually sent to embed(), per call
        self.fail_next_embed = False

    def d1_query(self, sql, params=None):
        cur = self.db.execute(sql, params or [])
        self.db.commit()
        return [dict(r) for r in cur.fetchall()] if cur.description else []

    def embed(self, texts):
        self.embed_calls += 1
        if self.fail_next_embed:
            self.fail_next_embed = False
            raise RuntimeError("Workers AI unavailable")
        self.embedded_texts.append(list(texts))
        return [[float(len(t)), 0.0, 1.0] for t in texts]

    def vectorize_upsert(self, index, vectors):
        for v in vectors:
            self.vectors[v["id"]] = v

    def vectorize_delete(self, index, ids):
        for i in ids:
            self.vectors.pop(i, None)

    def row(self, path="learnings/a.md"):
        return dict(self.db.execute("SELECT * FROM entries WHERE path = ?", [path]).fetchone())


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        os.mkdir("learnings")
        self.fake = FakeCloudflare()
        patcher = mock.patch.multiple(
            cf,
            d1_query=self.fake.d1_query,
            embed=self.fake.embed,
            vectorize_upsert=self.fake.vectorize_upsert,
            vectorize_delete=self.fake.vectorize_delete,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # Deterministic regardless of whether the real environment happens to
        # have a key set: no key -> context.generate() returns each chunk's
        # static context unchanged, exactly like the pre-LLM-context behaviour.
        key_patcher = mock.patch.object(context, "GEMINI_API_KEY", "")
        key_patcher.start()
        self.addCleanup(key_patcher.stop)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def write(self, text, name="a.md"):
        with open(os.path.join("learnings", name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_new_long_note_is_chunked_and_indexed(self):
        self.write(LONG_NOTE)
        result = sync.sync()
        row = self.fake.row()
        n = row["chunk_count"]
        self.assertGreater(n, 2)
        self.assertEqual(result, {"inserted": 1, "updated": 0, "reindexed": 0, "deleted": 0, "chunks": n})
        self.assertEqual(row["chunk_config"], CHUNK_CONFIG)
        self.assertEqual(set(self.fake.vectors), {f"{row['id']}:{i}" for i in range(n)})
        meta = self.fake.vectors[f"{row['id']}:0"]["metadata"]
        self.assertEqual(meta["title"], "Long note")
        self.assertEqual(meta["heading"], "Part one")
        self.assertEqual(meta["entry_id"], row["id"])
        self.assertTrue(meta["text"].startswith("Sentence number 0"))

    def test_llm_generated_context_reaches_the_embedded_text(self):
        self.write(LONG_NOTE)
        fake_contexts = mock.Mock(side_effect=lambda note_text, chunks: [f"CTX-{i}" for i in range(len(chunks))])
        with mock.patch.object(sync.ctx, "generate", fake_contexts):
            sync.sync()
        fake_contexts.assert_called_once()
        sent = self.fake.embedded_texts[-1]
        self.assertGreater(len(sent), 2)
        for i, text in enumerate(sent):
            self.assertTrue(text.startswith(f"CTX-{i}\n\n"), text[:20])

    def test_unchanged_rerun_does_no_work(self):
        self.write(LONG_NOTE)
        sync.sync()
        calls = self.fake.embed_calls
        result = sync.sync()
        self.assertEqual(result, {"inserted": 0, "updated": 0, "reindexed": 0, "deleted": 0, "chunks": 0})
        self.assertEqual(self.fake.embed_calls, calls)

    def test_editing_to_a_shorter_note_removes_the_surplus_vectors(self):
        self.write(LONG_NOTE)
        sync.sync()
        self.fake.d1_query("UPDATE entries SET consolidated = 1")
        self.write("Now just one short paragraph.")
        result = sync.sync()
        row = self.fake.row()
        self.assertEqual((result["updated"], result["reindexed"]), (1, 0))
        self.assertEqual(row["chunk_count"], 1)
        self.assertEqual(set(self.fake.vectors), {f"{row['id']}:0"})
        self.assertEqual(row["consolidated"], 0, "a text edit must re-queue the note for consolidation")

    def test_changed_chunk_settings_reindex_without_requeuing_consolidation(self):
        self.write(LONG_NOTE)
        sync.sync()
        self.fake.d1_query("UPDATE entries SET consolidated = 1")
        with mock.patch.object(sync, "CHUNK_CONFIG", "md-recursive-v2:900:100"):
            result = sync.sync()
        row = self.fake.row()
        self.assertEqual((result["updated"], result["reindexed"]), (0, 1))
        self.assertEqual(row["chunk_config"], "md-recursive-v2:900:100")
        self.assertEqual(row["consolidated"], 1)

    def test_deleting_a_note_removes_its_row_and_every_chunk_vector(self):
        self.write(LONG_NOTE)
        sync.sync()
        os.remove(os.path.join("learnings", "a.md"))
        result = sync.sync()
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(self.fake.vectors, {})
        self.assertEqual(self.fake.d1_query("SELECT * FROM entries"), [])

    def test_failed_indexing_of_a_new_note_is_retried_next_run(self):
        self.write(LONG_NOTE)
        self.fake.fail_next_embed = True
        with self.assertRaises(RuntimeError):
            sync.sync()
        self.assertEqual(self.fake.row()["chunk_config"], "")
        self.assertEqual(self.fake.vectors, {})
        result = sync.sync()
        self.assertEqual((result["inserted"], result["reindexed"]), (0, 1))
        self.assertGreater(len(self.fake.vectors), 2)

    def test_failed_indexing_of_an_edit_is_not_forgotten(self):
        self.write(LONG_NOTE)
        sync.sync()
        self.write("Edited text that must end up in the index.")
        self.fake.fail_next_embed = True
        with self.assertRaises(RuntimeError):
            sync.sync()
        self.assertEqual(self.fake.row()["chunk_config"], "", "index must be marked stale")
        result = sync.sync()
        self.assertEqual((result["updated"], result["reindexed"]), (0, 1))
        row = self.fake.row()
        self.assertEqual(set(self.fake.vectors), {f"{row['id']}:0"})
        self.assertEqual(self.fake.vectors[f"{row['id']}:0"]["metadata"]["text"], "Edited text that must end up in the index.")


class TitleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        os.mkdir("learnings")

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def title_of(self, name, content):
        with open(os.path.join("learnings", name), "w", encoding="utf-8") as f:
            f.write(content)
        return load_notes()[0].title

    def test_frontmatter_title_wins(self):
        self.assertEqual(self.title_of("x.md", "---\ntitle: From frontmatter\n---\n# Heading\nbody"), "From frontmatter")

    def test_first_h1_is_next(self):
        self.assertEqual(self.title_of("x.md", "# A heading\n\nbody"), "A heading")

    def test_filename_is_the_fallback_with_the_date_stripped(self):
        self.assertEqual(self.title_of("2026-09-22-rag-basics.md", "just body text"), "rag basics")


if __name__ == "__main__":
    unittest.main()
