"""Common result contract for pluggable gallery collectors."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceResult:
    source: str
    status: str
    items: list[dict] = field(default_factory=list)
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def has_items(self) -> bool:
        return bool(self.items)

    @property
    def healthy(self) -> bool:
        return self.status in {"ok", "degraded"} and self.has_items

    def public(self) -> dict:
        return {
            "source": self.source,
            "status": self.status,
            "item_count": len(self.items),
            "error": self.error,
            "details": self.details,
            "stats": self.stats,
        }


def failed_result(source: str, error: str) -> SourceResult:
    return SourceResult(
        source=source,
        status="blocked",
        error=error[:400],
        details={"reason": error[:400]},
        stats={"fetched": 0, "with_images": 0},
    )
