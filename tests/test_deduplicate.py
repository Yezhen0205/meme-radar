from __future__ import annotations

import unittest

from collector.deduplicate import deduplicate, stabilize_collected_at
from tests.test_normalize import item


class DeduplicateTests(unittest.TestCase):
    def test_exact_title_across_sources_is_grouped(self):
        first = item(
            "央视叫停涉姆巴佩赛事和广告",
            source_id="weibo_hot",
            source_name="微博热搜",
            native_id="a",
            url="https://s.weibo.com/weibo?q=1",
        )
        second = item(
            "央视叫停涉姆巴佩赛事和广告",
            source_id="toutiao_hot",
            source_name="头条热榜",
            native_id="b",
            url="https://www.toutiao.com/trending/1",
        )
        result, stats = deduplicate([first, second], max_items=100)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["group_size"], 2)
        self.assertEqual(len(result[0]["related"]), 1)
        self.assertEqual(stats["duplicates_removed"], 0)

    def test_tracking_url_is_exact_duplicate(self):
        first = item("同一标题", native_id="a", url="https://example.com/a?utm_source=x")
        second = item("另一标题", native_id="b", url="https://example.com/a")
        result, stats = deduplicate([first, second], max_items=100)
        self.assertEqual(len(result), 1)
        self.assertEqual(stats["duplicates_removed"], 1)

    def test_same_comment_text_in_different_videos_is_kept(self):
        first = item(
            "笑死我了",
            source_id="bilibili_comments",
            source_name="B站评论",
            source_kind="comment",
            category="comment",
            native_id="1",
            context_id="BV1",
            context="视频一",
            url="https://www.bilibili.com/video/BV1#reply1",
        )
        second = item(
            "笑死我了",
            source_id="bilibili_comments",
            source_name="B站评论",
            source_kind="comment",
            category="comment",
            native_id="2",
            context_id="BV2",
            context="视频二",
            url="https://www.bilibili.com/video/BV2#reply2",
        )
        result, _ = deduplicate([first, second], max_items=100)
        self.assertEqual(len(result), 2)

    def test_near_duplicate_long_title_is_grouped(self):
        first = item("央视全面叫停涉姆巴佩赛事和广告播出")
        second = item("央视全面叫停涉姆巴佩赛事和广告")
        result, _ = deduplicate([first, second], max_items=100)
        self.assertEqual(len(result), 1)
        self.assertGreaterEqual(result[0]["group_size"], 2)

    def test_stabilize_collected_at_reuses_unchanged_item_time(self):
        old = item("不变的内容")
        old["collected_at"] = "2026-10-01T00:00:00Z"
        new = item("不变的内容")
        stabilize_collected_at([new], [old])
        self.assertEqual(new["collected_at"], "2026-10-01T00:00:00Z")

        changed = item("不变的内容", heat_value=9999)
        stabilize_collected_at([changed], [old])
        self.assertNotEqual(changed["collected_at"], "2026-10-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
