"""Source adapters for public, anonymous JSON endpoints.

Every adapter returns normalised feed items.  No adapter logs in, solves a
captcha, rotates proxies, or invents an engagement number.
"""
from __future__ import annotations

import html
import logging
import re
import urllib.parse
from datetime import datetime
from typing import Any

from .classify import classify_item
from .http import FetchError, HttpClient
from .normalize import (
    clean_comment,
    clean_text,
    make_item,
    parse_source_time,
    split_title_summary,
    utc_now,
)


LOGGER = logging.getLogger("meme_radar.sources")
_SPAM = re.compile(r"(加微信|加vx|加VX|代练|博彩|彩票|刷单|返利|公众号|点击链接|扫码)", re.I)
_BVID = re.compile(r"^BV[0-9A-Za-z]+$")


def _require_ok(payload: dict, name: str) -> dict:
    code = payload.get("code")
    if code not in (None, 0):
        raise FetchError(f"{name} returned code={code} message={payload.get('message', '')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise FetchError(f"{name} returned no data object")
    return data


def fetch_bilibili_cookie(client: HttpClient) -> str | None:
    """Fetch Bilibili's anonymous buvid identifiers, just like its web frontend.

    These are not login credentials and the endpoint is public.  If it fails the
    adapters still try without the cookie rather than inventing one.
    """
    try:
        payload = client.get_json(
            "https://api.bilibili.com/x/frontend/finger/spi",
            "https://www.bilibili.com/",
        )
        data = _require_ok(payload, "bilibili spi")
        b3 = str(data.get("b_3") or "")
        b4 = str(data.get("b_4") or "")
        if b3 and b4:
            return f"buvid3={b3}; buvid4={b4}"
    except FetchError as exc:
        LOGGER.warning("bilibili anonymous session unavailable: %s", exc)
    return None


def collect_bilibili_popular(
    source: dict,
    client: HttpClient,
    now: datetime,
    cookie: str | None = None,
) -> tuple[list[dict], list[dict]]:
    payload = client.get_json(source["url"], source.get("referer"), cookie=cookie)
    data = _require_ok(payload, "bilibili popular")
    videos = data.get("list") or []
    if not isinstance(videos, list):
        raise FetchError("bilibili popular list is not an array")
    items: list[dict] = []
    raw_videos: list[dict] = []
    for index, video in enumerate(videos[: int(source.get("limit", 50))], start=1):
        bvid = clean_text(video.get("bvid"), 24)
        if not _BVID.match(bvid):
            continue
        stat = video.get("stat") or {}
        owner = video.get("owner") or {}
        title = clean_text(video.get("title"), 180)
        if not title:
            continue
        category, tags = classify_item(
            title=title,
            summary=video.get("desc") or "",
            source_kind="video",
            tname=video.get("tname"),
        )
        item = make_item(
            source_id=source["id"],
            source_name=source["name"],
            source_kind="video",
            native_id=bvid,
            title=title,
            summary=video.get("desc") or "",
            url=f"https://www.bilibili.com/video/{bvid}",
            published_at=parse_source_time(video.get("pubdate")),
            collected_at=now,
            category=category,
            tags=["B站热门", *tags],
            heat_label="播放",
            heat_value=stat.get("view"),
            heat_rank=index,
            author=owner.get("name"),
            image=video.get("pic"),
            context_id=bvid,
        )
        items.append(item)
        raw_videos.append(
            {
                "aid": video.get("aid"),
                "bvid": bvid,
                "title": title,
                "reply_count": int(stat.get("reply") or 0),
                "url": f"https://www.bilibili.com/video/{bvid}",
            }
        )
    if not items:
        raise FetchError("bilibili popular returned zero usable videos")
    return items, raw_videos


def _comment_url(video: dict, rpid: Any) -> str:
    return f"{video['url']}#reply{rpid}"


def _root_comment_item(
    source: dict,
    video: dict,
    reply: dict,
    now: datetime,
) -> dict | None:
    text = clean_comment((reply.get("content") or {}).get("message"), max_len=300)
    if len(re.sub(r"\s+", "", text)) < 3 or _SPAM.search(text):
        return None
    member = reply.get("member") or {}
    title, remainder = split_title_summary(text, title_len=90, summary_len=220)
    return make_item(
        source_id=source["id"],
        source_name=source["name"],
        source_kind="comment",
        native_id=reply.get("rpid"),
        title=title,
        summary=remainder,
        url=_comment_url(video, reply.get("rpid")),
        published_at=parse_source_time(reply.get("ctime")),
        collected_at=now,
        category="comment",
        tags=["B站评论区", "热评"],
        heat_label="点赞",
        heat_value=reply.get("like"),
        heat_rank=1,
        context=video["title"],
        context_url=video["url"],
        author=member.get("uname"),
        context_id=video["bvid"],
    )


def _subreply_item(
    source: dict,
    video: dict,
    reply: dict,
    root_text: str,
    root_author: str,
    now: datetime,
) -> dict | None:
    text = clean_comment((reply.get("content") or {}).get("message"), max_len=260)
    if len(re.sub(r"\s+", "", text)) < 3 or _SPAM.search(text):
        return None
    member = reply.get("member") or {}
    title, remainder = split_title_summary(text, title_len=90, summary_len=180)
    context_summary = f"回复 @{root_author}：{root_text[:90]}"
    if remainder:
        context_summary = f"{context_summary} · {remainder}"
    return make_item(
        source_id=source["id"],
        source_name=source["name"],
        source_kind="reply",
        native_id=reply.get("rpid"),
        title=title,
        summary=context_summary,
        url=_comment_url(video, reply.get("rpid")),
        published_at=parse_source_time(reply.get("ctime")),
        collected_at=now,
        category="reply",
        tags=["B站评论区", "神回复"],
        heat_label="点赞",
        heat_value=reply.get("like"),
        heat_rank=1,
        context=video["title"],
        context_url=video["url"],
        author=member.get("uname"),
        context_id=video["bvid"],
    )


def _assign_ranks(items: list[dict]) -> None:
    """Rank comments/replies inside their own category, never across sources."""
    for category in ("comment", "reply"):
        bucket = [item for item in items if item["category"] == category]
        bucket.sort(key=lambda item: (-(item["heat"] or {}).get("value", 0), item["id"]))
        for rank, item in enumerate(bucket, start=1):
            item["rank"] = rank
            if item.get("heat"):
                item["heat"]["rank"] = rank


def collect_bilibili_comments(
    source: dict,
    client: HttpClient,
    now: datetime,
    videos: list[dict],
    cookie: str | None = None,
) -> list[dict]:
    if not videos:
        raise FetchError("B站热门没有可用视频，跳过评论区采集")
    # Prefer videos with active discussion, but keep at most N to stay polite.
    candidates = sorted(videos, key=lambda video: -video.get("reply_count", 0))[
        : int(source.get("videos", 4))
    ]
    min_comment_likes = int(source.get("min_comment_likes", 20))
    min_reply_likes = int(source.get("min_reply_likes", 10))
    per_video_comments = int(source.get("comments_per_video", 10))
    per_video_replies = int(source.get("subreplies_per_video", 6))
    items: list[dict] = []
    seen_rpids: set[str] = set()
    errors: list[str] = []

    for video in candidates:
        aid = video.get("aid")
        if not aid:
            continue
        try:
            payload = client.get_json(
                f"https://api.bilibili.com/x/v2/reply/main?type=1&oid={aid}&mode=3&ps=20&pn=1",
                video["url"],
                cookie=cookie,
            )
            data = _require_ok(payload, "bilibili comments")
            roots = data.get("replies") or []
            roots = [reply for reply in roots if int(reply.get("like") or 0) >= min_comment_likes]
            roots.sort(key=lambda reply: -int(reply.get("like") or 0))
            roots = roots[:per_video_comments]
            for root in roots:
                rpid = str(root.get("rpid") or "")
                if not rpid or rpid in seen_rpids:
                    continue
                item = _root_comment_item(source, video, root, now)
                if item:
                    items.append(item)
                    seen_rpids.add(rpid)

            # Actual replies under the most-discussed roots become 神回复.
            reply_roots = sorted(
                roots,
                key=lambda reply: (-int(reply.get("rcount") or 0), -int(reply.get("like") or 0)),
            )[:2]
            for root in reply_roots:
                root_id = root.get("rpid")
                if not root_id:
                    continue
                try:
                    sub_payload = client.get_json(
                        f"https://api.bilibili.com/x/v2/reply/reply?type=1&oid={aid}&root={root_id}&ps=20&pn=1",
                        video["url"],
                        cookie=cookie,
                    )
                    sub_data = _require_ok(sub_payload, "bilibili sub-replies")
                    subreplies = sub_data.get("replies") or []
                    subreplies = [
                        reply
                        for reply in subreplies
                        if int(reply.get("like") or 0) >= min_reply_likes
                    ]
                    subreplies.sort(key=lambda reply: -int(reply.get("like") or 0))
                    root_member = root.get("member") or {}
                    root_text = clean_comment((root.get("content") or {}).get("message"), 80)
                    for subreply in subreplies[:per_video_replies]:
                        rpid = str(subreply.get("rpid") or "")
                        if not rpid or rpid in seen_rpids:
                            continue
                        item = _subreply_item(
                            source,
                            video,
                            subreply,
                            root_text=root_text,
                            root_author=root_member.get("uname") or "楼主",
                            now=now,
                        )
                        if item:
                            items.append(item)
                            seen_rpids.add(rpid)
                except FetchError as exc:
                    errors.append(str(exc))
                    LOGGER.warning("sub-replies failed for %s: %s", video["bvid"], exc)
        except FetchError as exc:
            errors.append(f"{video['bvid']}: {exc}")
            LOGGER.warning("comments failed for %s: %s", video["bvid"], exc)

    if not items:
        raise FetchError("; ".join(errors[-2:]) or "B站评论区没有获取到公开热评")
    _assign_ranks(items)
    LOGGER.info(
        "bilibili comments: %s items (%s comments, %s replies), %s errors",
        len(items),
        sum(1 for item in items if item["category"] == "comment"),
        sum(1 for item in items if item["category"] == "reply"),
        len(errors),
    )
    return items


def collect_weibo_hot(source: dict, client: HttpClient, now: datetime) -> list[dict]:
    payload = client.get_json(source["url"], source.get("referer"))
    if payload.get("ok") not in (1, True):
        raise FetchError(f"weibo hot returned ok={payload.get('ok')!r}")
    realtime = (payload.get("data") or {}).get("realtime") or []
    if not isinstance(realtime, list):
        raise FetchError("weibo realtime is not an array")
    items: list[dict] = []
    for index, raw in enumerate(realtime[: int(source.get("limit", 50))], start=1):
        word = clean_text(raw.get("word"), 120)
        if not word:
            continue
        rank = int(raw.get("realpos") or raw.get("rank") or index)
        label = clean_text(raw.get("label_name"), 8)
        word_scheme = clean_text(raw.get("word_scheme"), 140) or word
        query = word_scheme if word_scheme.startswith("#") else f"#{word}#" if raw.get("topic_flag") else word
        url = "https://s.weibo.com/weibo?q=" + urllib.parse.quote(query, safe="")
        category, tags = classify_item(
            title=word,
            summary=raw.get("note") or "",
            source_kind="hot",
            label=label,
        )
        summary = clean_text(raw.get("note"), 160)
        if not summary or summary == word:
            summary = f"微博热搜第 {rank} 位" + (f" · {label}" if label else "")
        item = make_item(
            source_id=source["id"],
            source_name=source["name"],
            source_kind="hot",
            native_id=word_scheme,
            title=word,
            summary=summary,
            url=url,
            collected_at=now,
            category=category,
            tags=["微博热搜", *tags],
            heat_label="热搜指数",
            heat_value=raw.get("num"),
            heat_rank=rank,
        )
        items.append(item)
    if not items:
        raise FetchError("weibo hot returned zero usable items")
    return items


def collect_baidu_hot(source: dict, client: HttpClient, now: datetime) -> list[dict]:
    payload = client.get_json(source["url"], source.get("referer"))
    if payload.get("success") is not True:
        raise FetchError("baidu hot returned success=false")
    cards = (payload.get("data") or {}).get("cards") or []
    raw_items: list[dict] = []
    for card in cards:
        for block in card.get("content") or []:
            for raw in block.get("content") or []:
                if isinstance(raw, dict):
                    raw_items.append(raw)
    items: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_items[: int(source.get("limit", 50))], start=1):
        word = clean_text(raw.get("word") or raw.get("query"), 120)
        if not word or word in seen:
            continue
        seen.add(word)
        rank = int(raw.get("index") or index)
        # The mobile URL returned by the API often redirects to a captcha page
        # for automated clients.  A standard search URL is the same public
        # lookup in a browser and is easier for a phone to open.
        url = "https://www.baidu.com/s?wd=" + urllib.parse.quote(word)
        category, tags = classify_item(title=word, source_kind="hot")
        summary = clean_text(raw.get("desc"), 160) or f"百度热搜第 {rank} 位"
        item = make_item(
            source_id=source["id"],
            source_name=source["name"],
            source_kind="hot",
            native_id=word,
            title=word,
            summary=summary,
            url=url,
            collected_at=now,
            category=category,
            tags=["百度热搜", *tags, *(["置顶"] if raw.get("isTop") else [])],
            heat_rank=rank,
        )
        items.append(item)
    if not items:
        raise FetchError("baidu hot returned zero usable items")
    return items


