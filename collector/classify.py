"""Transparent, keyword-based fun-content classification.

No model is called and no engagement metric is invented.  The rules are
intentionally simple; a false positive is visible in the UI and can be tuned in
this one file.
"""
from __future__ import annotations

import re
from typing import Any

from .normalize import clean_text


# Strong signals that a title/summary is intended to be funny or meme-like.
MEME_KEYWORDS = {
    "搞笑",
    "笑死",
    "笑不活",
    "笑疯",
    "哈哈哈",
    "哈哈",
    "沙雕",
    "抽象",
    "离谱",
    "整活",
    "鬼畜",
    "名场面",
    "翻车",
    "绷不住",
    "破防",
    "社死",
    "尴尬",
    "无语",
    "吐槽",
    "逆天",
    "乐子",
    "吃瓜",
    "段子",
    "神回复",
    "评论区",
    "表情包",
    "恶搞",
    "整蛊",
    "二创",
    "梗",
    "笑点",
    "幽默",
    "搞笑视频",
    "沙雕动画",
    "小剧场",
    "迷惑行为",
    "人类早期",
    "离谱操作",
}

# Bilibili's public category name is a useful, non-fabricated signal.  Strong
# categories are entertainment formats; weak categories only count when the
# title itself contains a meme word.
STRONG_FUNNY_TNAMES = {
    "搞笑",
    "鬼畜",
    "鬼畜调教",
    "综艺",
    "短片",
    "日常",
    "喵星人",
    "美食侦探",
    "娱乐杂谈",
    "仿妆cos",
    "同人·手书",
    "动物圈",
}

SERIOUS_HINTS = {
    "外交部",
    "国防部",
    "国务院",
    "习近平",
    "总统",
    "战争",
    "地震",
    "事故",
    "遇难",
    "犯罪",
    "警方通报",
    "纪委",
    "判决",
    "疫情",
}


def _contains_any(text: str, words: set[str]) -> list[str]:
    return [word for word in words if word in text]


def classify_item(
    *,
    title: str,
    summary: str = "",
    source_kind: str = "hot",
    tname: str | None = None,
    interest_category: str | None = None,
    label: str | None = None,
) -> tuple[str, list[str]]:
    """Return ``(category, tags)`` for a non-comment item."""
    title_text = title.lower()
    summary_text = summary.lower()
    text = f"{title_text} {summary_text}"
    tags: list[str] = []
    # A throwaway word in a long description (for example a phone review saying
    # a chip "翻车") should not turn a serious post into a meme.  The title and
    # the platform's own category are the signals we can explain.
    meme_hits = _contains_any(title_text, MEME_KEYWORDS)
    strong_category = bool(tname and _category_matches(tname, STRONG_FUNNY_TNAMES))
    serious = bool(_contains_any(text, SERIOUS_HINTS))

    if interest_category:
        tags.append(interest_category)
    if tname:
        tags.append(tname)
    if label:
        tags.append(label)

    is_meme = bool(meme_hits) or strong_category
    if is_meme:
        tags.extend(["热梗", "搞笑"] if meme_hits else ["热梗"])
        # In a serious headline a single word such as "翻车" should not turn the
        # item into entertainment.  The general hot tab still keeps it.
        if serious:
            is_meme = False
    if source_kind == "article":
        # Editorial explainers are still useful under 综合热点.
        pass
    category = "meme" if is_meme else "hot"
    return category, _dedupe_tags(tags)


def _dedupe_tags(tags: list[str]) -> list[str]:
    result: list[str] = []
    for tag in tags:
        tag = clean_text(tag, 16)
        if tag and tag not in result:
            result.append(tag)
        if len(result) >= 4:
            break
    return result


def _category_matches(tname: str, names: set[str]) -> bool:
    """Bilibili sub-categories are named like 手机游戏 or 鬼畜调教."""
    return any(name in tname for name in names)


def normalise_category(value: Any) -> str:
    value = str(value or "").strip().lower()
    return value if value in {"meme", "reply", "comment", "hot"} else "hot"


def keyword_tag_count(title: str, summary: str = "") -> int:
    text = f"{title} {summary}".lower()
    return sum(1 for word in MEME_KEYWORDS if word in text)


def title_words_for_grouping(text: str) -> set[str]:
    """Character bigrams plus ASCII words, used only for duplicate grouping."""
    text = re.sub(r"[\W_]+", " ", text.lower(), flags=re.UNICODE)
    words = {word for word in text.split() if len(word) >= 2}
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in chinese:
        for index in range(len(run) - 1):
            gram = run[index : index + 2]
            if gram not in {"一个", "什么", "怎么", "我们", "他们", "这个", "那个", "可以", "已经", "没有"}:
                words.add(gram)
    return words
