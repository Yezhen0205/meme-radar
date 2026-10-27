"""Baidu Tieba collector.

The forum/thread HTML endpoints return 403 to automated requests in this
environment, but the public hot-topic page exposes real thread titles, links,
reply counts, forum names and image URLs.  We use that page and mark the source
as degraded, never as a fully verified thread fetch.
"""
from __future__ import annotations

import html
import logging
import re
import urllib.parse
from datetime import datetime

from ..http import HttpClient, HttpError
from ..models import clean_text, make_item, utc_now
from . import SourceResult, failed_result


LOGGER = logging.getLogger("meme_radar.gallery.tieba")
FUN_KEYWORDS = (
    "表情包",
    "梗",
    "搞笑",
    "沙雕",
    "抽象",
    "整活",
    "乐子",
    "图吧",
    "胶佬",
    "神回复",
    "段子",
    "meme",
    "二次元",
    "动漫",
    "游戏",
    "离谱",
    "翻车",
    "名场面",
    "吐槽",
)
EXCLUDE_KEYWORDS = (
    "去世",
    "离世",
    "悼念",
    "遇难",
    "事故",
    "战争",
    "辱华",
    "抵制",
    "贪",
    "判决",
    "地震",
    "癌症",
    "疫情",
    "外交部",
)
_THREAD_LINK = re.compile(r"/p/(\d+)")
_IMAGE_SIZE = re.compile(r"(?:w|h)%3D(?:120|150)", re.I)


def _select_topics(raw_topics: list[dict], config: dict) -> list[dict]:
    max_topics = int(config.get("max_topics", 3))
    topic_keywords = [str(word) for word in (config.get("topic_keywords") or FUN_KEYWORDS)]
    scored = []
    for raw in raw_topics:
        name = clean_text(raw.get("topic_name"), 120)
        desc = clean_text(raw.get("topic_desc") or raw.get("abstract"), 240)
        if not name:
            continue
        text = f"{name} {desc}"
        if any(word in text for word in EXCLUDE_KEYWORDS):
            continue
        score = 0
        for word in topic_keywords:
            if word.lower() in text.lower():
                score += 3 if word in name else 1
        if "表情包" in name:
            score += 6
        if score <= 0:
            continue
        scored.append((score, int(raw.get("discuss_num") or 0), raw))
    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    return [entry[2] for entry in scored[:max_topics]]


def _parse_thread_page(
    page: str,
    *,
    topic: dict,
    now: datetime,
    max_threads: int,
) -> list[dict]:
    try:
        from lxml import html as lxml_html
    except ImportError as exc:
        raise RuntimeError("lxml is required for Tieba parsing") from exc
    document = lxml_html.fromstring(page)
    nodes = document.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), " thread-item ")]'
    )
    topic_name = clean_text(topic.get("topic_name"), 100)
    items: list[dict] = []
    for node in nodes[:max_threads]:
        title_nodes = node.xpath('.//a[contains(@class, "title")]')
        if not title_nodes:
            continue
        title_node = title_nodes[0]
        href = title_node.get("href") or ""
        match = _THREAD_LINK.search(href)
        if not match:
            continue
        title = clean_text(title_node.text_content(), 220)
        if not title:
            continue
        content_nodes = node.xpath('.//*[contains(@class, "content")]')
        summary = clean_text(content_nodes[0].text_content(), 360) if content_nodes else ""
        if summary == title:
            summary = ""
        reply_nodes = node.xpath('.//*[contains(@class, "reply-num")]')
        comment_count = None
        if reply_nodes:
            try:
                comment_count = int(re.sub(r"\D", "", reply_nodes[0].text_content()) or 0)
            except ValueError:
                comment_count = None
        forum_nodes = node.xpath('.//*[contains(@class, "forum-name")]')
        forum = clean_text(forum_nodes[0].text_content(), 80) if forum_nodes else ""
        tag_nodes = node.xpath('.//*[contains(@class, "topic-tag")]')
        tags = ["贴吧"]
        if topic_name:
            tags.append(topic_name)
        if forum:
            tags.append(forum)
        for tag_node in tag_nodes[:3]:
            raw_tag = urllib.parse.unquote(tag_node.get("data-name") or "")
            raw_tag = clean_text(raw_tag, 32).strip("#")
            if raw_tag:
                tags.append(raw_tag)
        images: list[dict] = []
        for image_node in node.xpath(".//img"):
            origin = (
                image_node.get("data-origin")
                or image_node.get("data-original")
                or image_node.get("src")
                or ""
            )
            thumb = image_node.get("src") or origin
            origin = html.unescape(origin)
            thumb = html.unescape(thumb)
            if not origin.startswith(("http://", "https://")):
                continue
            if "tiebapic.baidu.com" not in origin and "imgsa.baidu.com" not in origin:
                continue
            if _IMAGE_SIZE.search(origin):
                continue
            if any(entry["url"] == origin for entry in images):
                continue
            images.append({"url": origin, "thumbnail_url": thumb or origin})
            if len(images) >= 3:
                break
        if not images:
            continue
        post_id = match.group(1)
        post_url = f"https://tieba.baidu.com/p/{post_id}"
        item = make_item(
            source="tieba",
            source_name="百度贴吧",
            source_id=post_id,
            community=forum or topic_name or "百度贴吧",
            title=title,
            summary=summary,
            post_url=post_url,
            image_url=images[0]["url"],
            thumbnail_url=images[0]["thumbnail_url"],
            images=images,
            created_at=None,
            collected_at=now,
            score=None,
            comment_count=comment_count,
            tags=tags,
        )
        item["time_source"] = "collection"
        items.append(item)
    return items


