"""Small, dependency-free HTTP client for public JSON endpoints."""
from __future__ import annotations

import gzip
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field


LOGGER = logging.getLogger("meme_radar.http")


class FetchError(RuntimeError):
    """A source request failed after the configured retries."""


@dataclass
class HttpClient:
    timeout: float = 15.0
    retries: int = 1
    backoff: float = 2.0
    min_interval: float = 1.2
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    _last_request_at: dict[str, float] = field(default_factory=dict)

    def _throttle(self, url: str) -> None:
        host = urllib.parse.urlsplit(url).netloc.lower()
        last = self._last_request_at.get(host, 0.0)
        wait = self.min_interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)

    def get_json(self, url: str, referer: str | None = None, cookie: str | None = None) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                delay = self.backoff * (2 ** (attempt - 1))
                LOGGER.warning("retrying in %.1fs: %s", delay, _safe_url(url))
                time.sleep(delay)
            self._throttle(url)
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "close",
            }
            if referer:
                headers["Referer"] = referer
            if cookie:
                # Anonymous session identifiers only (for example Bilibili's
                # public buvid values).  No account cookie is ever accepted.
                headers["Cookie"] = cookie
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    if response.headers.get("Content-Encoding", "").lower() == "gzip":
                        raw = gzip.decompress(raw)
                    elif response.headers.get("Content-Encoding", "").lower() == "deflate":
                        raw = zlib.decompress(raw)
                    if not raw:
                        raise FetchError("empty response body")
                    payload = json.loads(raw.decode("utf-8", errors="replace"))
                    if not isinstance(payload, dict):
                        raise FetchError("JSON root is not an object")
                    self._last_request_at[urllib.parse.urlsplit(url).netloc.lower()] = time.monotonic()
                    return payload
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read(240).decode("utf-8", errors="replace").replace("\n", " ")
                except Exception:
                    pass
                last_error = FetchError(
                    f"HTTP {exc.code} from {_safe_url(url)}"
                    + (f": {body[:180]}" if body else "")
                )
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if exc.code == 429 and retry_after:
                    try:
                        time.sleep(min(float(retry_after), 12.0))
                    except ValueError:
                        pass
                if exc.code not in {408, 425, 429, 500, 502, 503, 504}:
                    break
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, FetchError) as exc:
                last_error = FetchError(f"{type(exc).__name__}: {exc}")
            finally:
                self._last_request_at[urllib.parse.urlsplit(url).netloc.lower()] = time.monotonic()
        raise FetchError(str(last_error or "unknown request failure"))


def _safe_url(url: str) -> str:
    """Keep error messages useful without echoing query strings that may hold tokens."""
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"
