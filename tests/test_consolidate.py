import json
import unittest
from unittest import mock

from ingest import consolidate


class PromptTests(unittest.TestCase):
    def test_prompt_formats_without_error(self):
        # The prompt holds a literal JSON example, so its braces must be
        # escaped for str.format -- a bad brace only fails once consolidation
        # actually runs (the scheduled job), not on a normal sync.
        prompt = consolidate._PROMPT.format(notes="- a note {with braces}", facts="(none yet)")
        self.assertIn("- a note {with braces}", prompt)
        self.assertIn('{"operations": [', prompt)

    def test_prompt_json_example_is_present_and_intact(self):
        prompt = consolidate._PROMPT.format(notes="n", facts="f")
        example = prompt[prompt.index('{"operations"') : prompt.index("## New notes")].strip()
        self.assertTrue(example.endswith("]}"))
        self.assertIn('"op": "add"', example)
        json.dumps(example)  # a plain string, just confirm nothing odd slipped in


PENDING = [{"id": 1, "created_at": "2026-10-02T00:00:00", "text": "a note"}]


def _server_error(code: int = 503):
    from google.genai import errors

    return errors.ServerError(code, {"error": {"code": code, "message": "high demand", "status": "UNAVAILABLE"}})


def _client_error(code: int = 429):
    from google.genai import errors

    return errors.ClientError(code, {"error": {"code": code, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})


class CallGeminiRetryTests(unittest.TestCase):
    def _run(self, side_effect):
        client = mock.MagicMock()
        client.models.generate_content.side_effect = side_effect
        with mock.patch("google.genai.Client", return_value=client), \
             mock.patch.object(consolidate, "GEMINI_API_KEY", "key"), \
             mock.patch.object(consolidate.time, "sleep") as sleep:
            try:
                result = consolidate._call_gemini(PENDING, [])
            except Exception as e:  # noqa: BLE001 - the test inspects what was raised
                result = e
        return result, client.models.generate_content.call_count, sleep

    def test_transient_503_is_retried_until_it_succeeds(self):
        ok = mock.MagicMock(text='{"operations": [{"op": "add", "text": "x"}]}')
        result, calls, sleep = self._run([_server_error(), _server_error(), ok])
        self.assertEqual(result, [{"op": "add", "text": "x"}])
        self.assertEqual(calls, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_persistent_503_gives_up_and_raises(self):
        result, calls, _ = self._run([_server_error()] * consolidate._MAX_ATTEMPTS)
        self.assertIsInstance(result, Exception)
        self.assertEqual(calls, consolidate._MAX_ATTEMPTS)

    def test_a_429_is_not_retried(self):
        result, calls, sleep = self._run([_client_error(429)])
        self.assertIsInstance(result, Exception)
        self.assertEqual(calls, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
