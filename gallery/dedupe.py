"""Merge runs, preserve failed-source history, rank and group similar images."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Iterable

from .collectors import SourceResult
from .images import hamming_distance
from .models import age_hours, digest, item_timestamp


SOURCE_PRIORITY = {"reddit": 0, "tieba": 1}
RETENTION_DEFAULT = 336


def _public_fields(item: dict) -> dict:
    return {
        key: item.get(key)
        for key in (
            "title",
            "summary",
            "community",
            "post_url",
            "image_url",
            "thumbnail_url",
            "created_at",
            "score",
            "comment_count",
            "tags",
            "content_hash",
            "image_hash",
            "status",
            "image_status",
        )
    }


def merge_and_rank(
    previous_items: list[dict],
    results: dict[str, SourceResult],
    trend_keywords: list[dict],
    *,
    now: datetime,
    retention_hours: int = RETENTION_DEFAULT,
    max_items: int = 300,
) -> tuple[list[dict], dict]:
    previous_by_id = {item["id"]: item for item in previous_items if item.get("id")}
    pool: dict[str, dict] = {}
    new_count = 0
    updated_count = 0

    for source, result in results.items():
        for item in result.items:
            item_id = item["id"]
            old = previous_by_id.get(item_id)
            if old:
                if _public_fields(old) != _public_fields(item):
                    updated_count += 1
                # First-seen time is stable; do not rewrite it every run.
                item["collected_at"] = old.get("collected_at") or item.get("collected_at")
                if old.get("image_status") == "ok" and old.get("image_url") == item.get("image_url"):
                    for field in (
                        "image_status",
                        "image_http_status",
                        "image_checked_at",
                        "image_error",
                        "image_width",
                        "image_height",
                        "image_hash",
                    ):
                        item[field] = old.get(field)
                item["source_stale"] = False
            else:
                new_count += 1
                item["source_stale"] = False
            pool[item_id] = item

    # Keep history, including the last good items of a temporarily failed source.
    for item in previous_items:
        item_id = item.get("id")
        if not item_id or item_id in pool:
            continue
        source = item.get("source")
        if source not in results:
            continue
        if age_hours(item, now=now) > retention_hours:
            continue
        copy = dict(item)
        copy["source_stale"] = results[source].status not in {"ok", "degraded"}
        pool[item_id] = copy

    items = list(pool.values())
    # Exact duplicate post/image URLs (keep the representative with more metadata).
    url_best: dict[tuple[str, str], dict] = {}
    for item in items:
        key = (item.get("source", ""), item.get("post_url", ""))
        old = url_best.get(key)
        if old is None or _quality(item) > _quality(old):
            url_best[key] = item
    items = list(url_best.values())

    # Near-duplicate images across sources (dHash Hamming distance <= 6).
    groups: list[list[dict]] = []
    for item in items:
        matched = None
        for group in groups:
            rep = group[0]
            exact = item.get("image_url") and item.get("image_url") == rep.get("image_url")
            similar = hamming_distance(item.get("image_hash"), rep.get("image_hash")) <= 6
            if exact or similar:
                matched = group
                break
        if matched is None:
            groups.append([item])
        else:
            matched.append(item)

    ranked = []
    for group in groups:
        group.sort(key=_representative_key)
        rep = dict(group[0])
        related = []
        for other in group[1:5]:
            related.append(
                {
                    "source": other.get("source"),
                    "source_name": other.get("source_name"),
                    "post_url": other.get("post_url"),
                    "image_url": other.get("image_url"),
                    "title": other.get("title"),
                }
            )
        keys = sorted(
            {
                item.get("image_hash") or item.get("image_url") or item.get("content_hash")
                for item in group
            }
        )
        rep["group_id"] = hashlib.sha1("|".join(keys).encode("utf-8")).hexdigest()[:12]
        rep["group_size"] = len(group)
        rep["related"] = related
        rep["rank_score"], rep["rank_basis"] = _rank_score(rep, trend_keywords, now)
        rep["trending"] = _matching_keywords(rep, trend_keywords)
        ranked.append(rep)

    ranked.sort(
        key=lambda item: (
            0 if item.get("image_status") == "ok" else 1,
            -float(item.get("rank_score") or 0),
            -item_timestamp(item).timestamp(),
        )
    )
    if len(ranked) > max_items:
        ranked = ranked[:max_items]
    stats = {
        "input": len(previous_items) + sum(len(result.items) for result in results.values()),
        "new": new_count,
        "updated": updated_count,
        "final": len(ranked),
        "groups": sum(1 for item in ranked if item.get("group_size", 1) > 1),
        "duplicates_removed": max(0, len(pool) - len(items)),
    }
    return ranked, stats


def _quality(item: dict) -> tuple:
    return (
        1 if item.get("image_status") == "ok" else 0,
        1 if item.get("image_hash") else 0,
        len(item.get("summary") or ""),
        item.get("comment_count") or 0,
    )


def _representative_key(item: dict) -> tuple:
    return (
        SOURCE_PRIORITY.get(item.get("source"), 9),
        -float(item.get("rank_score") or 0),
        0 if item.get("image_status") == "ok" else 1,
    )


def _matching_keywords(item: dict, keywords: Iterable[dict]) -> list[str]:
    text = " ".join(
        [
            item.get("title") or "",
            item.get("summary") or "",
            " ".join(item.get("tags") or []),
        ]
    )
    return [entry["word"] for entry in keywords if entry.get("word") and entry["word"] in text][:5]


def _rank_score(item: dict, keywords: list[dict], now: datetime) -> tuple[float, str]:
    age = age_hours(item, now=now)
    recency = max(0.0, 100.0 - (age / 168.0) * 100.0)
    basis = "recency"
    comments = 0.0
    count = item.get("comment_count")
    if isinstance(count, int) and count > 0:
        comments = min(45.0, math.log10(count + 1) * 18.0)
        basis = "recency+comments"
    boost = 12.0 if _matching_keywords(item, keywords) else 0.0
    if boost:
        basis += "+trend"
    return round(recency + comments + boost, 1), basis


def feed_signature(feed: dict) -> str:
    """Substantive signature; excludes check timestamps and run durations."""
    sources = []
    for source in feed.get("sources", []):
        sources.append(
            {
                "source": source.get("source"),
                "status": source.get("status"),
                "item_count": source.get("item_count"),
                "error": source.get("error"),
            }
        )
    payload = {
        "items": feed.get("items", []),
        "sources": sources,
        "trends": feed.get("trends", {}).get("keywords", []),
        "stale": feed.get("stale"),
        "health": {
            "status": (feed.get("health") or {}).get("status"),
            "alerts": (feed.get("health") or {}).get("alerts", []),
            "sources": {
                key: {
                    "status": value.get("status"),
                    "consecutive_failures": value.get("consecutive_failures"),
                }
                for key, value in ((feed.get("health") or {}).get("sources") or {}).items()
            },
        },
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