def collect(config: dict, http: HttpClient, now: datetime | None = None) -> SourceResult:
    now = now or utc_now()
    try:
        payload = http.get_json(
            "https://tieba.baidu.com/hottopic/browse/topicList",
            referer="https://tieba.baidu.com/",
        )
    except HttpError as exc:
        return failed_result("tieba", f"贴吧热榜接口不可用: {exc}")
    data = payload.get("data") or {}
    raw_topics = data.get("topic_list") or (data.get("bang_topic") or {}).get("topic_list") or []
    topics = _select_topics(raw_topics, config)
    if not topics:
        return SourceResult(
            source="tieba",
            status="degraded",
            error="当前贴吧热榜没有匹配「梗图/表情包」的话题",
            details={"topics": [], "topic_count": len(raw_topics)},
            stats={"fetched": 0, "with_images": 0},
        )
    items: list[dict] = []
    seen_posts: set[str] = set()
    page_details = []
    for topic in topics:
        topic_id = topic.get("topic_id")
        if not topic_id:
            continue
        url = f"https://tieba.baidu.com/hottopic/browse/hottopic?topic_id={topic_id}"
        try:
            page = http.get_text(url, referer="https://tieba.baidu.com/")
            parsed = _parse_thread_page(
                page,
                topic=topic,
                now=now,
                max_threads=int(config.get("max_threads_per_topic", 10)),
            )
            added = 0
            for item in parsed:
                if item["source_id"] in seen_posts:
                    continue
                items.append(item)
                seen_posts.add(item["source_id"])
                added += 1
            page_details.append(
                {
                    "topic_id": topic_id,
                    "topic": clean_text(topic.get("topic_name"), 80),
                    "status": "ok",
                    "threads": len(parsed),
                    "added": added,
                }
            )
            LOGGER.info("tieba topic %s: %s threads", topic_id, added)
        except (HttpError, RuntimeError) as exc:
            page_details.append(
                {
                    "topic_id": topic_id,
                    "topic": clean_text(topic.get("topic_name"), 80),
                    "status": "failed",
                    "error": str(exc)[:200],
                }
            )
            LOGGER.warning("tieba topic %s failed: %s", topic_id, exc)
    stats = {
        "fetched": len(items),
        "with_images": sum(1 for item in items if item["image_url"]),
        "topics": len(topics),
    }
    if not items:
        return SourceResult(
            source="tieba",
            status="blocked",
            error="贴吧热点页没有返回带图片的帖子",
            details={"topics": page_details},
            stats=stats,
        )
    return SourceResult(
        source="tieba",
        status="degraded",
        items=items,
        error="帖子详情页对自动请求返回 403；当前使用公开热点页的帖子摘要、原帖链接和图片，已标记为 degraded",
        details={
            "topics": page_details,
            "degraded_reason": "thread_detail_403",
        },
        stats=stats,
    )
