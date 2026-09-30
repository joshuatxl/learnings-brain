import unittest

from ingest.chunking import chunk_note, embed_text
from ingest.config import CHUNK_OVERLAP, CHUNK_SIZE


def sentences(n: int) -> str:
    """n distinct sentences, so overlap and coverage can be told apart."""
    return " ".join(f"Sentence number {i} explains a distinct idea about topic {i}." for i in range(n))


class ChunkNoteTests(unittest.TestCase):
    def test_short_note_is_a_single_chunk(self):
        chunks = chunk_note("RAG retrieves passages before answering.", "RAG basics")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "RAG retrieves passages before answering.")
        self.assertEqual(chunks[0].context, "RAG basics")
        self.assertEqual(embed_text(chunks[0]), "RAG basics\n\nRAG retrieves passages before answering.")
        self.assertEqual(chunks[0].heading, "")

    def test_heading_trail_is_kept_and_title_is_not_repeated(self):
        note = "# RAG basics\n\nIntro.\n\n## Retrieval\n\nTop-k search.\n\n### Overlap\n\nRepeat a little text."
        by_text = {c.text: c for c in chunk_note(note, "RAG basics")}
        self.assertEqual(by_text["Intro."].heading, "")  # h1 == title, so dropped
        self.assertEqual(by_text["Top-k search."].heading, "Retrieval")
        self.assertEqual(by_text["Repeat a little text."].heading, "Retrieval > Overlap")
        self.assertEqual(
            embed_text(by_text["Repeat a little text."]),
            "RAG basics - Retrieval > Overlap\n\nRepeat a little text.",
        )
        self.assertEqual(  # an LLM-generated context overrides the static one
            embed_text(by_text["Repeat a little text."], "Explains why overlap matters."),
            "Explains why overlap matters.\n\nRepeat a little text.",
        )

    def test_long_section_is_split_within_the_size_limit(self):
        chunks = chunk_note(sentences(80), "Long note")
        self.assertGreater(len(chunks), 2)
        for c in chunks:
            self.assertLessEqual(len(c.text), CHUNK_SIZE)

    def test_every_sentence_survives_chunking(self):
        text = sentences(80)
        joined = " ".join(c.text for c in chunk_note(text, "Long note"))
        for i in range(80):
            self.assertIn(f"Sentence number {i} explains", joined)

    def test_neighbouring_chunks_overlap(self):
        chunks = chunk_note(sentences(80), "Long note")
        for a, b in zip(chunks, chunks[1:]):
            last_sentence_of_a = a.text.rsplit(". ", 1)[-1]
            self.assertIn(last_sentence_of_a, b.text, "chunk should repeat the previous chunk's tail")
        self.assertGreater(CHUNK_OVERLAP, 0)

    def test_chunks_start_and_end_on_sentence_boundaries(self):
        for c in chunk_note(sentences(80), "Long note"):
            self.assertTrue(c.text.startswith("Sentence"), c.text[:30])
            self.assertTrue(c.text.endswith("."), c.text[-30:])

    def test_a_small_code_block_stays_whole_with_its_indentation(self):
        note = "## Snippet\n\nIntro text.\n\n```python\ndef f(x):\n    return x + 1\n```\n"
        chunks = chunk_note(note, "Code note")
        self.assertEqual(len(chunks), 1)
        self.assertIn("def f(x):\n    return x + 1", chunks[0].text)

    def test_hash_comments_inside_code_fences_are_not_headings(self):
        note = "## Real heading\n\n```python\n# not a heading\nx = 1\n```\n"
        chunks = chunk_note(note, "Code note")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].heading, "Real heading")
        self.assertIn("# not a heading", chunks[0].text)

    def test_heading_only_note_still_gets_a_chunk(self):
        chunks = chunk_note("# Just a title", "Just a title")
        self.assertEqual(len(chunks), 1)
        self.assertIn("Just a title", chunks[0].text)

    def test_empty_note_has_no_chunks(self):
        self.assertEqual(chunk_note("   \n\n  ", "Empty"), [])


if __name__ == "__main__":
    unittest.main()
