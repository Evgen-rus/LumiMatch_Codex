"""Catalogue collector: sitemap first, then HTTP category links, one bad site is isolated."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .discovery import link_urls, product_url_score, sitemap_urls
from .extract import parse_product_page
from .fetch import PublicFetcher
from .storage import CatalogStore

LOGGER = logging.getLogger(__name__)


def supplier_name(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


@dataclass
class CollectionResult:
    supplier: str
    pages_visited: int = 0
    products_found: int = 0
    images_saved: int = 0
    errors: list[str] = field(default_factory=list)


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
        result = CollectionResult(supplier=supplier_name(base_url))
        try:
            sitemap, _ = sitemap_urls(
                self.fetcher, base_url, max_urls=max(max_pages * 40, 200)
            )
            home = self.fetcher.get(base_url)
            seeds = [base_url]
            if home:
                seeds.extend(
                    link_urls(
                        home.content.decode("utf-8", "replace"),
                        home.final_url,
                        base_url,
                    )[:80]
                )
            candidates = sorted(
                set(sitemap + seeds), key=product_url_score, reverse=True
            )
            queue = list(candidates)
            visited: set[str] = set()
            while queue and result.pages_visited < max_pages:
                url = queue.pop(0)
                if url in visited or urlparse(url).query.lower().startswith(
                    ("utm_", "yclid")
                ):
                    continue
                visited.add(url)
                page = self.fetcher.get(url)
                if not page:
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
                    continue
                discovered = link_urls(html, page.final_url, base_url)
                new_links = [
                    link
                    for link in discovered
                    if link not in visited and link not in queue
                ]
                new_links.sort(key=product_url_score, reverse=True)
                queue.extend(new_links[: max_pages * 2])
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            result.errors.append(message)
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
