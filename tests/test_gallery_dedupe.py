from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from gallery.collectors import SourceResult
from gallery.dedupe import merge_and_rank
from gallery.models import make_item


NOW = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)


def sample(
    source: str = "tieba",
    source_id: str = "1",
    title: str = "测试梗图",
    image_url: str = "https://tiebapic.baidu.com/forum/test.jpg",
    image_hash: str | None = "abcdabcdabcdabcd",
    created_at: datetime | None = NOW - timedelta(hours=1),
    comment_count: int | None = 12,
) -> dict:
    item = make_item(
        source=source,
        source_name="百度贴吧" if source == "tieba" else "Reddit",
        source_id=source_id,
        community="deepseek吧" if source == "tieba" else "r/196",
        title=title,
        summary="测试摘要",
        post_url=(
            f"https://tieba.baidu.com/p/{source_id}"
            if source == "tieba"
            else f"https://www.reddit.com/r/196/comments/{source_id}/x/"
        ),
        image_url=image_url,
        thumbnail_url=image_url,
        images=[{"url": image_url, "thumbnail_url": image_url}],
        created_at=created_at,
        collected_at=NOW - timedelta(hours=1),
        score=None,
        comment_count=comment_count,
        tags=["测试"],
    )
    item["image_status"] = "ok"
    item["image_checked_at"] = NOW.isoformat()
    item["image_hash"] = image_hash
    return item


class MergeTests(unittest.TestCase):
    def test_failed_source_history_is_preserved(self):
        old = sample()
        results = {
            "reddit": SourceResult("reddit", "blocked", error="403"),
            "tieba": SourceResult("tieba", "blocked", error="403"),
        }
        items, stats = merge_and_rank([old], results, [], now=NOW)
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["source_stale"])
        self.assertEqual(stats["new"], 0)

    def test_same_image_across_sources_is_grouped(self):
        reddit = sample(source="reddit", source_id="r1", image_url="https://preview.redd.it/a.jpg")
        tieba = sample(source="tieba", source_id="t1", image_url="https://tiebapic.baidu.com/a.jpg")
        results = {
            "reddit": SourceResult("reddit", "ok", [reddit]),
            "tieba": SourceResult("tieba", "degraded", [tieba]),
        }
        items, stats = merge_and_rank([], results, [], now=NOW)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["group_size"], 2)
        self.assertEqual(len(items[0]["related"]), 1)
        self.assertEqual(items[0]["source"], "reddit")
        self.assertEqual(stats["groups"], 1)

    def test_same_post_url_is_not_duplicated(self):
        first = sample(source_id="same", title="一")
        second = sample(source_id="same", title="二")
        results = {"tieba": SourceResult("tieba", "degraded", [first, second])}
        items, _ = merge_and_rank([], results, [], now=NOW)
        self.assertEqual(len(items), 1)

    def test_new_items_are_counted_and_timestamp_stable(self):
        old = sample(source_id="old", image_hash="1111111111111111", image_url="https://tiebapic.baidu.com/old.jpg")
        new = sample(source_id="new", image_hash="2222222222222222", image_url="https://tiebapic.baidu.com/new.jpg")
        results = {"tieba": SourceResult("tieba", "degraded", [new])}
        items, stats = merge_and_rank([old], results, [], now=NOW)
        self.assertEqual(len(items), 2)
        self.assertEqual(stats["new"], 1)
        self.assertEqual(stats["updated"], 0)


if __name__ == "__main__":
    unittest.main()
