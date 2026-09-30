import json
import unittest
from unittest import mock

from ingest import context
from ingest.chunking import Chunk


def gemini_returning(text: str):
    """A fake google.genai.Client whose generate_content(...).text is `text`."""
    client = mock.MagicMock()
    client.models.generate_content.return_value.text = text
    return client


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            Chunk(text="First passage.", context="Note - Section A", heading="Section A"),
            Chunk(text="Second passage.", context="Note - Section B", heading="Section B"),
        ]

    def test_no_api_key_returns_the_static_context_unchanged(self):
        with mock.patch.object(context, "GEMINI_API_KEY", ""):
            result = context.generate("full note text", self.chunks)
        self.assertEqual(result, ["Note - Section A", "Note - Section B"])

    def test_no_chunks_makes_no_call_and_returns_empty(self):
        with mock.patch.object(context, "GEMINI_API_KEY", "fake-key"):
            with mock.patch("google.genai.Client") as Client:
                result = context.generate("full note text", [])
        Client.assert_not_called()
        self.assertEqual(result, [])

    def test_successful_call_returns_the_generated_contexts_in_order(self):
        payload = json.dumps({"contexts": ["Context for the first passage.", "Context for the second."]})
        with mock.patch.object(context, "GEMINI_API_KEY", "fake-key"):
            with mock.patch("google.genai.Client", return_value=gemini_returning(payload)):
                result = context.generate("full note text", self.chunks)
        self.assertEqual(result, ["Context for the first passage.", "Context for the second."])

    def test_call_wraps_response_in_a_code_fence_is_still_parsed(self):
        payload = "```json\n" + json.dumps({"contexts": ["A.", "B."]}) + "\n```"
        with mock.patch.object(context, "GEMINI_API_KEY", "fake-key"):
            with mock.patch("google.genai.Client", return_value=gemini_returning(payload)):
                result = context.generate("full note text", self.chunks)
        self.assertEqual(result, ["A.", "B."])

    def test_wrong_number_of_contexts_falls_back_to_static(self):
        payload = json.dumps({"contexts": ["Only one."]})
        with mock.patch.object(context, "GEMINI_API_KEY", "fake-key"):
            with mock.patch("google.genai.Client", return_value=gemini_returning(payload)):
                result = context.generate("full note text", self.chunks)
        self.assertEqual(result, ["Note - Section A", "Note - Section B"])

    def test_malformed_json_falls_back_to_static(self):
        with mock.patch.object(context, "GEMINI_API_KEY", "fake-key"):
            with mock.patch("google.genai.Client", return_value=gemini_returning("not json at all")):
                result = context.generate("full note text", self.chunks)
        self.assertEqual(result, ["Note - Section A", "Note - Section B"])

    def test_gemini_error_falls_back_to_static(self):
        client = mock.MagicMock()
        client.models.generate_content.side_effect = RuntimeError("quota exceeded")
        with mock.patch.object(context, "GEMINI_API_KEY", "fake-key"):
            with mock.patch("google.genai.Client", return_value=client):
                result = context.generate("full note text", self.chunks)
        self.assertEqual(result, ["Note - Section A", "Note - Section B"])

    def test_a_blank_generated_context_falls_back_to_static_for_just_that_chunk(self):
        payload = json.dumps({"contexts": ["", "Context for the second."]})
        with mock.patch.object(context, "GEMINI_API_KEY", "fake-key"):
            with mock.patch("google.genai.Client", return_value=gemini_returning(payload)):
                result = context.generate("full note text", self.chunks)
        self.assertEqual(result, ["Note - Section A", "Context for the second."])


if __name__ == "__main__":
    unittest.main()
