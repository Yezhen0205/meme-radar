"""Normalisation helpers shared by all source adapters."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc

_TRACKING_KEYS = {
    "from",
    "from_source",
    "from_spmid",
    "spm",
    "spm_id_from",
    "vd_source",
    "share_source",
    "share_medium",
    "share_plat",
    "share_tag",
    "share_session_id",
    "share_from",
    "timestamp",
    "unique_k",
    "wxfid",
    "scene",
    "clicktime",
    "enterid",
    "sa",
    "msource",
    "query",
    "rank",
}
_TRACKING_PREFIXES = ("utm_", "share_", "spm")
_HTML_TAG = re.compile(r"<[^>]+>")
_BILI_EMOTICON = re.compile(r"\[[^\[\]]{1,16}\]")
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_SPACE = re.compile(r"\s+")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PUNCT = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


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
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_source_time(value: Any) -> datetime | None:
    """Parse Unix seconds/milliseconds, ISO strings, or YYYYMMDD dates."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        if 946684800 <= number <= 4_102_444_800:  # 2000-01-01..2100-01-01
            return datetime.fromtimestamp(number, tz=UTC)
        return None
    if isinstance(value, str):
        raw = value.strip()
        if re.fullmatch(r"\d{8}", raw):
            try:
                day = datetime.strptime(raw, "%Y%m%d").replace(tzinfo=SHANGHAI)
                return day.astimezone(UTC)
            except ValueError:
                return None
        if re.fullmatch(r"\d{10,13}", raw):
            return parse_source_time(int(raw))
        return parse_iso(raw)
    return None


def clean_text(value: Any, max_len: int = 500) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = _HTML_TAG.sub(" ", text)
    text = _BILI_EMOTICON.sub(" ", text)
    text = _ZERO_WIDTH.sub("", text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = _SPACE.sub(" ", text).strip(" \u3000\"'“”‘’")
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip("，,。.;；、 ") + "…"
    return text


def redact_personal(text: str) -> str:
    text = _PHONE.sub("1**********", text)
    text = _EMAIL.sub("***@***", text)
    return text


def clean_comment(value: Any, max_len: int = 320) -> str:
    text = clean_text(value, max_len=800)
    text = re.sub(r"https?://\S+", " ", text)
    text = redact_personal(text)
    return clean_text(text, max_len=max_len)


def split_title_summary(text: str, title_len: int = 80, summary_len: int = 260) -> tuple[str, str]:
    """Keep short comments readable while preserving longer ones as a summary."""
    text = clean_text(text, max_len=title_len + summary_len)
    if len(text) <= title_len:
        return text, ""
    cut = max(
        text.rfind(mark, 0, title_len + 1)
        for mark in ("。", "！", "？", "；", "…", "，", " ")
    )
    if cut < title_len // 2:
        cut = title_len
    return text[:cut].rstrip("，,。.;；、 ") + "…", text[cut:].strip()


def canonical_url(value: Any, keep_fragment: bool = True) -> str:
    if not value:
        return ""
    url = html.unescape(str(value)).strip().replace("\\/", "/")
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"^https?://", url, flags=re.I):
        return url
    parts = urllib.parse.urlsplit(url)
    scheme = "https"
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host
    if port and port not in (80, 443):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    query_pairs = []
    for key, val in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        lower = key.lower()
        if lower in _TRACKING_KEYS or lower.startswith(_TRACKING_PREFIXES):
            continue
        query_pairs.append((key, val))
    query = urllib.parse.urlencode(query_pairs, doseq=True)
    fragment = ""
    if keep_fragment and parts.fragment and re.match(r"^(reply|comment|rpid)", parts.fragment, re.I):
        fragment = parts.fragment
    return urllib.parse.urlunsplit((scheme, netloc, path, query, fragment))


def fingerprint_for(title: str, context_id: str | None = None) -> str:
    normal = _PUNCT.sub("", (title or "").lower())
    if context_id:
        normal = f"{context_id}|{normal}"
    return hashlib.sha1(normal.encode("utf-8")).hexdigest()


def stable_id(source_id: str, native_id: Any, url: str) -> str:
    base = str(native_id) if native_id not in (None, "") else canonical_url(url)
    digest = hashlib.sha1(f"{source_id}|{base}".encode("utf-8")).hexdigest()[:16]
    return f"{source_id}:{digest}"


def format_heat(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number < 0:
        return ""
    if number >= 100_000_000:
        return f"{number / 100_000_000:.1f}亿".replace(".0亿", "亿")
    if number >= 10_000:
        return f"{number / 10_000:.1f}万".replace(".0万", "万")
    return str(int(number))


def make_item(
    *,
    source_id: str,
    source_name: str,
    source_kind: str,
    title: str,
    url: str,
    collected_at: datetime,
    native_id: Any = None,
    summary: str = "",
    category: str = "hot",
    tags: list[str] | None = None,
    heat_label: str | None = None,
    heat_value: Any = None,
    heat_rank: int | None = None,
    published_at: datetime | None = None,
    published_precision: str = "datetime",
    context: str | None = None,
    context_url: str | None = None,
    author: str | None = None,
    image: str | None = None,
    context_id: str | None = None,
) -> dict:
    title = clean_text(title, max_len=180)
    summary = clean_text(summary, max_len=360)
    if not title:
        raise ValueError("item title is empty")
    url = canonical_url(url)
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"item URL is not absolute: {url!r}")
    category = category if category in {"meme", "reply", "comment", "hot"} else "hot"
    source_rank = max(1, int(heat_rank or 1))
    heat = None
    if heat_label and heat_value is not None:
        try:
            numeric = int(float(heat_value))
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None and numeric >= 0:
            heat = {
                "label": clean_text(heat_label, 12),
                "value": numeric,
                "display": format_heat(numeric),
                "rank": source_rank,
            }
    clean_tags = []
    for tag in tags or []:
        value = clean_text(tag, 16)
        if value and value not in clean_tags:
            clean_tags.append(value)
        if len(clean_tags) >= 4:
            break
    context_value = clean_text(context, 120) if context else None
    item = {
        "id": stable_id(source_id, native_id, url),
        "fingerprint": fingerprint_for(title, context_id=context_id),
        "title": title,
        "summary": summary,
        "source_id": source_id,
        "source_name": source_name,
        "source_kind": source_kind,
        "url": url,
        "published_at": iso_utc(published_at),
        "published_precision": published_precision if published_at else None,
        "collected_at": iso_utc(collected_at),
        "category": category,
        "tags": clean_tags,
        "heat": heat,
        "rank": source_rank,
        "context": context_value,
        "context_url": canonical_url(context_url) if context_url else None,
        "author": clean_text(author, 60) if author else None,
        "image": _https_image(image),
        "group_id": fingerprint_for(title, context_id=context_id)[:12],
        "group_size": 1,
        "related": [],
    }
    return item


def _https_image(value: Any) -> str | None:
    if not value:
        return None
    url = html.unescape(str(value)).strip()
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("http://"):
        url = "https://" + url[7:]
    if not url.startswith("https://"):
        return None
    return url[:500]


def item_timestamp(item: dict) -> datetime:
    return (
        parse_iso(item.get("published_at"))
        or parse_iso(item.get("collected_at"))
        or datetime(1970, 1, 1, tzinfo=UTC)
    )


def age_hours(item: dict, now: datetime | None = None) -> float:
    now = now or utc_now()
    return max(0.0, (now - item_timestamp(item)).total_seconds() / 3600.0)


def date_at_start_of_day(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=SHANGHAI).astimezone(UTC)


def add_hours(value: datetime, hours: float) -> datetime:
    return value + timedelta(hours=hours)
