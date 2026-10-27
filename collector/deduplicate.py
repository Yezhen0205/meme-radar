"""URL / content deduplication and cross-source event grouping."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .classify import title_words_for_grouping
from .normalize import canonical_url, item_timestamp


GROUPABLE_KINDS = {"video", "article", "hot"}
KIND_PRIORITY = {"video": 0, "article": 1, "hot": 2}
CATEGORY_ORDER = {"meme": 0, "reply": 1, "comment": 2, "hot": 3}
_CONTENT_FIELDS = (
    "title",
    "summary",
    "source_id",
    "source_kind",
    "url",
    "published_at",
    "published_precision",
    "category",
    "tags",
    "heat",
    "rank",
    "context",
    "context_url",
    "author",
    "image",
)


def deduplicate(items: list[dict], max_items: int = 300) -> tuple[list[dict], dict]:
    """Remove exact duplicates, group similar event coverage, and cap the feed."""
    raw_count = len(items)
    unique: list[dict] = []
    seen_urls: set[tuple[str, str]] = set()
    seen_fingerprints: set[tuple[str, str]] = set()
    for item in items:
        url_key = (item["source_id"], canonical_url(item["url"]))
        fp_key = (item["source_id"], item["fingerprint"])
        if url_key in seen_urls or fp_key in seen_fingerprints:
            continue
        seen_urls.add(url_key)
        seen_fingerprints.add(fp_key)
        unique.append(item)

    groups: list[list[dict]] = []
    for item in unique:
        if item["category"] in {"comment", "reply"} or item["source_kind"] not in GROUPABLE_KINDS:
            groups.append([item])
            continue
        tokens = title_words_for_grouping(item["title"])
        best_group: list[dict] | None = None
        best_score = 0.0
        for group in groups:
            rep = group[0]
            if rep["category"] in {"comment", "reply"} or rep["source_kind"] not in GROUPABLE_KINDS:
                continue
            if item["fingerprint"] == rep["fingerprint"]:
                best_group, best_score = group, 1.0
                break
            if rep["source_kind"] != item["source_kind"]:
                continue
            other = title_words_for_grouping(rep["title"])
            if min(len(tokens), len(other)) < 3:
                continue
            inter = len(tokens & other)
            union = len(tokens | other)
            score = inter / union if union else 0.0
            containment = inter / min(len(tokens), len(other))
            if score >= 0.52 or (containment >= 0.72 and inter >= 3):
                if score > best_score:
                    best_group, best_score = group, score
        if best_group is None:
            groups.append([item])
        else:
            best_group.append(item)

    representatives: list[dict] = []
    grouped_count = 0
    for group in groups:
        if len(group) > 1:
            grouped_count += 1
        group.sort(key=_representative_key)
        rep = dict(group[0])
        related = []
        seen_related_urls = set()
        for other in group[1:]:
            if len(related) >= 4:
                break
            if other["url"] in seen_related_urls:
                continue
            seen_related_urls.add(other["url"])
            related.append(
                {
                    "title": other["title"],
                    "source_id": other["source_id"],
                    "source_name": other["source_name"],
                    "url": other["url"],
                    "heat": other.get("heat"),
                }
            )
        fingerprint_set = sorted(item["fingerprint"] for item in group)
        group_hash = hashlib.sha1("|".join(fingerprint_set).encode("utf-8")).hexdigest()[:12]
        rep["group_id"] = group_hash
        rep["group_size"] = len(group)
        rep["related"] = related
        representatives.append(rep)

    representatives.sort(
        key=lambda item: (
            CATEGORY_ORDER.get(item["category"], 9),
            -item_timestamp(item).timestamp(),
            item["rank"],
        )
    )
    if len(representatives) > max_items:
        representatives = representatives[:max_items]
    stats = {
        "input": raw_count,
        "unique": len(unique),
        "duplicates_removed": raw_count - len(unique),
        "groups": grouped_count,
        "final": len(representatives),
    }
    return representatives, stats


def _representative_key(item: dict) -> tuple:
    heat = (item.get("heat") or {}).get("value", 0)
    return (
        KIND_PRIORITY.get(item.get("source_kind"), 9),
        int(item.get("rank") or 1),
        -int(heat or 0),
        item.get("id", ""),
    )


def content_signature(item: dict) -> str:
    payload = {field: item.get(field) for field in _CONTENT_FIELDS}
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def stabilize_collected_at(items: list[dict], previous_items: list[dict]) -> None:
    """Keep first-seen timestamps when a feed item is unchanged between runs."""
    previous = {item.get("id"): item for item in previous_items}
    for item in items:
        old = previous.get(item.get("id"))
        if not old:
            continue
        if content_signature(item) == content_signature(old):
            item["collected_at"] = old.get("collected_at")


def feed_signature(feed: dict) -> str:
    """Signature of substantive data, ignoring run timing details."""
    sources = []
    for source in feed.get("sources", []):
        sources.append(
            {
                key: source.get(key)
                for key in (
                    "id",
                    "status",
                    "fetched",
                    "accepted",
                    "error",
                    "using_previous",
                )
            }
        )
    payload = {
        "stale": feed.get("stale"),
        "stale_reason": feed.get("stale_reason"),
        "run": {
            key: (feed.get("run") or {}).get(key)
            for key in ("ok", "partial", "sources_ok", "sources_failed")
        },
        "sources": sources,
        "items": feed.get("items", []),
    }
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def content_only_signature(feed: dict) -> str:
    payload = {"items": feed.get("items", [])}
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
