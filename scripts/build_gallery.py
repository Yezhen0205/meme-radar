#!/usr/bin/env python3
"""Validate data/gallery.json and stage a compact Pages payload."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gallery.models import parse_iso  # noqa: E402


DEFAULT_GALLERY = ROOT / "data" / "gallery.json"
DEFAULT_HEALTH = ROOT / "data" / "health.json"
SITE_GALLERY = ROOT / "site" / "data" / "gallery.json"
SITE_HEALTH = ROOT / "site" / "data" / "health.json"
SOURCES = {"reddit", "tieba"}
HEX64 = re.compile(r"^[0-9a-f]{16}$")


def validate_feed(feed: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(feed, dict):
        return ["gallery root is not an object"]
    if feed.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    items = feed.get("items")
    if not isinstance(items, list):
        return errors + ["items must be an array"]
    if not items:
        errors.append("items is empty")
    if feed.get("generated_at") and parse_iso(feed["generated_at"]) is None:
        errors.append("generated_at is invalid")
    if not feed.get("generated_at") and items:
        errors.append("generated_at is required when items exist")
    settings = feed.get("settings") or {}
    max_items = int(settings.get("max_items", 0) or 0)
    if max_items and len(items) > max_items:
        errors.append(f"items ({len(items)}) exceeds max_items ({max_items})")
    source_status = {entry.get("source"): entry for entry in feed.get("sources", []) if isinstance(entry, dict)}
    for required in ("reddit", "tieba"):
        if required not in source_status:
            errors.append(f"missing source status: {required}")
    seen: set[str] = set()
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} is not an object")
            continue
        for field in (
            "id",
            "source",
            "source_id",
            "source_name",
            "community",
            "title",
            "post_url",
            "image_url",
            "thumbnail_url",
            "images",
            "created_at",
            "collected_at",
            "score",
            "comment_count",
            "tags",
            "content_hash",
            "image_hash",
            "image_status",
            "status",
            "rank_score",
        ):
            if field not in item:
                errors.append(f"{prefix} missing {field}")
        item_id = str(item.get("id") or "")
        if not item_id:
            errors.append(f"{prefix} has empty id")
        elif item_id in seen:
            errors.append(f"{prefix} duplicate id {item_id}")
        seen.add(item_id)
        source = item.get("source")
        if source not in SOURCES:
            errors.append(f"{prefix} invalid source {source!r}")
        post_url = str(item.get("post_url") or "")
        post_parts = urlsplit(post_url)
        if post_parts.scheme not in {"http", "https"} or not post_parts.netloc:
            errors.append(f"{prefix} invalid post_url")
        elif source == "reddit" and "reddit.com" not in post_parts.netloc:
            errors.append(f"{prefix} Reddit post URL is not reddit.com")
        elif source == "tieba" and "tieba.baidu.com" not in post_parts.netloc:
            errors.append(f"{prefix} Tieba post URL is not tieba.baidu.com")
        image_parts = urlsplit(str(item.get("image_url") or ""))
        if image_parts.scheme not in {"http", "https"} or not image_parts.netloc:
            errors.append(f"{prefix} invalid image_url")
        if not str(item.get("title") or "").strip():
            errors.append(f"{prefix} empty title")
        if item.get("score") is not None and (not isinstance(item["score"], int) or item["score"] < 0):
            errors.append(f"{prefix} score must be null or non-negative integer")
        if item.get("comment_count") is not None and (
            not isinstance(item["comment_count"], int) or item["comment_count"] < 0
        ):
            errors.append(f"{prefix} comment_count must be null or non-negative integer")
        if item.get("image_status") not in {"ok", "broken", "unchecked"}:
            errors.append(f"{prefix} invalid image_status")
        if item.get("status") not in {"active", "image_broken"}:
            errors.append(f"{prefix} invalid status")
        if item.get("image_hash") is not None and not HEX64.match(str(item["image_hash"])):
            errors.append(f"{prefix} invalid image_hash")
        if item.get("created_at") and parse_iso(item["created_at"]) is None:
            errors.append(f"{prefix} invalid created_at")
        if not item.get("collected_at") or parse_iso(item["collected_at"]) is None:
            errors.append(f"{prefix} invalid collected_at")
        if not item.get("content_hash"):
            errors.append(f"{prefix} missing content_hash")
        if not isinstance(item.get("images"), list) or not item["images"]:
            errors.append(f"{prefix} images must be a non-empty array")
        if item.get("source") in SOURCES and item.get("image_status") == "ok" and not item.get("image_checked_at"):
            errors.append(f"{prefix} verified image must have image_checked_at")
    health = feed.get("health") or {}
    if health.get("status") not in {"ok", "degraded", "blocked"}:
        errors.append("health.status invalid")
    if not isinstance(health.get("sources"), dict):
        errors.append("health.sources must be an object")
    return errors


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} root is not an object")
    return value


def stage(feed: dict, health: dict) -> None:
    SITE_GALLERY.parent.mkdir(parents=True, exist_ok=True)
    SITE_GALLERY.write_text(
        json.dumps(feed, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    SITE_HEALTH.write_text(
        json.dumps(health, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and stage Meme Radar gallery")
    parser.add_argument("--gallery", type=Path, default=DEFAULT_GALLERY)
    parser.add_argument("--health", type=Path, default=DEFAULT_HEALTH)
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    feed = load_json(args.gallery)
    health = load_json(args.health)
    errors = validate_feed(feed)
    if args.summary:
        run = feed.get("run") or {}
        print(
            json.dumps(
                {
                    "items": len(feed.get("items", [])),
                    "generated_at": feed.get("generated_at"),
                    "health": (feed.get("health") or {}).get("status"),
                    "new": run.get("items_new"),
                    "broken_images": run.get("images_broken"),
                    "sources": [
                        {"source": source.get("source"), "status": source.get("status")}
                        for source in feed.get("sources", [])
                    ],
                },
                ensure_ascii=False,
            )
        )
    if errors:
        for error in errors[:50]:
            print(f"ERROR: {error}", file=sys.stderr)
        if len(errors) > 50:
            print(f"ERROR: ... and {len(errors) - 50} more", file=sys.stderr)
        return 1
    if args.stage:
        stage(feed, health)
        print(f"staged {len(feed.get('items', []))} items -> {SITE_GALLERY}")
    if args.check:
        print(f"gallery valid: {len(feed.get('items', []))} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
