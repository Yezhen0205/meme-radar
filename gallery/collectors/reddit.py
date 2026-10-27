"""Reddit public Atom/RSS collector.

Anonymous JSON endpoints return 403 to cloud IPs, while the official
multi-community Atom feed is public and works from GitHub Actions.  RSS does
not expose score or comment counts, so those fields stay null.
"""
from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any

from ..http import HttpClient, HttpError
from ..models import age_hours, clean_text, make_item, parse_iso, utc_now
from . import SourceResult, failed_result


LOGGER = logging.getLogger("meme_radar.gallery.reddit")
ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"
_IMAGE_TAG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", flags=re.I)
_COMMENTS = re.compile(r"/comments/([^/]+)/")
_SUBREDDIT = re.compile(r"/r/([^/]+)/", flags=re.I)
_SUBMITTED = re.compile(r"submitted by\s+/u/\S+.*", flags=re.I)


def _strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = _SUBMITTED.sub("", text)
    text = re.sub(r"\[(?:link|comments)\]", " ", text, flags=re.I)
    return clean_text(text, max_len=360)


def _extract_images(content: str, thumbnail: str) -> list[str]:
    images = [html.unescape(value) for value in _IMAGE_TAG.findall(content or "")]
    if thumbnail:
        images.append(html.unescape(thumbnail))
    result = []
    for image in images:
        if image.startswith("//"):
            image = "https:" + image
        if image.startswith(("http://", "https://")) and image not in result:
            result.append(image)
    return result


def parse_rss(text: str, *, now: datetime, max_age_hours: int = 72) -> tuple[list[dict], dict]:
    root = ET.fromstring(text)
    entries = root.findall(f"{ATOM}entry")
    items: list[dict] = []
    skipped_old = 0
    no_image = 0
    seen: set[str] = set()
    for entry in entries:
        title = clean_text(entry.findtext(f"{ATOM}title", default=""), max_len=220)
        link_node = entry.find(f"{ATOM}link")
        post_url = link_node.get("href") if link_node is not None else ""
        if not title or not post_url:
            continue
        comment_match = _COMMENTS.search(post_url)
        subreddit_match = _SUBREDDIT.search(post_url)
        if not comment_match:
            continue
        source_id = comment_match.group(1)
        if source_id in seen:
            continue
        subreddit = subreddit_match.group(1) if subreddit_match else "unknown"
        published = (
            entry.findtext(f"{ATOM}published", default="")
            or entry.findtext(f"{ATOM}updated", default="")
        )
        created_at = parse_iso(published)
        content_node = entry.find(f"{ATOM}content")
        content = content_node.text if content_node is not None and content_node.text else ""
        thumb_node = entry.find(f"{MEDIA}thumbnail")
        thumbnail = thumb_node.get("url") if thumb_node is not None else ""
        images = _extract_images(content, thumbnail)
        if not images:
            no_image += 1
            continue
        if created_at and (now - created_at).total_seconds() / 3600.0 > max_age_hours:
            skipped_old += 1
            continue
        summary = _strip_html(content)
        tags = [f"r/{subreddit}", "reddit"]
        for category in entry.findall(f"{ATOM}category"):
            term = clean_text(category.get("term"), max_len=24)
            if term and term not in tags:
                tags.append(term)
        item = make_item(
            source="reddit",
            source_name="Reddit",
            source_id=source_id,
            community=f"r/{subreddit}",
            title=title,
            summary=summary,
            post_url=post_url,
            image_url=images[0],
            thumbnail_url=thumbnail or images[0],
            images=[{"url": image, "thumbnail_url": image} for image in images[:4]],
            created_at=created_at,
            collected_at=now,
            score=None,
            comment_count=None,
            tags=tags,
        )
        items.append(item)
        seen.add(source_id)
    return items, {
        "entries": len(entries),
        "with_images": len(items),
        "no_image": no_image,
        "skipped_old": skipped_old,
    }


def collect(config: dict, http: HttpClient, now: datetime | None = None) -> SourceResult:
    now = now or utc_now()
    communities = [
        str(name).strip().lstrip("r/").strip("/")
        for name in config.get("communities", [])
        if str(name).strip()
    ]
    if not communities:
        return failed_result("reddit", "没有配置任何 Reddit 社区")
    feed = str(config.get("feed", "new")).strip().lower()
    if feed not in {"new", "hot"}:
        feed = "new"
    joined = "+".join(communities)
    urls = []
    if feed == "hot":
        urls.append(f"https://www.reddit.com/r/{joined}/.rss")
    else:
        urls.append(f"https://www.reddit.com/r/{joined}/new/.rss")
    # Fallback if a subreddit name changes the route.
    urls.append(f"https://www.reddit.com/r/{joined}/.rss")

    last_error = ""
    for url in urls:
        try:
            text = http.get_text(url, referer="https://www.reddit.com/")
            items, stats = parse_rss(
                text,
                now=now,
                max_age_hours=int(config.get("max_age_hours", 72)),
            )
            limit = int(config.get("limit", 25))
            items = items[:limit]
            stats["with_images"] = len(items)
            status = "ok" if items else "degraded"
            error = None
            if not items:
                error = "RSS 可访问，但没有可用的图片帖子"
            return SourceResult(
                source="reddit",
                status=status,
                items=items,
                error=error,
                details={
                    "communities": communities,
                    "feed": feed,
                    "rss_url": url,
                    **stats,
                },
                stats={
                    "fetched": stats["entries"],
                    "with_images": len(items),
                    "no_image": stats["no_image"],
                    "skipped_old": stats["skipped_old"],
                },
            )
        except HttpError as exc:
            last_error = str(exc)
            LOGGER.warning("Reddit RSS failed (%s): %s", url, exc)
            if exc.status not in {404, 403, 429}:
                break
        except ET.ParseError as exc:
            last_error = f"RSS XML 解析失败: {exc}"
            LOGGER.warning("Reddit RSS parse failed: %s", exc)
            break
    return failed_result("reddit", last_error or "Reddit RSS 不可用")
