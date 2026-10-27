from __future__ import annotations

import unittest

from gallery.collectors.trends import extract_keywords


class TrendTests(unittest.TestCase):
    def test_extracts_repeated_entity_without_fragments(self):
        keywords = extract_keywords(
            [
                "姆巴佩道歉",
                "姆巴佩致歉",
                "西甲官方致歉",
                "图吧垃圾佬",
                "图吧年度捡漏",
            ],
            limit=12,
        )
        words = [entry["word"] for entry in keywords]
        self.assertIn("姆巴佩", words)
        self.assertIn("图吧", words)
        self.assertNotIn("姆巴", words)
        self.assertNotIn("交部回应", words)
        for entry in keywords:
            self.assertGreaterEqual(entry["count"], 2)


if __name__ == "__main__":
    unittest.main()
