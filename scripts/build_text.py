#!/usr/bin/env python3
"""Validate data/text.json and stage a compact copy for the unified site."""
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


DEFAULT_TEXT = ROOT / "data" / "text.json"
SITE_TEXT = ROOT / "site" / "data" / "text.json"
CATEGORIES = {"meme", "abstract", "reply", "comment", "hot"}
AUTHENTICITY = {"real", "rewrite", "ai"}


def validate(feed: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(feed, dict):
        return ["text root is not an object"]
    if feed.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    if feed.get("content_kind") != "text":
        errors.append("content_kind must be text")
    items = feed.get("items")
    if not isinstance(items, list):
        return errors + ["items must be an array"]
    if not items:
        errors.append("items is empty")
    if not feed.get("generated_at") or parse_iso(feed.get("generated_at")) is None:
        errors.append("generated_at is invalid or missing")
    seen: set[str] = set()
    counts = {category: 0 for category in CATEGORIES}
    authenticity = {key: 0 for key in AUTHENTICITY}
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} is not an object")
            continue
        for field in ("id", "content_type", "authenticity", "category", "title", "source_name", "url", "collected_at"):
            if field not in item:
                errors.append(f"{prefix} missing {field}")
        item_id = str(item.get("id") or "")
        if not item_id:
            errors.append(f"{prefix} empty id")
        elif item_id in seen:
            errors.append(f"{prefix} duplicate id {item_id}")
        seen.add(item_id)
        if item.get("content_type") != "text":
            errors.append(f"{prefix} content_type must be text")
        if item.get("authenticity") not in AUTHENTICITY:
            errors.append(f"{prefix} invalid authenticity {item.get('authenticity')!r}")
        else:
            authenticity[item["authenticity"]] += 1
        category = item.get("category")
        if category not in CATEGORIES:
            errors.append(f"{prefix} invalid category {category!r}")
        else:
            counts[category] += 1
        if not str(item.get("title") or "").strip():
            errors.append(f"{prefix} empty title")
        url = str(item.get("url") or "")
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            errors.append(f"{prefix} invalid url")
        if not item.get("source_name"):
            errors.append(f"{prefix} missing source_name")
        if not item.get("collected_at") or parse_iso(item["collected_at"]) is None:
            errors.append(f"{prefix} invalid collected_at")
        if item.get("published_at") and parse_iso(item["published_at"]) is None:
            errors.append(f"{prefix} invalid published_at")
        if item.get("content_type") == "text" and item.get("authenticity") == "ai":
            # AI is allowed only with an explicit marker; it is counted and
            # displayed separately, never presented as a real comment.
            if not item.get("ai_generated"):
                errors.append(f"{prefix} ai item must carry ai_generated=true")
    run = feed.get("run") or {}
    if run.get("categories") and run["categories"] != {key: value for key, value in counts.items() if value}:
        errors.append("run.categories does not match item categories")
    if run.get("authenticity") and run["authenticity"] != authenticity:
        errors.append("run.authenticity does not match items")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and stage Meme Radar text feed")
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    feed = json.loads(args.text.read_text(encoding="utf-8"))
    errors = validate(feed)
    if args.summary:
        run = feed.get("run") or {}
        print(
            json.dumps(
                {
                    "items": len(feed.get("items", [])),
                    "categories": run.get("categories"),
                    "authenticity": run.get("authenticity"),
                    "generated_at": feed.get("generated_at"),
                    "sources": [
                        {"id": source.get("id"), "status": source.get("status"), "accepted": source.get("accepted")}
                        for source in feed.get("sources", [])
                    ],
                },
                ensure_ascii=False,
            )
        )
    if errors:
        for error in errors[:40]:
            print("ERROR:", error, file=sys.stderr)
        return 1
    if args.stage:
        SITE_TEXT.parent.mkdir(parents=True, exist_ok=True)
        SITE_TEXT.write_text(
            json.dumps(feed, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"staged {len(feed.get('items', []))} text items -> {SITE_TEXT}")
    if args.check:
        print(f"text valid: {len(feed.get('items', []))} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
