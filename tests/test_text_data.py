from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.build_text import validate as validate_text


ROOT = Path(__file__).resolve().parent.parent


class TextDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = json.loads((ROOT / "data" / "text.json").read_text(encoding="utf-8"))
        cls.gallery = json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8"))

    def test_text_feed_schema_and_authenticity(self):
        self.assertEqual(self.text["schema_version"], 2)
        self.assertEqual(self.text["content_kind"], "text")
        self.assertEqual(validate_text(self.text), [])
        self.assertGreater(len(self.text["items"]), 0)
        self.assertTrue(all(item["content_type"] == "text" for item in self.text["items"]))
        self.assertTrue(all(item["authenticity"] in {"real", "rewrite", "ai"} for item in self.text["items"]))
        self.assertIn("real", self.text["run"]["authenticity"])
        self.assertEqual(
            self.text["run"]["authenticity"]["real"] + self.text["run"]["authenticity"]["rewrite"] + self.text["run"]["authenticity"]["ai"],
            len(self.text["items"]),
        )

    def test_required_text_categories_have_real_content(self):
        categories = {item["category"] for item in self.text["items"]}
        self.assertTrue({"meme", "abstract", "reply", "comment", "hot"}.issubset(categories))
        for category in ("meme", "abstract", "reply", "comment", "hot"):
            self.assertGreaterEqual(sum(1 for item in self.text["items"] if item["category"] == category), 1)

    def test_gallery_items_are_marked_as_real_images(self):
        self.assertGreater(len(self.gallery["items"]), 0)
        for item in self.gallery["items"]:
            self.assertEqual(item.get("content_type"), "image")
            self.assertEqual(item.get("authenticity"), "real")

    def test_text_and_image_ids_do_not_collide(self):
        text_ids = {f"text:{item['id']}" for item in self.text["items"]}
        image_ids = {f"image:{item['id']}" for item in self.gallery["items"]}
        self.assertFalse(text_ids & image_ids)


if __name__ == "__main__":
    unittest.main()