def collect_tieba_hot(source: dict, client: HttpClient, now: datetime) -> list[dict]:
    payload = client.get_json(source["url"], source.get("referer"))
    data = payload.get("data") or {}
    topics = data.get("topic_list") or (data.get("bang_topic") or {}).get("topic_list") or []
    if not isinstance(topics, list):
        raise FetchError("tieba topic list is not an array")
    items: list[dict] = []
    for index, raw in enumerate(topics[: int(source.get("limit", 30))], start=1):
        title = clean_text(raw.get("topic_name"), 160)
        if not title:
            continue
        url = html.unescape(raw.get("topic_url") or "")
        if not url:
            url = f"https://tieba.baidu.com/hottopic/browse/hottopic?topic_id={raw.get('topic_id', '')}"
        summary = clean_text(raw.get("abstract") or raw.get("topic_desc"), 300)
        if summary == title:
            summary = ""
        category, tags = classify_item(title=title, summary=summary, source_kind="hot")
        rank = int(raw.get("idx_num") or index)
        item = make_item(
            source_id=source["id"],
            source_name=source["name"],
            source_kind="hot",
            native_id=raw.get("topic_id") or title,
            title=title,
            summary=summary,
            url=url,
            published_at=parse_source_time(raw.get("create_time")),
            collected_at=now,
            category=category,
            tags=["贴吧热榜", *tags],
            heat_label="讨论",
            heat_value=raw.get("discuss_num"),
            heat_rank=rank,
        )
        items.append(item)
    if not items:
        raise FetchError("tieba hot returned zero usable topics")
    return items


