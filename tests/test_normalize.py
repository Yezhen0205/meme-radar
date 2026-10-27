from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from collector.normalize import (
    canonical_url,
    clean_comment,
    clean_text,
    format_heat,
    make_item,
    split_title_summary,
)


NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def item(
    title: str,
    *,
    source_id: str = "weibo_hot",
    source_name: str = "微博热搜",
    source_kind: str = "hot",
    category: str = "hot",
    url: str | None = None,
    native_id: str | None = None,
    context_id: str | None = None,
    context: str | None = None,
    heat_value: int = 1000,
    summary: str = "测试摘要",
) -> dict:
    return make_item(
        source_id=source_id,
        source_name=source_name,
        source_kind=source_kind,
        native_id=native_id or title,
        title=title,
        summary=summary,
        url=url or f"https://example.com/{abs(hash(title))}",
        collected_at=NOW,
        published_at=NOW - timedelta(hours=1),
        category=category,
        context_id=context_id,
        context=context,
        heat_label="热度",
        heat_value=heat_value,
        heat_rank=1,
    )


class NormalizeTests(unittest.TestCase):
    def test_canonical_url_strips_tracking_and_www(self):
        url = "http://www.example.com/a/?utm_source=x&spm_id_from=1&id=3#reply9"
        self.assertEqual(canonical_url(url), "https://example.com/a/?id=3#reply9")

    def test_canonical_url_keeps_comment_anchor(self):
        url = "https://www.bilibili.com/video/BV1x/#reply123"
        self.assertTrue(canonical_url(url).endswith("#reply123"))

    def test_clean_comment_redacts_contact_details(self):
        value = "联系我 13800138000 或 a@b.com [doge]  https://spam.example/x"
        cleaned = clean_comment(value)
        self.assertNotIn("13800138000", cleaned)
        self.assertNotIn("a@b.com", cleaned)
        self.assertNotIn("https://spam.example", cleaned)

    def test_clean_text_collapses_and_truncates(self):
        self.assertEqual(clean_text("<b>你好</b>\n\n世界"), "你好 世界")
        self.assertTrue(clean_text("x" * 20, max_len=10).endswith("…"))

    def test_format_heat(self):
        self.assertEqual(format_heat(999), "999")
        self.assertEqual(format_heat(12_345), "1.2万")
        self.assertEqual(format_heat(120_000_000), "1.2亿")

    def test_split_title_summary(self):
        title, summary = split_title_summary("一二三四五六七八九十", title_len=6)
        self.assertTrue(title.endswith("…"))
        self.assertTrue(summary)

    def test_make_item_has_no_fabricated_heat(self):
        result = make_item(
            source_id="x",
            source_name="X",
            source_kind="hot",
            title="标题",
            url="https://example.com/a",
            collected_at=NOW,
        )
        self.assertIsNone(result["heat"])
        self.assertEqual(result["rank"], 1)


if __name__ == "__main__":
    unittest.main()
