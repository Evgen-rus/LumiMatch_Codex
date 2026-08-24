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
    sitemap_documents = 0
    while queue and len(urls) < max_urls:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        if current.endswith(".xml") or "sitemap" in current.lower():
            if sitemap_documents >= 24:
                continue
            child = fetcher.get(current)
            sitemap_documents += 1
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


def is_product_url(url: str) -> bool:
    """Conservative URL classifier used before fetching product pages."""
    path = urlparse(url).path.lower()
    if any(marker in path for marker in ("/about/", "/news/", "/blog/", "/article/", "/search", "/filter")):
        return False
    if path.endswith(("/", ".xml", ".jpg", ".png", ".webp")):
        return False
    return product_url_score(url) >= 6 or bool(re.search(r"(?:/[a-zа-я-]{2,}\d{3,}|/\d{5,})(?:/|$)", path))


def discover_product_urls(
    fetcher: PublicFetcher, base_url: str, max_urls: int = 1000
) -> tuple[list[str], int, list[str]]:
    """Separate product URL discovery from product fetching.

    Sitemaps are treated as URL inventories. Only product-like URLs are sent
    to the card parser; a small homepage/category fallback handles suppliers
    without a useful sitemap.
    """
    sitemap, _ = sitemap_urls(fetcher, base_url, max_urls=max(max_urls * 8, 500))
    product_urls = [url for url in sitemap if is_product_url(url)]
    inspected = 0
    fallback_pages: list[str] = []
    home = fetcher.get(base_url)
    if home:
        inspected += 1
        links = link_urls(home.content.decode("utf-8", "replace"), home.final_url, base_url)
        product_urls.extend(url for url in links if is_product_url(url))
        fallback_pages.extend(url for url in links if not is_product_url(url))
    if len(product_urls) < min(max_urls, 20):
        for category_url in fallback_pages[:8]:
            if inspected >= 12:
                break
            page = fetcher.get(category_url)
            if not page:
                continue
            inspected += 1
            links = link_urls(page.content.decode("utf-8", "replace"), page.final_url, base_url)
            product_urls.extend(url for url in links if is_product_url(url))
    unique: list[str] = []
    for url in product_urls:
        if url not in unique:
            unique.append(url)
        if len(unique) >= max_urls:
            break
    return unique, inspected, sitemap