def collect_toutiao_hot(source: dict, client: HttpClient, now: datetime) -> list[dict]:
    payload = client.get_json(source["url"], source.get("referer"))
    raw_items = payload.get("data") or []
    if not isinstance(raw_items, list):
        raise FetchError("toutiao hot data is not an array")
    items: list[dict] = []
    for index, raw in enumerate(raw_items[: int(source.get("limit", 50))], start=1):
        title = clean_text(raw.get("Title"), 180)
        if not title:
            continue
        url = raw.get("Url") or ""
        cluster_id = str(raw.get("ClusterIdStr") or "")
        if not str(url).startswith(("http://", "https://")):
            url = "https://www.toutiao.com/trending/" + cluster_id + "/"
        elif cluster_id:
            # Drop the per-impression tracking blob that the API appends.
            url = f"https://www.toutiao.com/trending/{cluster_id}/"
        interest = clean_text(raw.get("InterestCategory"), 16)
        label = clean_text(raw.get("Label"), 16)
        category, tags = classify_item(
            title=title,
            summary=raw.get("LabelDesc") or "",
            source_kind="hot",
            interest_category=interest,
            label=label,
        )
        summary = clean_text(raw.get("LabelDesc"), 160) or f"头条热榜第 {index} 位"
        item = make_item(
            source_id=source["id"],
            source_name=source["name"],
            source_kind="hot",
            native_id=raw.get("ClusterIdStr") or title,
            title=title,
            summary=summary,
            url=url,
            collected_at=now,
            category=category,
            tags=["头条热榜", *tags],
            heat_label="热度",
            heat_value=raw.get("HotValue"),
            heat_rank=index,
        )
        items.append(item)
    if not items:
        raise FetchError("toutiao hot returned zero usable items")
    return items


