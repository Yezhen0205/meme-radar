#!/usr/bin/env python3
"""Validate data/feed.json and stage a compact copy for GitHub Pages."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.normalize import parse_iso  # noqa: E402


DEFAULT_FEED = ROOT / "data" / "feed.json"
SITE_FEED = ROOT / "site" / "data" / "feed.json"
CATEGORIES = {"meme", "reply", "comment", "hot"}
KINDS = {"hot", "video", "article", "comment", "reply"}


def validate_feed(feed: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(feed, dict):
        return ["feed root is not an object"]
    if feed.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(feed.get("items"), list):
        return errors + ["items must be an array"]
    if not isinstance(feed.get("sources"), list):
        errors.append("sources must be an array")
    items = feed["items"]
    if not items:
        errors.append("items is empty")
    settings = feed.get("settings") or {}
    max_items = int(settings.get("max_items", 0) or 0)
    if max_items and len(items) > max_items:
        errors.append(f"items ({len(items)}) exceeds max_items ({max_items})")
    generated_at = feed.get("generated_at")
    if generated_at and parse_iso(generated_at) is None:
        errors.append("generated_at is not ISO-8601")
    if not generated_at and items:
        errors.append("generated_at is required when items exist")
    source_ids = {
        source.get("id")
        for source in feed.get("sources", [])
        if isinstance(source, dict) and source.get("id")
    }
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} is not an object")
            continue
        for field in (
            "id",
            "fingerprint",
            "title",
            "source_id",
            "source_name",
            "source_kind",
            "url",
            "category",
            "rank",
            "group_size",
            "related",
        ):
            if field not in item:
                errors.append(f"{prefix} missing {field}")
        item_id = str(item.get("id") or "")
        if not item_id:
            errors.append(f"{prefix} has empty id")
        elif item_id in seen_ids:
            errors.append(f"{prefix} duplicate id {item_id}")
        seen_ids.add(item_id)
        if item.get("source_id") and item["source_id"] not in source_ids:
            errors.append(f"{prefix} unknown source_id {item['source_id']}")
        if item.get("category") not in CATEGORIES:
            errors.append(f"{prefix} invalid category {item.get('category')!r}")
        if item.get("source_kind") not in KINDS:
            errors.append(f"{prefix} invalid source_kind {item.get('source_kind')!r}")
        title = str(item.get("title") or "").strip()
        if not title:
            errors.append(f"{prefix} empty title")
        url = str(item.get("url") or "")
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            errors.append(f"{prefix} invalid URL {url!r}")
        if item.get("published_at") and parse_iso(item["published_at"]) is None:
            errors.append(f"{prefix} invalid published_at")
        rank = item.get("rank")
        if not isinstance(rank, int) or rank < 1:
            errors.append(f"{prefix} rank must be a positive integer")
        heat = item.get("heat")
        if heat is not None:
            if not isinstance(heat, dict):
                errors.append(f"{prefix} heat must be null or an object")
            else:
                if not str(heat.get("label") or "").strip():
                    errors.append(f"{prefix} heat.label is empty")
                if not isinstance(heat.get("value"), int) or heat["value"] < 0:
                    errors.append(f"{prefix} heat.value must be a non-negative integer")
                if not str(heat.get("display") or "").strip():
                    errors.append(f"{prefix} heat.display is empty")
                if heat.get("rank") != rank:
                    errors.append(f"{prefix} heat.rank must equal item rank")
        related = item.get("related")
        group_size = item.get("group_size")
        if not isinstance(related, list):
            errors.append(f"{prefix} related must be an array")
        else:
            if len(related) > 4:
                errors.append(f"{prefix} related exceeds 4 entries")
            for related_index, entry in enumerate(related):
                if not isinstance(entry, dict):
                    errors.append(f"{prefix}.related[{related_index}] is not an object")
                    continue
                if not entry.get("title") or not entry.get("url") or not entry.get("source_name"):
                    errors.append(f"{prefix}.related[{related_index}] is missing fields")
        if not isinstance(group_size, int) or group_size < 1:
            errors.append(f"{prefix} group_size must be a positive integer")
        elif isinstance(related, list) and group_size < len(related) + 1:
            errors.append(f"{prefix} group_size is smaller than related")
    return errors


def load_feed(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("feed root is not an object")
    return data


def stage(feed: dict, destination: Path = SITE_FEED) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        json.dumps(feed, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and stage Meme Radar feed")
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--stage", action="store_true", help="write compact site/data/feed.json")
    parser.add_argument("--check", action="store_true", help="fail on validation errors")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    feed = load_feed(args.feed)
    errors = validate_feed(feed)
    if args.summary:
        run = feed.get("run") or {}
        print(
            json.dumps(
                {
                    "items": len(feed.get("items", [])),
                    "generated_at": feed.get("generated_at"),
                    "sources_ok": run.get("sources_ok"),
                    "sources_failed": run.get("sources_failed"),
                    "stale": feed.get("stale"),
                },
                ensure_ascii=False,
            )
        )
    if errors:
        for error in errors[:40]:
            print(f"ERROR: {error}", file=sys.stderr)
        if len(errors) > 40:
            print(f"ERROR: ... and {len(errors) - 40} more", file=sys.stderr)
        return 1
    if args.stage:
        stage(feed)
        print(f"staged {len(feed.get('items', []))} items -> {SITE_FEED}")
    if args.check:
        print(f"feed valid: {len(feed.get('items', []))} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
