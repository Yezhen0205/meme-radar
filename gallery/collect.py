"""Orchestrate the image gallery collectors and write gallery/health data."""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from .collectors import SourceResult, failed_result
from .collectors import reddit as reddit_collector
from .collectors import tieba as tieba_collector
from .collectors import trends as trends_collector
from .dedupe import feed_signature, merge_and_rank
from .health import load_health, update_health
from .http import HttpClient, HttpError
from .images import dhash, image_dimensions, image_is_valid, magic_image
from .models import clean_text, iso_utc, parse_iso, utc_now


LOGGER = logging.getLogger("meme_radar.gallery.collect")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "gallery.json"
DEFAULT_OUTPUT = ROOT / "data" / "gallery.json"
DEFAULT_HEALTH = ROOT / "data" / "health.json"
SITE = {
    "name": "梗图雷达",
    "name_en": "Meme Radar",
    "tagline": "Reddit × 百度贴吧，真实的梗图瀑布流。",
}


def load_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config root must be an object")
    for key in ("reddit", "tieba", "trends", "limits"):
        if key not in data:
            raise ValueError(f"config missing {key}")
    return data


def load_previous(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return data
    except (OSError, ValueError):
        LOGGER.warning("cannot read previous gallery %s", path)
    return None


def _source_disabled(source: str) -> SourceResult:
    return SourceResult(
        source=source,
        status="disabled",
        error="数据源在配置中关闭",
        details={"reason": "disabled"},
        stats={"fetched": 0, "with_images": 0},
    )


def _run_source(source: str, config: dict, http: HttpClient, now: datetime) -> SourceResult:
    enabled = bool(config.get("enabled", True))
    if not enabled:
        return _source_disabled(source)
    try:
        if source == "reddit":
            return reddit_collector.collect(config, http, now)
        if source == "tieba":
            return tieba_collector.collect(config, http, now)
    except Exception as exc:
        LOGGER.exception("%s collector crashed", source)
        return failed_result(source, f"{type(exc).__name__}: {exc}")
    return failed_result(source, f"unknown source {source}")


def _copy_image_fields(target: dict, source: dict) -> None:
    for field in (
        "image_status",
        "image_http_status",
        "image_checked_at",
        "image_error",
        "image_width",
        "image_height",
        "image_hash",
        "image_fallback",
    ):
        target[field] = source.get(field)


def _enrich_image(item: dict, image_http: HttpClient, now: datetime, limits: dict) -> None:
    old = item.get("_previous") or {}
    same_url = old.get("image_url") == item.get("image_url")
    old_checked = parse_iso(old.get("image_checked_at"))
    fresh = old_checked and (now - old_checked).total_seconds() < 12 * 3600
    if same_url and old.get("image_status") in {"ok", "broken"} and fresh:
        _copy_image_fields(item, old)
        item["status"] = "active" if item["image_status"] == "ok" else "image_broken"
        return

    probe = image_http.probe_image(item["image_url"], referer=item.get("post_url"))
    valid = not probe.error and image_is_valid(probe.body, probe.content_type)
    used_url = item["image_url"]
    if not valid and item.get("thumbnail_url") and item["thumbnail_url"] != item["image_url"]:
        thumb_probe = image_http.probe_image(item["thumbnail_url"], referer=item.get("post_url"))
        if not thumb_probe.error and image_is_valid(thumb_probe.body, thumb_probe.content_type):
            probe = thumb_probe
            valid = True
            used_url = item["thumbnail_url"]
            item["image_url"] = used_url
            item["image_fallback"] = True
    item["image_checked_at"] = iso_utc(now)
    item["image_http_status"] = probe.status
    if valid:
        item["image_status"] = "ok"
        item["image_error"] = None
        item["status"] = "active"
        if int(limits.get("_hash_count", 0)) < int(limits.get("image_hash_limit", 35)):
            try:
                data = image_http.download_image(
                    used_url,
                    referer=item.get("post_url"),
                    max_bytes=int(limits.get("image_max_bytes", 3145728)),
                )
                if image_is_valid(data, probe.content_type):
                    width, height = image_dimensions(data)
                    item["image_width"] = width
                    item["image_height"] = height
                    item["image_hash"] = dhash(data)
                    limits["_hash_count"] = int(limits.get("_hash_count", 0)) + 1
            except HttpError as exc:
                LOGGER.debug("image hash download failed for %s: %s", item.get("id"), exc)
    else:
        item["image_status"] = "broken"
        item["image_error"] = (probe.error or "image body is not a supported image")[:300]
        item["status"] = "image_broken"


def enrich_images(items: list[dict], previous_items: list[dict], http: HttpClient, now: datetime, limits: dict) -> dict:
    previous = {item.get("id"): item for item in previous_items}
    check_limit = int(limits.get("image_check_limit", 60))
    checked = 0
    broken = 0
    for item in items:
        item["_previous"] = previous.get(item.get("id"))
        if checked >= check_limit:
            item["image_status"] = "unchecked"
            item["status"] = "active"
            continue
        _enrich_image(item, http, now, limits)
        checked += 1
        if item.get("image_status") == "broken":
            broken += 1
        item.pop("_previous", None)
    return {"checked": checked, "broken": broken, "hashed": int(limits.get("_hash_count", 0))}


def build_feed(
    config: dict,
    previous: dict | None,
    now: datetime,
    *,
    previous_health: dict | None = None,
    image_enabled: bool = True,
) -> tuple[dict, dict, int]:
    request_cfg = config.get("request") or {}
    limits = dict(config.get("limits") or {})
    source_http = HttpClient(
        timeout=float(request_cfg.get("timeout_seconds", 20)),
        retries=int(request_cfg.get("retries", 1)),
        backoff=float(request_cfg.get("backoff_seconds", 6)),
        min_interval=float(request_cfg.get("min_interval_seconds", 2)),
        user_agent=str(request_cfg.get("user_agent", "MemeRadar/2.0")),
    )
    image_http = HttpClient(
        timeout=min(15.0, float(request_cfg.get("timeout_seconds", 20))),
        retries=0,
        backoff=2,
        min_interval=float(request_cfg.get("image_min_interval_seconds", 0.35)),
        user_agent=str(request_cfg.get("user_agent", "MemeRadar/2.0")),
    )
    results: dict[str, SourceResult] = {}
    for source in ("reddit", "tieba"):
        LOGGER.info("collecting %s", source)
        results[source] = _run_source(source, config.get(source) or {}, source_http, now)
        LOGGER.info("%s -> %s (%s items)", source, results[source].status, len(results[source].items))

    trends_cfg = config.get("trends") or {}
    try:
        trend_result = trends_collector.collect(trends_cfg, source_http, now)
    except Exception as exc:
        LOGGER.exception("trends crashed")
        trend_result = trends_collector.TrendResult(status="blocked", error=f"{type(exc).__name__}: {exc}")
    LOGGER.info("trends -> %s (%s keywords)", trend_result.status, len(trend_result.keywords))

    previous_items = (previous or {}).get("items") or []
    candidate_items = []
    for result in results.values():
        for item in result.items:
            item["source_stale"] = False
            candidate_items.append(item)
    image_stats = {"checked": 0, "broken": 0, "hashed": 0}
    if image_enabled:
        image_stats = enrich_images(candidate_items, previous_items, image_http, now, limits)
    else:
        for item in candidate_items:
            item["image_status"] = "unchecked"

    items, merge_stats = merge_and_rank(
        previous_items,
        results,
        trend_result.keywords,
        now=now,
        retention_hours=int(limits.get("retention_hours", 336)),
        max_items=int(limits.get("max_items", 300)),
    )
    for item in items:
        item["status"] = "active" if item.get("image_status") == "ok" else "image_broken" if item.get("image_status") == "broken" else "active"
        if item.get("image_status") == "ok":
            item["status"] = "active"
        item.pop("_previous", None)

    planned = list(config.get("planned") or [])
    health = update_health(
        previous_health or {},
        results,
        trend_result.status,
        items,
        now=now,
        planned=planned,
    )
    health["history"][-1]["new"] = merge_stats["new"]
    health["history"][-1]["broken_images"] = image_stats["broken"]
    if "trends" in health.get("sources", {}):
        health["sources"]["trends"]["item_count"] = len(trend_result.keywords)

    blocked_sources = [source for source, result in results.items() if result.status in {"blocked", "failed"}]
    ok_sources = [source for source, result in results.items() if result.has_items and result.status in {"ok", "degraded"}]
    stale = not items or len(ok_sources) == 0
    partial = bool(blocked_sources or any(result.status == "degraded" for result in results.values()) or trend_result.status in {"degraded", "blocked"})
    if stale:
        stale_reason = "本轮没有可用图片，保留上次成功数据"
    elif blocked_sources:
        stale_reason = f"{', '.join(blocked_sources)} 本次不可用，保留其历史数据"
    else:
        stale_reason = None
    generated_at = iso_utc(now) if ok_sources else (previous or {}).get("generated_at")
    sources_public = []
    for source in ("reddit", "tieba"):
        result = results[source]
        entry = result.public()
        entry["name"] = "Reddit" if source == "reddit" else "百度贴吧"
        sources_public.append(entry)
    sources_public.append(
        {
            "source": "trends",
            "name": "公开热点榜",
            "status": trend_result.status,
            "item_count": len(trend_result.keywords),
            "error": trend_result.error,
            "details": {"sources": trend_result.sources},
            "stats": {"keywords": len(trend_result.keywords)},
        }
    )
    for planned_source in planned:
        sources_public.append(
            {
                "source": planned_source,
                "name": planned_source,
                "status": "planned",
                "item_count": 0,
                "error": None,
                "details": {"reason": "not_implemented"},
                "stats": {},
            }
        )
    feed = {
        "schema_version": 2,
        "site": SITE,
        "timezone": config.get("timezone", "Asia/Shanghai"),
        "generated_at": generated_at,
        "checked_at": iso_utc(now),
        "stale": stale,
        "stale_reason": stale_reason,
        "partial": partial,
        "health": health,
        "trends": trend_result.public(),
        "sources": sources_public,
        "run": {
            "ok": not stale and not blocked_sources,
            "status": health["status"],
            "items_new": merge_stats["new"],
            "items_updated": merge_stats["updated"],
            "items_total": len(items),
            "duplicate_posts": merge_stats["duplicates_removed"],
            "groups": merge_stats["groups"],
            "images_checked": image_stats["checked"],
            "images_broken": image_stats["broken"],
            "images_hashed": image_stats["hashed"],
            "duration_ms": 0,
            "sources_ok": len(ok_sources),
            "sources_blocked": len(blocked_sources),
        },
        "settings": {
            "max_items": int(limits.get("max_items", 300)),
            "retention_hours": int(limits.get("retention_hours", 336)),
            "image_check_limit": int(limits.get("image_check_limit", 60)),
        },
        "items": items,
    }
    return feed, health, 0 if items else 1


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def print_summary(feed: dict, health: dict) -> None:
    run = feed.get("run") or {}
    print(
        json.dumps(
            {
                "generated_at": feed.get("generated_at"),
                "checked_at": feed.get("checked_at"),
                "status": health.get("status"),
                "items": len(feed.get("items", [])),
                "new": run.get("items_new"),
                "updated": run.get("items_updated"),
                "images_broken": run.get("images_broken"),
                "sources": [
                    {
                        "source": source.get("source"),
                        "status": source.get("status"),
                        "count": source.get("item_count"),
                        "error": source.get("error"),
                    }
                    for source in feed.get("sources", [])
                ],
                "alerts": health.get("alerts", []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect real meme images from Reddit and Tieba")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--health", type=Path, default=DEFAULT_HEALTH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-images", action="store_true", help="skip image probing (tests only)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    previous = load_previous(args.output)
    previous_health = load_health(args.health)
    started = time.monotonic()
    now = utc_now()
    feed, health, code = build_feed(
        config,
        previous,
        now,
        previous_health=previous_health,
        image_enabled=not args.no_images,
    )
    feed["run"]["duration_ms"] = int((time.monotonic() - started) * 1000)
    if previous is not None and feed_signature(feed) == feed_signature(previous):
        LOGGER.info("no substantive gallery change; keeping previous feed")
        feed = previous
    if not args.dry_run:
        write_json(args.output, feed)
        write_json(args.health, health)
        LOGGER.info("wrote %s and %s", args.output, args.health)
    print_summary(feed, health)
    return code


if __name__ == "__main__":
    sys.exit(main())