def collect_douyin_hot(source: dict, client: HttpClient, now: datetime) -> list[dict]:
    payload = client.get_json(source["url"], source.get("referer"))
    data = payload.get("data") or {}
    raw_items = data.get("word_list") or []
    if not isinstance(raw_items, list):
        raise FetchError("douyin word_list is not an array")
    items: list[dict] = []
    for index, raw in enumerate(raw_items[: int(source.get("limit", 50))], start=1):
        title = clean_text(raw.get("word"), 160)
        if not title:
            continue
        rank = int(raw.get("position") or index)
        url = "https://www.douyin.com/search/" + urllib.parse.quote(title, safe="")
        category, tags = classify_item(title=title, source_kind="hot")
        item = make_item(
            source_id=source["id"],
            source_name=source["name"],
            source_kind="hot",
            native_id=raw.get("sentence_id") or title,
            title=title,
            summary=f"抖音热榜第 {rank} 位",
            url=url,
            collected_at=now,
            category=category,
            tags=["抖音热榜", *tags],
            heat_label="热度",
            heat_value=raw.get("hot_value"),
            heat_rank=rank,
        )
        items.append(item)
    if not items:
        raise FetchError("douyin hot returned zero usable items")
    return items


def collect_zhihu_daily(source: dict, client: HttpClient, now: datetime) -> list[dict]:
    payload = client.get_json(source["url"], source.get("referer"))
    date_value = payload.get("date")
    published = parse_source_time(date_value)
    stories = payload.get("stories") or []
    if not isinstance(stories, list):
        raise FetchError("zhihu daily stories is not an array")
    items: list[dict] = []
    for index, raw in enumerate(stories[: int(source.get("limit", 10))], start=1):
        title = clean_text(raw.get("title"), 200)
        url = raw.get("url") or ""
        if not title or not url:
            continue
        hint = clean_text(raw.get("hint"), 160)
        category, tags = classify_item(title=title, summary=hint, source_kind="article")
        images = raw.get("images") or []
        item = make_item(
            source_id=source["id"],
            source_name=source["name"],
            source_kind="article",
            native_id=raw.get("id") or title,
            title=title,
            summary=hint,
            url=url,
            published_at=published,
            published_precision="date" if published else "datetime",
            collected_at=now,
            category=category,
            tags=["知乎日报", *tags],
            heat_rank=index,
            image=images[0] if isinstance(images, list) and images else None,
        )
        items.append(item)
    if not items:
        raise FetchError("zhihu daily returned zero usable stories")
    return items


ADAPTERS = {
    "bilibili_popular": collect_bilibili_popular,
    "bilibili_comments": collect_bilibili_comments,
    "weibo_hot": collect_weibo_hot,
    "baidu_hot": collect_baidu_hot,
    "tieba_hot": collect_tieba_hot,
    "toutiao_hot": collect_toutiao_hot,
    "douyin_hot": collect_douyin_hot,
    "zhihu_daily": collect_zhihu_daily,
}


def adapter_names() -> set[str]:
    return set(ADAPTERS)
