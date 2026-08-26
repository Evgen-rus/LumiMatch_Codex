"""Catalogue collector: sitemap first, then HTTP category links, one bad site is isolated."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from .availability import effective_availability_status, supplier_availability_mode
from .discovery import discover_inventory
from .extract import parse_product_page
from .fetch import PublicFetcher
from .inventory import InventoryRecord
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
    adapter: str = "generic"
    discovery_method: str = "generic"
    sitemap_urls_total: int = 0
    sitemap_documents: int = 0
    category_pages_visited: int = 0
    cards_attempted: int = 0
    approximate_catalog_urls: int | None = None
    discovery_coverage: float | None = None
    discovery_quality: str = "unverified"
    parse_quality: str = "unverified"
    coverage_basis: str = "unverified"
    availability_counts: dict[str, int] = field(default_factory=dict)
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


def _quality(rate: float, denominator: int, *, empty: str = "broken") -> str:
    if not denominator:
        return empty
    if rate >= 0.5:
        return "healthy"
    if rate > 0:
        return "partial"
    return "broken"


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
            inventory = discover_inventory(
                self.fetcher, base_url, max_urls=max(max_pages * 4, 60)
            )
            result.adapter = inventory.adapter_name
            result.discovery_method = inventory.discovery_method
            result.sitemap_urls_total = inventory.sitemap_urls_total
            result.sitemap_documents = inventory.sitemap_documents
            result.category_pages_visited = inventory.category_pages_visited
            result.approximate_catalog_urls = inventory.approximate_catalog_urls
            result.coverage_basis = inventory.coverage_basis
            candidates = inventory.urls
            result.discovered_product_urls = len(candidates)
            for url in candidates:
                if result.cards_attempted >= max_pages:
                    break
                result.cards_attempted += 1
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
                    result.availability_counts[status] = result.availability_counts.get(status, 0) + 1
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
            result.parse_success_rate = (
                result.parsed_products / result.cards_attempted
                if result.cards_attempted
                else 0.0
            )
            result.parse_quality = _quality(
                result.parse_success_rate, result.cards_attempted
            )
            if result.approximate_catalog_urls:
                result.discovery_coverage = min(
                    result.discovered_product_urls / result.approximate_catalog_urls,
                    1.0,
                )
                result.discovery_quality = _quality(
                    result.discovery_coverage, result.approximate_catalog_urls
                )
            else:
                result.discovery_quality = _quality(
                    1.0 if result.discovered_product_urls else 0.0,
                    result.discovered_product_urls,
                    empty="unverified",
                )
            if not result.discovered_product_urls:
                result.status = "broken"
                result.coverage_quality = "discovery_broken"
            elif result.parse_quality == "broken":
                result.status = "partial"
                result.coverage_quality = "parse_broken"
            elif result.discovery_quality == "healthy" and result.parse_quality == "healthy":
                result.status = "healthy"
                result.coverage_quality = "healthy"
            else:
                result.status = "partial"
                result.coverage_quality = (
                    f"discovery_{result.discovery_quality}_parse_{result.parse_quality}"
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

    def collect_inventory(
        self,
        records: list[InventoryRecord],
        *,
        inventory_counts: dict[str, int] | None = None,
        download_images: bool = True,
    ) -> list[CollectionResult]:
        """Hydrate an explicit requirement-driven URL selection.

        Unlike ``collect_supplier`` this method never slices an inventory by
        position.  The caller has already selected URLs from the persistent
        product inventory using current FixtureRequirements.
        """
        counts = inventory_counts or {}
        grouped: dict[str, list[InventoryRecord]] = {}
        for record in records:
            grouped.setdefault(record.supplier, []).append(record)
        results: list[CollectionResult] = []
        try:
            for supplier, supplier_records in sorted(grouped.items()):
                result = CollectionResult(
                    supplier=supplier,
                    availability_mode=supplier_availability_mode(supplier),
                    discovered_product_urls=counts.get(supplier, len(supplier_records)),
                    coverage_basis="product_inventory",
                    discovery_quality="healthy" if counts.get(supplier, len(supplier_records)) else "broken",
                    discovery_method="requirement_driven_hydration",
                    adapter="inventory",
                    discovery_coverage=1.0 if counts.get(supplier, len(supplier_records)) else 0.0,
                )
                result.last_refresh = datetime.now(timezone.utc).isoformat()
                for record in supplier_records:
                    result.cards_attempted += 1
                    page = self.fetcher.get(record.product_url)
                    if not page:
                        result.failed_products += 1
                        continue
                    result.pages_visited += 1
                    html = page.content.decode("utf-8", "replace")
                    product = parse_product_page(html, page.final_url, supplier)
                    if not product:
                        result.failed_products += 1
                        continue
                    if download_images and product.primary_image_url:
                        saved = self.fetcher.save_image(product.primary_image_url)
                        if saved:
                            product.local_image_path = saved
                            result.images_saved += 1
                    self.store.upsert(product)
                    result.products_found += 1
                    result.parsed_products += 1
                    status = effective_availability_status(product)
                    result.availability_counts[status] = result.availability_counts.get(status, 0) + 1
                    if status == "in_stock":
                        result.in_stock_products += 1
                    elif status == "out_of_stock":
                        result.out_of_stock += 1
                    elif status == "discontinued":
                        result.discontinued += 1
                    elif status == "unknown":
                        result.unknown_products += 1
                result.parse_success_rate = result.parsed_products / result.cards_attempted if result.cards_attempted else 0.0
                result.parse_quality = _quality(result.parse_success_rate, result.cards_attempted)
                result.status = "healthy" if result.parse_quality == "healthy" else "partial" if result.parsed_products else "broken"
                result.coverage_quality = f"inventory_healthy_parse_{result.parse_quality}"
                results.append(result)
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
