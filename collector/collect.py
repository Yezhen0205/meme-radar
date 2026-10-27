"""Collect text hot lists, memes and comments into data/text.json."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .deduplicate import deduplicate, feed_signature, stabilize_collected_at
from .http import FetchError, HttpClient
from .normalize import age_hours, iso_utc, parse_iso, utc_now
from .sources import (
    ADAPTERS,
    adapter_names,
    collect_bilibili_comments,
    collect_bilibili_popular,
    fetch_bilibili_cookie,
)


LOGGER = logging.getLogger("meme_radar.collect")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "sources.json"
DEFAULT_OUTPUT = ROOT / "data" / "text.json"
SITE = {
    "name": "梗图雷达",
    "name_en": "Meme Radar",
    "tagline": "图片、热梗、抽象段子、神回复和热点，装进一部手机。",
}


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("config root must be an object")
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("config.sources must be a non-empty array")
    seen: set[str] = set()
    known = adapter_names()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("each source must be an object")
        source_id = source.get("id")
        if not source_id or source_id in seen:
            raise ValueError(f"duplicate or missing source id: {source_id!r}")
        seen.add(source_id)
        if source.get("adapter") not in known:
            raise ValueError(f"unknown adapter for {source_id}: {source.get('adapter')!r}")
    return config


def load_previous(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("feed root is not an object with items")
        return data
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.warning("cannot read previous feed %s: %s", path, exc)
        return None


def _source_collector(source: dict, client: HttpClient, now: datetime, context: dict):
    adapter = source["adapter"]
    if adapter == "bilibili_popular":
        items, videos = collect_bilibili_popular(
            source,
            client,
            now,
            cookie=context.get("bilibili_cookie"),
        )
        context["bilibili_videos"] = videos
        return items
    if adapter == "bilibili_comments":
        return collect_bilibili_comments(
            source,
            client,
            now,
            context.get("bilibili_videos") or [],
            cookie=context.get("bilibili_cookie"),
        )
    return ADAPTERS[adapter](source, client, now)


def _previous_items_for_source(previous: dict | None, source_id: str, now: datetime, retention_hours: int) -> list[dict]:
    if not previous:
        return []
    result = []
    for item in previous.get("items", []):
        if item.get("source_id") != source_id:
            continue
        if age_hours(item, now=now) <= retention_hours:
            result.append(dict(item))
    return result


def collect(
    config: dict,
    previous: dict | None = None,
    *,
    now: datetime | None = None,
    client: HttpClient | None = None,
) -> tuple[dict, int]:
    """Run all enabled sources. Returns ``(feed, exit_code)``."""
    started_monotonic = time.monotonic()
    now = now or utc_now()
    request_cfg = config.get("request") or {}
    client = client or HttpClient(
        timeout=float(request_cfg.get("timeout_seconds", 15)),
        retries=int(request_cfg.get("retries", 1)),
        backoff=float(request_cfg.get("backoff_seconds", 2.0)),
        min_interval=float(request_cfg.get("min_interval_seconds", 1.2)),
        user_agent=str(request_cfg.get("user_agent", "MemeRadar/1.0")),
    )
    feed_cfg = config.get("feed") or {}
    retention_hours = int(feed_cfg.get("retention_hours", 168))
    max_items = int(feed_cfg.get("max_items", 300))
    previous_sources = {
        source.get("id"): source for source in (previous or {}).get("sources", [])
    }
    previous_items = (previous or {}).get("items", [])
    statuses: list[dict] = []
    new_items: list[dict] = []
    by_source: dict[str, list[dict]] = {}
    context: dict[str, Any] = {}
    status_by_id: dict[str, dict] = {}

    if any(
        source.get("enabled", True) and str(source.get("adapter", "")).startswith("bilibili")
        for source in config["sources"]
    ):
        context["bilibili_cookie"] = fetch_bilibili_cookie(client)

    for source in config["sources"]:
        source_id = source["id"]
        status = {
            "id": source_id,
            "name": source.get("name", source_id),
            "adapter": source.get("adapter"),
            "status": "disabled",
            "fetched": 0,
            "accepted": 0,
            "retained": 0,
            "error": None,
            "duration_ms": 0,
            "last_success_at": (previous_sources.get(source_id) or {}).get("last_success_at"),
            "last_attempt_at": iso_utc(now),
            "using_previous": False,
        }
        if not source.get("enabled", True):
            statuses.append(status)
            status_by_id[source_id] = status
            continue
        depends_on = source.get("depends_on")
        if depends_on:
            dependency = status_by_id.get(depends_on)
            if not dependency or dependency["status"] != "ok":
                status["status"] = "skipped"
                status["error"] = f"依赖的数据源 {depends_on} 未成功，跳过"
                statuses.append(status)
                status_by_id[source_id] = status
                LOGGER.warning("%s: %s", source_id, status["error"])
                continue

        source_started = time.monotonic()
        LOGGER.info("collecting %s (%s)", source_id, source.get("name"))
        try:
            items = _source_collector(source, client, now, context)
            if not items:
                raise FetchError("adapter returned zero items")
            status["status"] = "ok"
            status["fetched"] = len(items)
            status["accepted"] = len(items)
            status["last_success_at"] = iso_utc(now)
            by_source[source_id] = items
            new_items.extend(items)
            LOGGER.info("%s: %s items", source_id, len(items))
        except Exception as exc:  # one broken source must not stop the others
            status["status"] = "failed"
            status["error"] = f"{type(exc).__name__}: {exc}"[:500]
            status["last_success_at"] = (previous_sources.get(source_id) or {}).get("last_success_at")
            LOGGER.warning("%s failed: %s", source_id, status["error"])
            LOGGER.debug("source failure detail", exc_info=True)
        finally:
            status["duration_ms"] = int((time.monotonic() - source_started) * 1000)
            statuses.append(status)
            status_by_id[source_id] = status

    # Preserve the last good items from a failed source, but never from a source
    # that has never succeeded.
    merged_items = list(new_items)
    for status in statuses:
        # A deliberately disabled source should disappear; only failures and
        # dependency skips fall back to their last good snapshot.
        if status["status"] not in {"failed", "skipped"}:
            continue
        retained = _previous_items_for_source(previous, status["id"], now, retention_hours)
        if retained:
            for item in retained:
                item["source_stale"] = True
            merged_items.extend(retained)
            status["retained"] = len(retained)
            status["using_previous"] = True

    if previous_items:
        stabilize_collected_at(merged_items, previous_items)
    previous_ids = {item.get("id") for item in previous_items if item.get("id")}
    items, dedupe_stats = deduplicate(merged_items, max_items=max_items)
    new_count = sum(1 for item in items if item.get("id") not in previous_ids)
    category_counts: dict[str, int] = {}
    for item in items:
        category = item.get("category") or "hot"
        category_counts[category] = category_counts.get(category, 0) + 1

    enabled = [s for s in statuses if s["status"] != "disabled"]
    sources_ok = sum(1 for s in statuses if s["status"] == "ok")
    sources_failed = sum(1 for s in statuses if s["status"] == "failed")
    sources_skipped = sum(1 for s in statuses if s["status"] == "skipped")
    sources_with_previous = sum(1 for s in statuses if s["using_previous"])
    all_failed = sources_ok == 0
    partial = sources_ok > 0 and (sources_failed > 0 or sources_skipped > 0)
    stale = all_failed
    if stale:
        if previous_items:
            stale_reason = "本次采集全部失败，页面展示上次成功保存的数据"
        else:
            stale_reason = "首次采集未成功，暂时没有可展示的数据"
    elif partial:
        stale_reason = "部分数据源本次未更新，页面同时保留了它们的上次成功数据"
    else:
        stale_reason = None

    generated_at = iso_utc(now) if sources_ok else (previous or {}).get("generated_at")
    feed = {
        "schema_version": 2,
        "content_kind": "text",
        "site": SITE,
        "timezone": config.get("timezone", "Asia/Shanghai"),
        "generated_at": generated_at,
        "checked_at": iso_utc(now),
        "settings": {
            "today_hours": int(feed_cfg.get("today_hours", 24)),
            "retention_hours": retention_hours,
            "max_items": max_items,
        },
        "stale": stale,
        "stale_reason": stale_reason,
        "run": {
            "ok": not stale and not partial and sources_failed == 0 and sources_skipped == 0,
            "partial": partial,
            "sources_total": len(enabled),
            "sources_ok": sources_ok,
            "sources_failed": sources_failed,
            "sources_skipped": sources_skipped,
            "sources_using_previous": sources_with_previous,
            "items_raw": sum(s["fetched"] for s in statuses),
            "items_final": len(items),
            "items_new": new_count,
            "duplicates_removed": dedupe_stats["duplicates_removed"],
            "groups": dedupe_stats["groups"],
            "categories": category_counts,
            "authenticity": {
                "real": sum(1 for item in items if item.get("authenticity", "real") == "real"),
                "rewrite": sum(1 for item in items if item.get("authenticity") == "rewrite"),
                "ai": sum(1 for item in items if item.get("authenticity") == "ai"),
            },
            "duration_ms": int((time.monotonic() - started_monotonic) * 1000),
        },
        "sources": statuses,
        "items": items,
    }

    # If the substantive data is unchanged, keep the old file byte-for-byte.
    # This is what lets the scheduled workflow avoid empty commits.
    if previous is not None and feed_signature(feed) == feed_signature(previous):
        LOGGER.info("no substantive data change; keeping previous feed")
        feed = previous

    exit_code = 0 if items else 1
    LOGGER.info(
        "done: ok=%s partial=%s failed=%s items=%s stale=%s exit=%s",
        sources_ok,
        partial,
        sources_failed,
        len(items),
        stale,
        exit_code,
    )
    return feed, exit_code


def write_feed(feed: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    payload = json.dumps(feed, ensure_ascii=False, indent=2) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    os.replace(temporary, path)


def _print_summary(feed: dict) -> None:
    run = feed.get("run") or {}
    print(
        json.dumps(
            {
                "generated_at": feed.get("generated_at"),
                "checked_at": feed.get("checked_at"),
                "stale": feed.get("stale"),
                "sources_ok": run.get("sources_ok"),
                "sources_failed": run.get("sources_failed"),
                "sources_skipped": run.get("sources_skipped"),
                "items": (feed.get("run") or {}).get("items_final"),
                "new": (feed.get("run") or {}).get("items_new"),
                "categories": (feed.get("run") or {}).get("categories"),
                "duplicates_removed": run.get("duplicates_removed"),
                "groups": run.get("groups"),
                "source_status": [
                    {
                        "id": source.get("id"),
                        "status": source.get("status"),
                        "accepted": source.get("accepted"),
                        "retained": source.get("retained"),
                        "error": source.get("error"),
                    }
                    for source in feed.get("sources", [])
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect Meme Radar's public feed")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--previous", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    previous_path = args.previous or args.output
    previous = load_previous(previous_path)
    feed, code = collect(config, previous)
    if not args.dry_run:
        write_feed(feed, args.output)
        LOGGER.info("wrote %s", args.output)
    _print_summary(feed)
    return code


if __name__ == "__main__":
    sys.exit(main())
