"""Bounded sitemap and category-link discovery."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import deque
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .fetch import PublicFetcher


def xml_locations(content: bytes) -> list[str]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        matches = re.findall(
            rb"<loc>\s*(.*?)\s*</loc>", content, flags=re.IGNORECASE | re.DOTALL
        )
        return [match.decode("utf-8", "ignore").strip() for match in matches]
    return [
        element.text.strip()
        for element in root.iter()
        if element.tag.endswith("loc") and element.text
    ]


def sitemap_urls(
    fetcher: PublicFetcher, base_url: str, max_urls: int = 10000
) -> tuple[list[str], int | None]:
    root_url = base_url.rstrip("/") + "/sitemap.xml"
    result = fetcher.get(root_url)
    if not result:
        return [], None
    status = result.status_code
    queue = deque(xml_locations(result.content))
    urls: list[str] = []
    visited: set[str] = set()
    while queue and len(urls) < max_urls:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        if current.endswith(".xml") or "sitemap" in current.lower():
            child = fetcher.get(current)
            if child:
                queue.extend(xml_locations(child.content)[:max_urls])
            continue
        urls.append(current)
    return urls, status


def link_urls(html: str, page_url: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    host = urlparse(base_url).netloc.lower()
    result: list[str] = []
    for tag in soup.select("a[href]"):
        value = tag.get("href")
        if not value:
            continue
        absolute = urljoin(page_url, value).split("#", 1)[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != host:
            continue
        if absolute not in result:
            result.append(absolute)
    return result


def product_url_score(url: str) -> int:
    path = urlparse(url).path.lower()
    score = 0
    if any(
        marker in path for marker in ("/store/", "/product", "/tovar", "/item", ".html")
    ):
        score += 6
    if re.search(r"(?:[a-z]{2,}\d{3,}|\d{5,})", path):
        score += 4
    score += min(path.count("/"), 4)
    if any(marker in path for marker in ("/about/", "/news/", "/blog/", "/catalog/")):
        score -= 2
    if path.endswith(("/", "/catalog", "/store")):
        score -= 4
    return score
