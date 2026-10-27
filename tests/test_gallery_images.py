from __future__ import annotations

import io
import unittest

from PIL import Image

from gallery.images import dhash, hamming_distance, image_dimensions, image_is_valid, magic_image


def png_bytes(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buffer, format="PNG")
    return buffer.getvalue()


class ImageTests(unittest.TestCase):
    def test_magic_and_dimensions(self):
        data = png_bytes((20, 40, 60))
        self.assertEqual(magic_image(data), "image/png")
        self.assertTrue(image_is_valid(data, "image/png"))
        self.assertEqual(image_dimensions(data), (32, 24))

    def test_dhash_and_distance(self):
        first = dhash(png_bytes((0, 0, 0)))
        second = dhash(png_bytes((255, 255, 255)))
        self.assertEqual(len(first), 16)
        self.assertEqual(len(second), 16)
        self.assertEqual(hamming_distance(first, first), 0)
        self.assertGreaterEqual(hamming_distance(first, second), 0)

    def test_html_is_not_an_image(self):
        self.assertFalse(image_is_valid(b"<!doctype html><html>blocked</html>", "text/html"))
        self.assertIsNone(magic_image(b"not an image"))


if __name__ == "__main__":
    unittest.main()
