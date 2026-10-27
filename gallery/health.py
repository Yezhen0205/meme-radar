"""Source health and consecutive-failure state for the gallery workflow."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .collectors import SourceResult
from .models import iso_utc


def load_health(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "sources": {}, "history": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {"schema_version": 1, "sources": {}, "history": []}


def update_health(
    previous: dict,
    results: dict[str, SourceResult],
    trends_status: str,
    items: list[dict],
    *,
    now: datetime,
    planned: list[str] | None = None,
) -> dict:
    previous_sources = previous.get("sources") or {}
    source_health: dict[str, dict] = {}
    for source, result in results.items():
        old = previous_sources.get(source) or {}
        failures = int(old.get("consecutive_failures") or 0)
        if result.status == "disabled":
            failures = 0
        elif result.status in {"blocked", "failed"} or not result.has_items:
            failures += 1
        elif result.status == "ok":
            failures = 0
        # degraded with items means partial success; keep the counter at zero.
        elif result.has_items:
            failures = 0
        source_health[source] = {
            "name": result.source,
            "status": result.status,
            "item_count": len(result.items),
            "error": result.error,
            "consecutive_failures": failures,
            "last_success_at": iso_utc(now) if result.has_items else old.get("last_success_at"),
            "last_attempt_at": iso_utc(now),
            "details": result.details,
        }
    source_health["trends"] = {
        "name": "公开热点榜",
        "status": trends_status,
        "item_count": 0,
        "error": None,
        "consecutive_failures": (
            int((previous_sources.get("trends") or {}).get("consecutive_failures") or 0) + 1
            if trends_status == "blocked"
            else 0
        ),
        "last_success_at": iso_utc(now) if trends_status in {"ok", "degraded"} else (previous_sources.get("trends") or {}).get("last_success_at"),
        "last_attempt_at": iso_utc(now),
        "details": {},
    }
    for planned_source in planned or []:
        source_health[planned_source] = {
            "name": planned_source,
            "status": "planned",
            "item_count": 0,
            "error": None,
            "consecutive_failures": 0,
            "last_success_at": None,
            "last_attempt_at": None,
            "details": {"reason": "not_implemented"},
        }

    primary = [source_health.get("reddit"), source_health.get("tieba")]
    primary = [entry for entry in primary if entry]
    if not items:
        overall = "blocked"
    elif any(entry["status"] == "blocked" for entry in primary):
        overall = "degraded" if len(primary) > 1 else "blocked"
    elif any(entry["status"] == "degraded" for entry in primary):
        overall = "degraded"
    else:
        overall = "ok"
    broken = sum(1 for item in items if item.get("image_status") == "broken")
    alerts = []
    if overall == "blocked":
        alerts.append("所有主要来源均未产出可用图片")
    for source, entry in source_health.items():
        if entry["consecutive_failures"] >= 3 and entry["status"] != "planned":
            alerts.append(f"{source} 已连续 {entry['consecutive_failures']} 轮失败")
    if items and broken / max(1, len(items)) > 0.5:
        alerts.append(f"本轮图片失效比例过高：{broken}/{len(items)}")
    history = list(previous.get("history") or [])
    history.append(
        {
            "at": iso_utc(now),
            "status": overall,
            "items": len(items),
            "new": None,
            "sources": {key: value["status"] for key, value in source_health.items() if value["status"] != "planned"},
            "errors": [value["error"] for value in source_health.values() if value.get("error")],
        }
    )
    health = {
        "schema_version": 1,
        "updated_at": iso_utc(now),
        "status": overall,
        "consecutive_failures": max(
            [entry["consecutive_failures"] for entry in source_health.values() if entry["status"] != "planned"] or [0]
        ),
        "last_success_at": iso_utc(now) if items else previous.get("last_success_at"),
        "alerts": alerts,
        "sources": source_health,
        "history": history[-20:],
    }
    return health
