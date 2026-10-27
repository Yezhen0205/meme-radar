"""Auxiliary public hot-list keyword discovery.

This reuses the proven text hot-list adapters already in the repository.  The
keywords are candidate phrases, not an AI ranking, and are only used to tag and
gently boost matching gallery items.
"""
from __future__ import annotations

import html
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from collector.http import HttpClient as HotHttpClient
from collector.sources import collect_baidu_hot, collect_toutiao_hot, collect_weibo_hot

from ..http import HttpClient
from ..models import clean_text, utc_now

try:
    import jieba
except ImportError:  # optional fallback: character n-grams
    jieba = None


LOGGER = logging.getLogger("meme_radar.gallery.trends")
STOPWORDS = {
    "什么",
    "怎么",
    "一个",
    "我们",
    "他们",
    "这个",
    "那个",
    "可以",
    "已经",
    "没有",
    "回应",
    "官方",
    "网友",
    "视频",
    "最新",
    "今日",
    "热搜",
    "新闻",
    "中国",
    "美国",
    "曝光",
    "表示",
    "发布",
    "进行",
    "相关",
    "记者",
    "目前",
    "还是",
    "不是",
    "就是",
    "自己",
    "大家",
    "时候",
    "因为",
    "所以",
    "但是",
    "不当",
    "言论",
    "回应",
    "中国足协",
    "央视",
    "官方通报",
    "通报",
}
FALLBACK_TERMS = [
    "表情包",
    "梗",
    "抽象",
    "沙雕",
    "搞笑",
    "整活",
    "乐子",
    "游戏",
    "动漫",
    "二次元",
    "猫",
    "狗",
    "婚礼",
    "外卖",
    "老师",
    "学生",
    "姆巴佩",
    "皇马",
    "孙颖莎",
    "西甲",
    "央视",
    "图吧",
    "胶佬",
    "AI",
]
SOURCE_DEFS = [
    {
        "id": "weibo_hot",
        "name": "微博热搜",
        "url": "https://weibo.com/ajax/side/hotSearch",
        "referer": "https://weibo.com/",
        "limit": 40,
    },
    {
        "id": "baidu_hot",
        "name": "百度热搜",
        "url": "https://top.baidu.com/api/board?platform=wise&tab=realtime",
        "referer": "https://top.baidu.com/",
        "limit": 40,
    },
    {
        "id": "toutiao_hot",
        "name": "头条热榜",
        "url": "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
        "referer": "https://www.toutiao.com/",
        "limit": 40,
    },
]


@dataclass
class TrendResult:
    status: str = "degraded"
    keywords: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    error: str | None = None

    def public(self) -> dict:
        return {
            "status": self.status,
            "keywords": self.keywords,
            "sources": self.sources,
            "error": self.error,
        }


def _tokens(text: str) -> set[str]:
    text = html.unescape(text or "")
    text = re.sub(r"#[^#\s]{1,40}#", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE)
    result: set[str] = set()
    if jieba is not None:
        for word in jieba.lcut(text):
            word = word.strip().lower()
            if len(word) >= 2 and word not in STOPWORDS and not re.fullmatch(r"[\d_]+", word):
                result.add(word)
        return result
    # Fallback if jieba is unavailable: curated meme/trend vocabulary plus
    # complete short phrases.  No sliding n-grams, which produce fragments such
    # as "交部回应" and "应姆巴佩" and are not useful keywords.
    lowered = text.lower()
    for term in FALLBACK_TERMS:
        if term.lower() in lowered:
            result.add(term)
    for word in re.findall(r"[A-Za-z]{3,}", text):
        if word.lower() not in STOPWORDS:
            result.add(word.lower())
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,12}", text):
        if 2 <= len(sequence) <= 8 and sequence not in STOPWORDS:
            result.add(sequence)
    return result


def extract_keywords(titles: list[str], limit: int = 12) -> list[dict]:
    counts: Counter[str] = Counter()
    sources: defaultdict[str, set[str]] = defaultdict(set)
    for title in titles:
        for token in _tokens(title):
            if len(token) < 2:
                continue
            counts[token] += 1
            if title:
                sources[token].add("hot")
    # Remove a shorter fragment when a longer phrase with the same frequency is
    # present; keep a word that also stands alone elsewhere.
    candidates = []
    for word, count in counts.items():
        if count < 2:
            continue
        longer_same = [
            other
            for other in counts
            if other != word and word in other and counts[other] == count
        ]
        if longer_same:
            continue
        candidates.append((count, len(word), word))
    candidates.sort(key=lambda value: (value[0], value[1]), reverse=True)
    if not candidates:
        candidates = sorted(
            ((count, len(word), word) for word, count in counts.items() if len(word) >= 2),
            key=lambda value: (value[0], value[1]),
            reverse=True,
        )
    return [
        {"word": word, "count": count, "sources": sorted(sources[word]), "score": count}
        for count, _length, word in candidates[:limit]
    ]


def collect(config: dict, client: HttpClient, now: datetime | None = None) -> TrendResult:
    now = now or utc_now()
    if not config.get("enabled", True):
        return TrendResult(status="disabled", error="热点辅助已关闭")
    legacy = HotHttpClient(
        timeout=client.timeout,
        retries=0,
        backoff=client.backoff,
        min_interval=client.min_interval,
        user_agent=client.user_agent,
    )
    titles: list[str] = []
    statuses: list[dict] = []
    errors: list[str] = []
    for source in SOURCE_DEFS:
        if source["id"] not in config.get("sources", ["weibo_hot", "baidu_hot", "toutiao_hot"]):
            continue
        try:
            if source["id"] == "weibo_hot":
                items = collect_weibo_hot(source, legacy, now)
            elif source["id"] == "baidu_hot":
                items = collect_baidu_hot(source, legacy, now)
            else:
                items = collect_toutiao_hot(source, legacy, now)
            source_titles = [clean_text(item.get("title"), 160) for item in items]
            source_titles = [title for title in source_titles if title]
            titles.extend(source_titles)
            statuses.append(
                {"source": source["id"], "name": source["name"], "status": "ok", "items": len(source_titles)}
            )
            LOGGER.info("trends %s: %s titles", source["id"], len(source_titles))
        except Exception as exc:
            errors.append(f"{source['name']}: {exc}")
            statuses.append(
                {"source": source["id"], "name": source["name"], "status": "failed", "items": 0, "error": str(exc)[:200]}
            )
            LOGGER.warning("trends %s failed: %s", source["id"], exc)
    keywords = extract_keywords(titles, limit=int(config.get("max_keywords", 12)))
    if not titles:
        return TrendResult(status="blocked", keywords=[], sources=statuses, error="; ".join(errors) or "没有可用的热点榜")
    status = "ok" if keywords and len(errors) == 0 else "degraded"
    return TrendResult(status=status, keywords=keywords, sources=statuses, error="; ".join(errors) or None)
