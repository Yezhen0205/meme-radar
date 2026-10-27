from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from collector.collect import collect
from collector.http import FetchError, HttpClient
from tests.test_normalize import item


NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
PREVIOUS_TIME = NOW - timedelta(hours=2)


def config_for(*source_ids: str) -> dict:
    return {
        "version": 1,
        "timezone": "Asia/Shanghai",
        "request": {
            "timeout_seconds": 2,
            "retries": 0,
            "backoff_seconds": 0,
            "min_interval_seconds": 0,
        },
        "feed": {"max_items": 50, "retention_hours": 168, "today_hours": 24},
        "sources": [
            {
                "id": source_id,
                "name": source_id,
                "adapter": "weibo_hot",
                "enabled": True,
            }
            for source_id in source_ids
        ],
    }


def previous_feed(*items: dict, source_id: str = "weibo_hot") -> dict:
    return {
        "schema_version": 1,
        "generated_at": "2026-10-27T08:00:00Z",
        "checked_at": "2026-10-27T08:00:00Z",
        "stale": False,
        "stale_reason": None,
        "run": {
            "ok": True,
            "partial": False,
            "sources_ok": 1,
            "sources_failed": 0,
        },
        "settings": {"max_items": 50, "retention_hours": 168, "today_hours": 24},
        "sources": [
            {
                "id": source_id,
                "name": source_id,
                "status": "ok",
                "fetched": len(items),
                "accepted": len(items),
                "retained": 0,
                "error": None,
                "duration_ms": 1,
                "last_success_at": "2026-10-27T08:00:00Z",
                "last_attempt_at": "2026-10-27T08:00:00Z",
                "using_previous": False,
            }
        ],
        "items": list(items),
    }


class CollectMergeTests(unittest.TestCase):
    def test_all_sources_fail_keeps_previous_items(self):
        old_item = item("旧数据", native_id="old")
        old_item["collected_at"] = PREVIOUS_TIME.isoformat().replace("+00:00", "Z")
        previous = previous_feed(old_item)
        client = HttpClient(timeout=1, retries=0, min_interval=0)

        with patch("collector.collect._source_collector", side_effect=FetchError("blocked")):
            feed, code = collect(
                config_for("weibo_hot"),
                previous,
                now=NOW,
                client=client,
            )

        self.assertEqual(code, 0)
        self.assertTrue(feed["stale"])
        self.assertFalse(feed["run"]["ok"])
        self.assertEqual(feed["generated_at"], previous["generated_at"])
        self.assertEqual(len(feed["items"]), 1)
        self.assertEqual(feed["items"][0]["title"], "旧数据")
        self.assertTrue(feed["items"][0]["source_stale"])
        self.assertTrue(feed["sources"][0]["using_previous"])
        self.assertEqual(feed["sources"][0]["retained"], 1)

    def test_first_run_all_fail_is_empty_and_exit_one(self):
        client = HttpClient(timeout=1, retries=0, min_interval=0)
        with patch("collector.collect._source_collector", side_effect=FetchError("blocked")):
            feed, code = collect(config_for("weibo_hot"), None, now=NOW, client=client)
        self.assertEqual(code, 1)
        self.assertEqual(feed["items"], [])
        self.assertIsNone(feed["generated_at"])
        self.assertTrue(feed["stale"])
        self.assertIn("首次", feed["stale_reason"])

    def test_partial_failure_keeps_only_failed_sources_previous_items(self):
        new_item = item("今天的新内容", native_id="new")
        old_item = item("旧内容", source_id="baidu_hot", source_name="百度热搜")
        old_item["source_id"] = "baidu_hot"
        old_item["collected_at"] = PREVIOUS_TIME.isoformat().replace("+00:00", "Z")
        previous = previous_feed(old_item, source_id="baidu_hot")
        previous["sources"].append(
            {
                "id": "weibo_hot",
                "name": "weibo_hot",
                "status": "ok",
                "fetched": 0,
                "accepted": 0,
                "retained": 0,
                "error": None,
                "duration_ms": 1,
                "last_success_at": "2026-10-27T08:00:00Z",
                "last_attempt_at": "2026-10-27T08:00:00Z",
                "using_previous": False,
            }
        )
        client = HttpClient(timeout=1, retries=0, min_interval=0)

        def fake(source, _client, _now, _context):
            if source["id"] == "weibo_hot":
                return [new_item]
            raise FetchError("blocked")

        with patch("collector.collect._source_collector", side_effect=fake):
            feed, code = collect(
                config_for("weibo_hot", "baidu_hot"),
                previous,
                now=NOW,
                client=client,
            )

        self.assertEqual(code, 0)
        self.assertFalse(feed["stale"])
        self.assertTrue(feed["run"]["partial"])
        self.assertEqual({item["title"] for item in feed["items"]}, {"今天的新内容", "旧内容"})
        self.assertEqual(feed["run"]["sources_failed"], 1)
        self.assertEqual(feed["run"]["sources_using_previous"], 1)

    def test_unchanged_second_run_reuses_previous_feed_object(self):
        new_item = item("稳定的内容", native_id="stable")
        client = HttpClient(timeout=1, retries=0, min_interval=0)

        def fake(_source, _client, now, _context):
            value = item("稳定的内容", native_id="stable")
            value["collected_at"] = now.isoformat().replace("+00:00", "Z")
            return [value]

        with patch("collector.collect._source_collector", side_effect=fake):
            first, _ = collect(config_for("weibo_hot"), None, now=NOW, client=client)
            second, _ = collect(config_for("weibo_hot"), first, now=NOW + timedelta(hours=6), client=client)

        self.assertIs(second, first)


class BuildFeedTests(unittest.TestCase):
    def test_valid_feed_passes(self):
        from scripts.build_feed import validate_feed

        value = item("有效标题")
        feed = previous_feed(value)
        self.assertEqual(validate_feed(feed), [])

    def test_invalid_feed_is_rejected(self):
        from scripts.build_feed import validate_feed

        errors = validate_feed(
            {
                "schema_version": 1,
                "generated_at": "not-a-date",
                "sources": [],
                "items": [{"id": "x"}],
            }
        )
        self.assertTrue(errors)
        self.assertTrue(any("invalid URL" in error or "missing" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
