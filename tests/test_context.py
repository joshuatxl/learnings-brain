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


def _server_error(code: int = 503):
    from google.genai import errors

    return errors.ServerError(code, {"error": {"code": code, "message": "high demand", "status": "UNAVAILABLE"}})


def _client_error(code: int = 429):
    from google.genai import errors

    return errors.ClientError(code, {"error": {"code": code, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            Chunk(text="First passage.", context="Note - Section A", heading="Section A"),
            Chunk(text="Second passage.", context="Note - Section B", heading="Section B"),
        ]
        self.sleep = mock.patch.object(context.time, "sleep").start()  # retries wait; tests shouldn't
        self.addCleanup(mock.patch.stopall)

    def _generate_with(self, side_effect):
        client = mock.MagicMock()
        client.models.generate_content.side_effect = side_effect
        with mock.patch.object(context, "GEMINI_API_KEY", "fake-key"):
            with mock.patch("google.genai.Client", return_value=client):
                result = context.generate("full note text", self.chunks)
        return result, client.models.generate_content.call_count

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

    def test_a_transient_server_error_is_retried_until_it_succeeds(self):
        good = mock.MagicMock(text=json.dumps({"contexts": ["First.", "Second."]}))
        result, calls = self._generate_with([_server_error(), _server_error(), good])
        self.assertEqual(result, ["First.", "Second."])
        self.assertEqual(calls, 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_a_malformed_response_is_retried(self):
        bad = mock.MagicMock(text="not json at all")
        good = mock.MagicMock(text=json.dumps({"contexts": ["First.", "Second."]}))
        result, calls = self._generate_with([bad, good])
        self.assertEqual(result, ["First.", "Second."])
        self.assertEqual(calls, 2)

    def test_the_wrong_number_of_contexts_is_retried(self):
        short = mock.MagicMock(text=json.dumps({"contexts": ["Only one."]}))
        good = mock.MagicMock(text=json.dumps({"contexts": ["First.", "Second."]}))
        result, calls = self._generate_with([short, good])
        self.assertEqual(result, ["First.", "Second."])
        self.assertEqual(calls, 2)

    def test_three_failures_in_a_row_fall_back_to_static(self):
        result, calls = self._generate_with([_server_error()] * 5)
        self.assertEqual(result, ["Note - Section A", "Note - Section B"])
        self.assertEqual(calls, 3)

    def test_a_client_error_such_as_a_429_is_not_retried(self):
        result, calls = self._generate_with([_client_error(429)] * 5)
        self.assertEqual(result, ["Note - Section A", "Note - Section B"])
        self.assertEqual(calls, 1)
        self.sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
