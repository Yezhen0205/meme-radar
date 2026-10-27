from __future__ import annotations

import unittest
from datetime import datetime, timezone

from gallery.collectors import SourceResult
from gallery.health import update_health
from tests.test_gallery_dedupe import sample


NOW = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)


class HealthTests(unittest.TestCase):
    def test_three_consecutive_blocked_runs_raise_alert(self):
        previous = {
            "sources": {
                "reddit": {"consecutive_failures": 2, "last_success_at": None},
                "tieba": {"consecutive_failures": 0, "last_success_at": None},
            },
            "history": [],
        }
        results = {
            "reddit": SourceResult("reddit", "blocked", error="403"),
            "tieba": SourceResult("tieba", "degraded", [sample()]),
        }
        health = update_health(previous, results, "ok", [sample()], now=NOW, planned=["x"])
        self.assertEqual(health["sources"]["reddit"]["consecutive_failures"], 3)
        self.assertTrue(any("连续 3 轮" in alert for alert in health["alerts"]))
        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["sources"]["x"]["status"], "planned")

    def test_no_items_is_blocked(self):
        results = {
            "reddit": SourceResult("reddit", "blocked", error="403"),
            "tieba": SourceResult("tieba", "blocked", error="403"),
        }
        health = update_health({}, results, "blocked", [], now=NOW)
        self.assertEqual(health["status"], "blocked")
        self.assertTrue(health["alerts"])

    def test_success_resets_failure_counter(self):
        previous = {"sources": {"reddit": {"consecutive_failures": 4}}, "history": []}
        results = {
            "reddit": SourceResult("reddit", "ok", [sample(source="reddit")]),
            "tieba": SourceResult("tieba", "degraded", [sample()]),
        }
        health = update_health(previous, results, "ok", [sample()], now=NOW)
        self.assertEqual(health["sources"]["reddit"]["consecutive_failures"], 0)


if __name__ == "__main__":
    unittest.main()
