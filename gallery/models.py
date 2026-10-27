"""Normalised gallery item model shared by Reddit and Tieba collectors."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def clean_text(value: Any, max_len: int = 400) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", text)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text).strip(" \u3000\"'“”‘’")
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip(" ,.;:，。；：、") + "…"
    return text


def clean_url(value: Any) -> str:
    if not value:
        return ""
    url = html.unescape(str(value)).strip()
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"^https?://", url, flags=re.I):
        return ""
    return url


def clean_hashtags(value: str) -> str:
    return re.sub(r"#[^#\s]{1,40}#", " ", value).strip()


def digest(*parts: Any) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def stable_item_id(source: str, source_id: Any, post_url: str) -> str:
    native = str(source_id) if source_id not in (None, "") else post_url
    return f"{source}:{digest(source, native)[:16]}"


def image_id_from_url(image_url: str) -> str:
    return digest(image_url)[:16]


def make_item(
    *,
    source: str,
    source_name: str,
    source_id: Any,
    community: str,
    title: str,
    post_url: str,
    image_url: str,
    thumbnail_url: str | None,
    images: list[dict] | None,
    created_at: datetime | None,
    collected_at: datetime,
    score: int | None,
    comment_count: int | None,
    tags: list[str] | None,
    summary: str = "",
    image_status: str = "unchecked",
) -> dict:
    title = clean_text(title, max_len=220)
    summary = clean_text(clean_hashtags(summary), max_len=360)
    post_url = clean_url(post_url)
    image_url = clean_url(image_url)
    if not title:
        raise ValueError("title is empty")
    if not post_url:
        raise ValueError("post_url is invalid")
    if not image_url:
        raise ValueError("image_url is invalid")
    if source not in {"reddit", "tieba"}:
        raise ValueError(f"unknown source {source!r}")
    if not isinstance(score, int) or score < 0:
        score = None
    if not isinstance(comment_count, int) or comment_count < 0:
        comment_count = None
    clean_tags: list[str] = []
    for tag in tags or []:
        tag = clean_text(tag, max_len=24)
        if tag and tag not in clean_tags:
            clean_tags.append(tag)
        if len(clean_tags) >= 8:
            break
    primary_images = images or [{"url": image_url, "thumbnail_url": thumbnail_url or image_url}]
    normalised_images = []
    for entry in primary_images[:4]:
        url = clean_url(entry.get("url"))
        if not url:
            continue
        normalised_images.append(
            {
                "url": url,
                "thumbnail_url": clean_url(entry.get("thumbnail_url")) or url,
                "width": entry.get("width"),
                "height": entry.get("height"),
            }
        )
    if not normalised_images:
        normalised_images = [{"url": image_url, "thumbnail_url": thumbnail_url or image_url, "width": None, "height": None}]
    thumb = clean_url(thumbnail_url) or normalised_images[0]["thumbnail_url"]
    content_hash = digest(source, source_id, title, post_url, image_url)
    item = {
        "id": stable_item_id(source, source_id, post_url),
        "source": source,
        "source_id": str(source_id),
        "source_name": source_name,
        "community": clean_text(community, max_len=80),
        "title": title,
        "summary": summary,
        "post_url": post_url,
        "image_url": image_url,
        "thumbnail_url": thumb,
        "images": normalised_images,
        "created_at": iso_utc(created_at),
        "collected_at": iso_utc(collected_at),
        "time_source": "source" if created_at else "collection",
        "score": score,
        "comment_count": comment_count,
        "tags": clean_tags,
        "content_hash": content_hash,
        "image_hash": None,
        "image_id": image_id_from_url(image_url),
        "status": "active",
        "image_status": image_status if image_status in {"ok", "broken", "unchecked"} else "unchecked",
        "image_http_status": None,
        "image_checked_at": None,
        "image_error": None,
        "image_width": None,
        "image_height": None,
        "rank_score": 0.0,
        "rank_basis": "recency",
        "group_id": content_hash[:12],
        "group_size": 1,
        "related": [],
    }
    return item


def item_timestamp(item: dict) -> datetime:
    return (
        parse_iso(item.get("created_at"))
        or parse_iso(item.get("collected_at"))
        or datetime(1970, 1, 1, tzinfo=UTC)
    )


def age_hours(item: dict, now: datetime | None = None) -> float:
    now = now or utc_now()
    return max(0.0, (now - item_timestamp(item)).total_seconds() / 3600.0)


def url_host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
