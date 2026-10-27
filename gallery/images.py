"""Image validation and perceptual hashing (dHash)."""
from __future__ import annotations

import io
import logging
from typing import Any


LOGGER = logging.getLogger("meme_radar.gallery.images")


def magic_image(data: bytes) -> str | None:
    if not data or len(data) < 12:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in {b"ftypavif", b"ftypavis"}:
        return "image/avif"
    return None


def image_is_valid(data: bytes, content_type: str = "") -> bool:
    detected = magic_image(data)
    if detected:
        return True
    return content_type.lower().startswith("image/") and len(data) > 64


def dhash(data: bytes, hash_size: int = 8) -> str | None:
    """Generate a 64-bit difference hash; null if Pillow cannot decode."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        grayscale = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        try:
            pixels = list(grayscale.get_flattened_data())
        except AttributeError:
            pixels = list(grayscale.getdata())
        bits = 0
        for row in range(hash_size):
            offset = row * (hash_size + 1)
            for column in range(hash_size):
                bits = (bits << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
        return f"{bits:0{hash_size * hash_size // 4}x}"
    except Exception as exc:
        LOGGER.warning("dhash failed: %s", exc)
        return None


def image_dimensions(data: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image
    except ImportError:
        return None, None
    try:
        image = Image.open(io.BytesIO(data))
        return int(image.width), int(image.height)
    except Exception:
        return None, None


def hamming_distance(left: str | None, right: str | None) -> int:
    if not left or not right:
        return 999
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError:
        return 999


def enrich_with_hash(item: dict, data: bytes) -> None:
    width, height = image_dimensions(data)
    item["image_width"] = width
    item["image_height"] = height
    item["image_hash"] = dhash(data)
    item["image_status"] = "ok"
    item["image_error"] = None
