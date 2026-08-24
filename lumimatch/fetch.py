"""Polite HTTP-first fetching with a bounded cache and optional browser fallback."""

from __future__ import annotations

import mimetypes
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .storage import CatalogStore


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content: bytes
    content_type: str
    from_cache: bool = False


class PublicFetcher:
    def __init__(
        self, store: CatalogStore, timeout: float = 20.0, delay: float = 0.15
    ) -> None:
        self.store = store
        self.delay = delay
        self.client = httpx.Client(
            headers={"User-Agent": "LumiMatch/0.1 (+public-catalog-audit)"},
            timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
            follow_redirects=True,
        )
        self._robots: dict[str, RobotFileParser | None] = {}

    def close(self) -> None:
        self.client.close()

    def _allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._robots:
            try:
                response = self.client.get(f"{root}/robots.txt")
                parser = RobotFileParser()
                parser.set_url(f"{root}/robots.txt")
                parser.parse(
                    response.text.splitlines() if response.status_code == 200 else []
                )
                self._robots[root] = parser
            except httpx.HTTPError:
                self._robots[root] = None
        parser = self._robots[root]
        return parser is None or parser.can_fetch(
            self.client.headers["User-Agent"], url
        )

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, TimeoutError)),
        wait=wait_exponential(multiplier=0.4, min=0.4, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _request(self, url: str) -> httpx.Response:
        response = self.client.get(url)
        response.raise_for_status()
        return response

    def get(self, url: str, *, use_cache: bool = True) -> FetchResult | None:
        if use_cache:
            cached = self.store.get_cached_response(url)
            if cached and cached.get("content"):
                return FetchResult(
                    url=url,
                    final_url=cached.get("final_url", url),
                    status_code=int(cached.get("status_code", 200)),
                    content=cached["content"].encode("utf-8"),
                    content_type=cached.get("content_type", "text/html"),
                    from_cache=True,
                )
        if not self._allowed(url):
            return None
        time.sleep(self.delay)
        try:
            response = self._request(url)
        except httpx.HTTPError:
            return None
        content_type = response.headers.get("content-type", "application/octet-stream")
        if "text" in content_type or "xml" in content_type or "json" in content_type:
            try:
                self.store.put_cached_response(
                    url,
                    {
                        "final_url": str(response.url),
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "content": response.text,
                    },
                )
            except (OSError, UnicodeDecodeError):
                pass
        return FetchResult(
            url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            content=response.content,
            content_type=content_type,
        )

    def save_image(self, url: str) -> str | None:
        if not url or url.startswith("data:") or url.lower().endswith(".svg"):
            return None
        stem = self.store.image_cache_path(url, ".bin").with_suffix("")
        for existing in stem.parent.glob(f"{stem.name}.*"):
            if existing.stat().st_size > 100:
                return str(existing)
        result = self.get(url, use_cache=False)
        if not result or not result.content_type.startswith("image/"):
            return None
        extension = (
            mimetypes.guess_extension(result.content_type.split(";", 1)[0]) or ".img"
        )
        target = self.store.image_cache_path(url, extension)
        try:
            target.write_bytes(result.content)
        except OSError:
            return None
        return str(target)
