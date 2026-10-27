from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from gallery.collectors.reddit import parse_rss
from gallery.collectors.tieba import _parse_thread_page


ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)


class RedditRssTests(unittest.TestCase):
    def test_parses_real_fixture_without_fabricating_metrics(self):
        text = (ROOT / "tests" / "fixtures" / "reddit_new.xml").read_text(encoding="utf-8")
        items, stats = parse_rss(text, now=NOW, max_age_hours=72)
        self.assertEqual(len(items), 1)
        self.assertEqual(stats["entries"], 2)
        self.assertEqual(stats["no_image"], 1)
        item = items[0]
        self.assertEqual(item["source"], "reddit")
        self.assertEqual(item["source_id"], "1xgrvst")
        self.assertEqual(item["community"], "r/okbuddyretard")
        self.assertEqual(item["score"], None)
        self.assertEqual(item["comment_count"], None)
        self.assertTrue(item["image_url"].startswith("https://i.redd.it/"))
        self.assertTrue(item["thumbnail_url"].startswith("https://preview.redd.it/"))
        self.assertTrue(item["post_url"].startswith("https://www.reddit.com/r/okbuddyretard/comments/"))

    def test_old_items_are_skipped_by_age(self):
        text = (ROOT / "tests" / "fixtures" / "reddit_new.xml").read_text(encoding="utf-8")
        items, stats = parse_rss(text, now=datetime(2027, 1, 1, tzinfo=timezone.utc), max_age_hours=72)
        self.assertEqual(items, [])
        self.assertEqual(stats["skipped_old"], 1)


class TiebaPageTests(unittest.TestCase):
    def test_maps_thread_to_real_image_and_post(self):
        page = (ROOT / "tests" / "fixtures" / "tieba_topic.html").read_text(encoding="utf-8")
        items = _parse_thread_page(
            page,
            topic={"topic_id": 1, "topic_name": "表情包大赛"},
            now=NOW,
            max_threads=10,
        )
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first["source"], "tieba")
        self.assertEqual(first["source_id"], "11127645792")
        self.assertEqual(first["post_url"], "https://tieba.baidu.com/p/11127645792")
        self.assertEqual(first["comment_count"], 247)
        self.assertEqual(first["score"], None)
        self.assertEqual(first["community"], "deepseek吧")
        self.assertIn("w%3D580", first["image_url"])
        self.assertIn("谁才是表情包顶流", first["tags"])

    def test_thread_without_image_is_skipped(self):
        page = (ROOT / "tests" / "fixtures" / "tieba_topic.html").read_text(encoding="utf-8")
        items = _parse_thread_page(page, topic={"topic_name": "梗"}, now=NOW, max_threads=10)
        self.assertNotIn("没有图片的帖子", [item["title"] for item in items])


if __name__ == "__main__":
    unittest.main()
