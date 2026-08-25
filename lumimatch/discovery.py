"""Bounded sitemap and category-link discovery."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .fetch import PublicFetcher


@dataclass
class DiscoveryInventory:
    """A supplier URL inventory plus evidence about how it was built."""

    urls: list[str] = field(default_factory=list)
    inspected_pages: int = 0
    category_pages_visited: int = 0
    sitemap_urls_total: int = 0
    sitemap_documents: int = 0
    approximate_catalog_urls: int | None = None
    discovery_method: str = "generic"
    adapter_name: str = "generic"
    coverage_basis: str = "unverified"
    notes: list[str] = field(default_factory=list)


class SupplierAdapter(Protocol):
    adapter_name: str

    def discover(
        self, fetcher: PublicFetcher, base_url: str, max_urls: int
    ) -> DiscoveryInventory:
        """Return arbitrary product URLs without knowing a requested SKU."""


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
    urls, status, _ = sitemap_inventory(fetcher, base_url, max_urls=max_urls)
    return urls, status


def sitemap_inventory(
    fetcher: PublicFetcher, base_url: str, max_urls: int = 10000
) -> tuple[list[str], int | None, int]:
    """Read a bounded sitemap tree and retain the number of child documents."""
    root_url = base_url.rstrip("/") + "/sitemap.xml"
    result = fetcher.get(root_url)
    if not result:
        return [], None, 0
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
    return urls, status, sitemap_documents


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


def _path_parts(url: str) -> list[str]:
    return [part for part in urlparse(url).path.split("/") if part]


def _same_host(url: str, base_url: str) -> bool:
    host = urlparse(base_url).netloc.lower().removeprefix("www.")
    return urlparse(url).netloc.lower().removeprefix("www.") == host


def _unique_limited(urls: list[str], max_urls: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        result.append(url)
        if len(result) >= max_urls:
            break
    return result


def _product_slug(slug: str) -> bool:
    folded = slug.casefold()
    return bool(re.search(r"\d", folded)) and not folded.startswith(("page", "index", "filter"))


def _category_fallback(
    fetcher: PublicFetcher,
    base_url: str,
    product_filter: Callable[[str], bool],
    inventory: DiscoveryInventory,
    initial_links: list[str],
    max_urls: int,
    max_pages: int = 12,
) -> list[str]:
    """Bounded category traversal used only when the sitemap is incomplete."""
    products: list[str] = []
    queue = [url for url in initial_links if _same_host(url, base_url)]
    inspected: set[str] = set()
    for category_url in queue[:max_pages]:
        if category_url in inspected:
            continue
        page = fetcher.get(category_url)
        inspected.add(category_url)
        if not page:
            continue
        inventory.inspected_pages += 1
        inventory.category_pages_visited += 1
        links = link_urls(page.content.decode("utf-8", "replace"), page.final_url, base_url)
        products.extend(url for url in links if product_filter(url))
        if len(products) >= max_urls:
            break
    return products


class GenericSupplierAdapter:
    adapter_name = "generic"

    def discover(
        self, fetcher: PublicFetcher, base_url: str, max_urls: int
    ) -> DiscoveryInventory:
        inventory = DiscoveryInventory(
            discovery_method="generic_sitemap_category",
            coverage_basis="sitemap_product_url_count",
        )
        sitemap, status, documents = sitemap_inventory(
            fetcher, base_url, max_urls=max(max_urls * 8, 500)
        )
        inventory.sitemap_urls_total = len(sitemap)
        inventory.sitemap_documents = documents
        sitemap_products = [url for url in sitemap if is_product_url(url)]
        inventory.approximate_catalog_urls = len(sitemap_products) or None
        products = list(sitemap_products)
        home = fetcher.get(base_url)
        if home:
            inventory.inspected_pages += 1
            links = link_urls(home.content.decode("utf-8", "replace"), home.final_url, base_url)
            products.extend(url for url in links if is_product_url(url))
            if len(products) < min(max_urls, 20):
                products.extend(
                    _category_fallback(
                        fetcher,
                        base_url,
                        is_product_url,
                        inventory,
                        [url for url in links if not is_product_url(url)],
                        max_urls,
                    )
                )
        inventory.urls = _unique_limited(products, max_urls)
        if status is None and not inventory.urls:
            inventory.coverage_basis = "no_sitemap_or_category_evidence"
        return inventory


class PathSitemapAdapter(GenericSupplierAdapter):
    """Adapter for suppliers whose product URL family is stable in the sitemap."""

    path_prefix: str = ""
    adapter_name = "path_sitemap"

    def product_filter(self, url: str, base_url: str) -> bool:
        return _same_host(url, base_url) and self.path_prefix in urlparse(url).path.casefold()

    def discover(
        self, fetcher: PublicFetcher, base_url: str, max_urls: int
    ) -> DiscoveryInventory:
        inventory = DiscoveryInventory(
            discovery_method=f"{self.adapter_name}_sitemap_category",
            coverage_basis="supplier_product_url_selector",
        )
        sitemap, _, documents = sitemap_inventory(
            fetcher, base_url, max_urls=max(max_urls * 10, 1000)
        )
        inventory.sitemap_urls_total = len(sitemap)
        inventory.sitemap_documents = documents
        selector = lambda url: self.product_filter(url, base_url)
        sitemap_products = [url for url in sitemap if selector(url)]
        inventory.approximate_catalog_urls = len(sitemap_products) or None
        products = list(sitemap_products)
        home = fetcher.get(base_url)
        if home:
            inventory.inspected_pages += 1
            links = link_urls(home.content.decode("utf-8", "replace"), home.final_url, base_url)
            products.extend(url for url in links if selector(url))
            products.extend(
                _category_fallback(
                    fetcher,
                    base_url,
                    selector,
                    inventory,
                    [url for url in links if not selector(url)],
                    max_urls,
                    max_pages=12,
                )
            )
        inventory.urls = _unique_limited(products, max_urls)
        return inventory


class FreyaAdapter(PathSitemapAdapter):
    adapter_name = "freya_products"
    path_prefix = "/products/"

    def product_filter(self, url: str, base_url: str) -> bool:
        parts = _path_parts(url)
        return (
            _same_host(url, base_url)
            and len(parts) >= 3
            and parts[0].casefold() == "products"
            and _product_slug(parts[-1])
        )


class LussoleAdapter(PathSitemapAdapter):
    adapter_name = "lussole_product_family"
    path_prefix = "/"

    def product_filter(self, url: str, base_url: str) -> bool:
        path = urlparse(url).path.casefold()
        slug = _path_parts(url)[-1] if _path_parts(url) else ""
        return _same_host(url, base_url) and bool(
            re.search(r"(?:^|[-_])lsp[-_]?\d", slug) and _product_slug(slug)
        ) and not any(marker in path for marker in ("/category/", "/news/", "/photos/", "/articles/", "/blog/"))


class KinkLightAdapter(GenericSupplierAdapter):
    adapter_name = "kink_numeric_html"

    @staticmethod
    def product_filter(url: str, base_url: str) -> bool:
        slug = _path_parts(url)[-1] if _path_parts(url) else ""
        return _same_host(url, base_url) and slug.endswith(".html") and bool(re.fullmatch(r"\d+\.html", slug))

    def discover(
        self, fetcher: PublicFetcher, base_url: str, max_urls: int
    ) -> DiscoveryInventory:
        inventory = DiscoveryInventory(
            discovery_method="kink_numeric_html_sitemap_category",
            coverage_basis="numeric_product_urls_in_sitemap",
        )
        sitemap, _, documents = sitemap_inventory(
            fetcher, base_url, max_urls=max(max_urls * 10, 1000)
        )
        inventory.sitemap_urls_total = len(sitemap)
        inventory.sitemap_documents = documents
        sitemap_products = [url for url in sitemap if self.product_filter(url, base_url)]
        inventory.approximate_catalog_urls = len(sitemap_products) or None
        products = list(sitemap_products)
        home = fetcher.get(base_url)
        if home:
            inventory.inspected_pages += 1
            links = link_urls(home.content.decode("utf-8", "replace"), home.final_url, base_url)
            products.extend(url for url in links if self.product_filter(url, base_url))
            products.extend(
                _category_fallback(
                    fetcher,
                    base_url,
                    lambda url: self.product_filter(url, base_url),
                    inventory,
                    [url for url in links if not self.product_filter(url, base_url)],
                    max_urls,
                )
            )
        inventory.urls = _unique_limited(products, max_urls)
        return inventory


class EurosvetAdapter(PathSitemapAdapter):
    adapter_name = "eurosvet_catalog_code"
    path_prefix = "/catalog/"

    def product_filter(self, url: str, base_url: str) -> bool:
        parts = _path_parts(url)
        slug = parts[-1] if parts else ""
        return (
            _same_host(url, base_url)
            and len(parts) >= 3
            and parts[0].casefold() == "catalog"
            and _product_slug(slug)
            and bool(re.search(r"\d{5,}", slug))
        )


class OdeonAdapter(PathSitemapAdapter):
    adapter_name = "odeon_catalog_links"
    path_prefix = "/catalog/"

    def product_filter(self, url: str, base_url: str) -> bool:
        parts = _path_parts(url)
        if not _same_host(url, base_url) or len(parts) < 4 or parts[0].casefold() != "catalog":
            return False
        slug = parts[-1].casefold()
        if slug in {"catalog", "index.php", "footer-description.php"} or "rasprod" in slug:
            return False
        return _product_slug(slug) or any(
            token in slug for token in ("svetilnik", "lyustra", "bra", "podves", "spot")
        )


class AmbrellaAdapter(PathSitemapAdapter):
    adapter_name = "ambrella_catalog_code"
    path_prefix = "/catalog/"

    def product_filter(self, url: str, base_url: str) -> bool:
        parts = _path_parts(url)
        slug = parts[-1] if parts else ""
        return (
            _same_host(url, base_url)
            and len(parts) >= 4
            and parts[0].casefold() == "catalog"
            and _product_slug(slug)
            and slug.casefold() not in {"index.php", "sect_sidebar.php"}
        )


SUPPLIER_ADAPTERS: dict[str, SupplierAdapter] = {
    "freya-light.com": FreyaAdapter(),
    "shop.lussole.ru": LussoleAdapter(),
    "kinklight.ru": KinkLightAdapter(),
    "eurosvet.ru": EurosvetAdapter(),
    "odeon-light.com": OdeonAdapter(),
    "ambrella.biz": AmbrellaAdapter(),
}


def get_supplier_adapter(base_url: str) -> SupplierAdapter:
    host = urlparse(base_url).netloc.lower().removeprefix("www.")
    return SUPPLIER_ADAPTERS.get(host, GenericSupplierAdapter())


def discover_inventory(
    fetcher: PublicFetcher, base_url: str, max_urls: int = 1000
) -> DiscoveryInventory:
    """Discover a supplier catalog without any requested SKU or golden input."""
    adapter = get_supplier_adapter(base_url)
    inventory = adapter.discover(fetcher, base_url.rstrip("/"), max_urls)
    inventory.adapter_name = adapter.adapter_name
    return inventory


def discover_product_urls(
    fetcher: PublicFetcher, base_url: str, max_urls: int = 1000
) -> tuple[list[str], int, list[str]]:
    """Separate product URL discovery from product fetching.

    Sitemaps are treated as URL inventories. Only product-like URLs are sent
    to the card parser; a small homepage/category fallback handles suppliers
    without a useful sitemap.
    """
    inventory = discover_inventory(fetcher, base_url, max_urls=max_urls)
    sitemap, _ = sitemap_urls(fetcher, base_url, max_urls=max(max_urls * 8, 500))
    return inventory.urls, inventory.inspected_pages, sitemap
