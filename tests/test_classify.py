from __future__ import annotations

import unittest

from collector.classify import classify_item


class ClassifyTests(unittest.TestCase):
    def test_funny_bilibili_category_is_meme(self):
        category, tags = classify_item(title="普通的一天", tname="搞笑", source_kind="video")
        self.assertEqual(category, "meme")
        self.assertIn("热梗", tags)

    def test_word_in_description_does_not_override_serious_title(self):
        category, _ = classify_item(
            title="旗舰手机芯片大横评",
            summary="今年有赢家，也有翻车严重的产品",
            tname="数码",
            source_kind="video",
        )
        self.assertEqual(category, "hot")

    def test_keyword_in_title_is_meme(self):
        category, _ = classify_item(title="这波操作太抽象了", source_kind="hot")
        self.assertEqual(category, "abstract")

    def test_abstract_category_is_distinct_from_general_meme(self):
        category, tags = classify_item(title="这波操作太抽象了", source_kind="hot")
        self.assertEqual(category, "abstract")
        self.assertIn("抽象", tags)

    def test_plain_funny_title_remains_meme(self):
        category, _ = classify_item(title="今天看到一个搞笑视频", source_kind="hot")
        self.assertEqual(category, "meme")

    def test_serious_hint_wins_over_single_keyword(self):
        category, _ = classify_item(
            title="外交部回应比赛翻车事件",
            tname="资讯",
            source_kind="hot",
        )
        self.assertEqual(category, "hot")


if __name__ == "__main__":
    unittest.main()
