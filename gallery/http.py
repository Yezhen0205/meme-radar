"""HTTP helpers for RSS, HTML and image validation."""
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
from typing import Any


LOGGER = logging.getLogger("meme_radar.gallery.http")
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class HttpError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: bytes = b""):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class Response:
    status: int
    url: str
    headers: dict[str, str]
    body: bytes


@dataclass
class ImageProbe:
    status: int | None
    content_type: str
    body: bytes
    error: str | None = None


@dataclass
class HttpClient:
    timeout: float = 20.0
    retries: int = 1
    backoff: float = 6.0
    min_interval: float = 1.2
    user_agent: str = DEFAULT_UA
    _last_request_at: dict[str, float] = field(default_factory=dict)

    def _throttle(self, url: str) -> None:
        host = urllib.parse.urlsplit(url).netloc.lower()
        last = self._last_request_at.get(host, 0.0)
        wait = self.min_interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)

    def request(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        range_header: str | None = None,
        max_bytes: int = 3_000_000,
        retry_statuses: set[int] | None = None,
    ) -> Response:
        retry_statuses = retry_statuses or {408, 425, 429, 500, 502, 503, 504}
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                delay = self.backoff * (2 ** (attempt - 1))
                LOGGER.warning("retry in %.1fs: %s", delay, _safe_url(url))
                time.sleep(delay)
            self._throttle(url)
            request_headers = {
                "User-Agent": self.user_agent,
                "Accept": "application/json,application/atom+xml,text/html,image/*,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "close",
            }
            if headers:
                request_headers.update(headers)
            if range_header:
                request_headers["Range"] = range_header
            request = urllib.request.Request(url, headers=request_headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read(max_bytes + 1)
                    encoding = (response.headers.get("Content-Encoding") or "").lower()
                    if encoding == "gzip":
                        raw = gzip.decompress(raw)
                    elif encoding == "deflate":
                        raw = zlib.decompress(raw)
                    if len(raw) > max_bytes:
                        raise HttpError(f"response exceeds {max_bytes} bytes", status=response.status)
                    self._last_request_at[urllib.parse.urlsplit(url).netloc.lower()] = time.monotonic()
                    return Response(
                        status=response.status,
                        url=response.geturl(),
                        headers={key.lower(): value for key, value in response.headers.items()},
                        body=raw,
                    )
            except urllib.error.HTTPError as exc:
                body = b""
                try:
                    body = exc.read(500)
                except Exception:
                    pass
                last_error = HttpError(
                    f"HTTP {exc.code} from {_safe_url(url)}",
                    status=exc.code,
                    body=body,
                )
                retry_after = (exc.headers.get("Retry-After") if exc.headers else None) or ""
                if exc.code in retry_statuses and attempt < self.retries:
                    try:
                        wait = min(float(retry_after), 60.0) if retry_after else 0
                    except ValueError:
                        wait = 0
                    if wait:
                        time.sleep(wait)
                    continue
                break
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                last_error = HttpError(f"{type(exc).__name__}: {exc}")
            finally:
                self._last_request_at[urllib.parse.urlsplit(url).netloc.lower()] = time.monotonic()
        raise HttpError(str(last_error or "request failed"))

    def get_text(self, url: str, *, referer: str | None = None, max_bytes: int = 2_000_000) -> str:
        headers = {"Accept": "application/atom+xml,application/xml,text/html,*/*"}
        if referer:
            headers["Referer"] = referer
        response = self.request(url, headers=headers, max_bytes=max_bytes)
        content_type = response.headers.get("content-type", "")
        charset = "utf-8"
        for part in content_type.split(";"):
            part = part.strip()
            if part.lower().startswith("charset="):
                charset = part.split("=", 1)[1].strip()
        return response.body.decode(charset or "utf-8", errors="replace")

    def get_json(self, url: str, *, referer: str | None = None) -> dict:
        headers = {"Accept": "application/json,text/plain,*/*"}
        if referer:
            headers["Referer"] = referer
        response = self.request(url, headers=headers)
        try:
            value = json.loads(response.body.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise HttpError(f"invalid JSON from {_safe_url(url)}: {exc}", status=response.status) from exc
        if not isinstance(value, dict):
            raise HttpError("JSON root is not an object", status=response.status)
        return value

    def probe_image(self, url: str, *, referer: str | None = None) -> ImageProbe:
        headers = {
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Range": "bytes=0-8191",
        }
        if referer:
            headers["Referer"] = referer
        try:
            response = self.request(url, headers=headers, range_header="bytes=0-8191", max_bytes=16_384)
            return ImageProbe(
                status=response.status,
                content_type=response.headers.get("content-type", ""),
                body=response.body,
            )
        except HttpError as exc:
            return ImageProbe(status=exc.status, content_type="", body=exc.body, error=str(exc))

    def download_image(self, url: str, *, referer: str | None = None, max_bytes: int = 3_000_000) -> bytes:
        headers = {
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        if referer:
            headers["Referer"] = referer
        response = self.request(url, headers=headers, max_bytes=max_bytes)
        if response.status not in {200, 206}:
            raise HttpError(f"image HTTP {response.status}", status=response.status)
        if len(response.body) > max_bytes:
            raise HttpError("image exceeds size limit", status=response.status)
        return response.body


def _safe_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"
