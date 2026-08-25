"""Catalogue collector: sitemap first, then HTTP category links, one bad site is isolated."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from .availability import effective_availability_status, supplier_availability_mode
from .discovery import discover_product_urls
from .extract import parse_product_page
from .fetch import PublicFetcher
from .storage import CatalogStore

LOGGER = logging.getLogger(__name__)


def supplier_name(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


@dataclass
class CollectionResult:
    supplier: str
    availability_mode: str = "stock_tracked"
    pages_visited: int = 0
    products_found: int = 0
    images_saved: int = 0
    discovered_product_urls: int = 0
    parsed_products: int = 0
    in_stock_products: int = 0
    out_of_stock: int = 0
    discontinued: int = 0
    unknown_products: int = 0
    failed_products: int = 0
    status: str = "not_started"
    coverage_quality: str = "unverified"
    parse_success_rate: float = 0.0
    last_refresh: str | None = None
    errors: list[str] = field(default_factory=list)


def coverage_state(discovered_product_urls: int, parsed_products: int) -> tuple[str, str, float]:
    """Classify inventory quality; discovery alone is never healthy coverage."""
    rate = parsed_products / discovered_product_urls if discovered_product_urls else 0.0
    if not discovered_product_urls or not parsed_products:
        return "broken", "broken", rate
    if rate >= 0.5:
        return "healthy", "healthy", rate
    return "partial", "partial", rate


class CatalogCollector:
    def __init__(
        self, store: CatalogStore, fetcher: PublicFetcher | None = None
    ) -> None:
        self.store = store
        self.fetcher = fetcher or PublicFetcher(store)
        self._owns_fetcher = fetcher is None

    def close(self) -> None:
        if self._owns_fetcher:
            self.fetcher.close()

    def collect_supplier(
        self, base_url: str, max_pages: int = 30, download_images: bool = True
    ) -> CollectionResult:
        base_url = base_url.rstrip("/")
        supplier = supplier_name(base_url)
        result = CollectionResult(
            supplier=supplier,
            availability_mode=supplier_availability_mode(supplier),
        )
        result.last_refresh = datetime.now(timezone.utc).isoformat()
        try:
            candidates, _, _ = discover_product_urls(
                self.fetcher, base_url, max_urls=max(max_pages * 4, 60)
            )
            result.discovered_product_urls = len(candidates)
            for url in candidates:
                if result.pages_visited >= max_pages:
                    break
                page = self.fetcher.get(url)
                if not page:
                    result.failed_products += 1
                    continue
                result.pages_visited += 1
                html = page.content.decode("utf-8", "replace")
                product = parse_product_page(html, page.final_url, result.supplier)
                if product:
                    if download_images and product.primary_image_url:
                        saved = self.fetcher.save_image(product.primary_image_url)
                        if saved:
                            product.local_image_path = saved
                            result.images_saved += 1
                    self.store.upsert(product)
                    result.products_found += 1
                    result.parsed_products += 1
                    status = effective_availability_status(product)
                    if status == "in_stock":
                        result.in_stock_products += 1
                    elif status == "out_of_stock":
                        result.out_of_stock += 1
                    elif status == "discontinued":
                        result.discontinued += 1
                    elif status == "unknown":
                        result.unknown_products += 1
                else:
                    result.failed_products += 1
            result.status, result.coverage_quality, result.parse_success_rate = coverage_state(
                result.discovered_product_urls, result.parsed_products
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            result.errors.append(message)
            result.status = "failed"
            LOGGER.exception("Supplier failed: %s", base_url)
        return result

    def collect(
        self, suppliers: list[str], max_pages: int = 30, download_images: bool = True
    ) -> list[CollectionResult]:
        results: list[CollectionResult] = []
        try:
            for base_url in suppliers:
                results.append(
                    self.collect_supplier(base_url, max_pages, download_images)
                )
        finally:
            self.close()
        return results

    def refresh_cached(self) -> int:
        """Re-parse cached pages and remove records proven to be category pages."""
        removed = 0
        for old_product in self.store.all():
            cached = self.store.get_cached_response(old_product.source_url)
            if not cached:
                continue
            refreshed = parse_product_page(
                cached.get("content", ""), old_product.source_url, old_product.supplier
            )
            if refreshed is None:
                self.store.delete(old_product.canonical_url)
                removed += 1
                continue
            if not refreshed.local_image_path and old_product.local_image_path:
                refreshed.local_image_path = old_product.local_image_path
            self.store.upsert(refreshed)
        return removed
