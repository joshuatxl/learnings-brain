import json
import unittest

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


if __name__ == "__main__":
    unittest.main()
