"""Shared paths, records and isolated HTTP/image cache for the visual spike.

This module deliberately does not import or write the production catalog.  It
may read the existing inventory and, when explicitly configured, reuse an
already downloaded production image as an input to the separate visual corpus.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import mimetypes
import re
import sqlite3
import threading
import time
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from PIL import Image

from lumimatch.extract import parse_product_page
from lumimatch.inventory import InventoryRecord, ProductInventoryStore
from lumimatch.models import CatalogProduct
from lumimatch.paths import ROOT
from lumimatch.storage import CatalogStore

SPIKE_DATA = ROOT / "data" / "visual_spike"
SPIKE_OUTPUT = ROOT / "output" / "visual_spike"
DEFAULT_INVENTORY = ROOT / "data" / "catalog" / "product_inventory_v4.sqlite3"
DEFAULT_CATALOG = ROOT / "data" / "catalog" / "production_v4.sqlite3"
DEFAULT_GOLDEN = ROOT / "data" / "golden" / "dan" / "golden_set.json"
DEFAULT_REQUIREMENTS = ROOT / "data" / "fixture_requirements.json"
DEFAULT_DISCOVERY = ROOT / "output" / "golden" / "dan" / "discovery_report.json"

SPIKE_SUPPLIERS = (
    "eurosvet.ru",
    "shop.lussole.ru",
    "freya-light.com",
    "kinklight.ru",
    "odeon-light.com",
)


def ensure_spike_dirs() -> None:
    for path in (
        SPIKE_DATA,
        SPIKE_DATA / "images",
        SPIKE_DATA / "http_cache",
        SPIKE_DATA / "embeddings",
        SPIKE_DATA / "oracle_eval",
        SPIKE_OUTPUT,
        SPIKE_OUTPUT / "review",
    ):
        path.mkdir(parents=True, exist_ok=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_sku(value: object | None) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", "", str(value or "").casefold())


def supplier_from_url(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class VisualProduct:
    supplier: str
    product_url: str
    canonical_url: str
    sku: str | None
    title: str | None
    brand: str | None
    category: str | None
    primary_image_url: str | None
    local_image_path: str | None
    image_hash: str | None
    image_source: str | None
    gallery_urls: tuple[str, ...] = ()
    status: str = "pending"
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "supplier": self.supplier,
            "product_url": self.product_url,
            "canonical_url": self.canonical_url,
            "sku": self.sku,
            "title": self.title,
            "brand": self.brand,
            "category": self.category,
            "primary_image_url": self.primary_image_url,
            "local_image_path": self.local_image_path,
            "image_hash": self.image_hash,
            "image_source": self.image_source,
            "gallery_urls": list(self.gallery_urls),
            "status": self.status,
            "error": self.error,
        }


@dataclass(frozen=True)
class VisualImage:
    image_hash: str
    source_url: str
    local_path: str
    width: int
    height: int
    byte_size: int
    content_type: str | None = None


@dataclass(frozen=True)
class VisualFetchResult:
    url: str
    final_url: str
    status_code: int
    content: bytes
    content_type: str
    from_cache: bool = False


class VisualCache:
    """SQLite metadata/HTML cache and content-hash image cache for the spike."""

    def __init__(self, db_path: Path | None = None) -> None:
        ensure_spike_dirs()
        self.db_path = db_path or (SPIKE_DATA / "visual_cache.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS http_cache (
                    url TEXT PRIMARY KEY,
                    final_url TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    content_type TEXT NOT NULL,
                    content_gzip BLOB NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS image_urls (
                    source_url TEXT PRIMARY KEY,
                    image_hash TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    content_type TEXT,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    byte_size INTEGER NOT NULL,
                    saved_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS image_products (
                    image_hash TEXT NOT NULL,
                    supplier TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY(image_hash, supplier, canonical_url)
                );
                """
            )

    def get_http(self, url: str) -> VisualFetchResult | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM http_cache WHERE url = ?", (url,)
            ).fetchone()
        if not row:
            return None
        try:
            content = gzip.decompress(row["content_gzip"])
        except (OSError, EOFError):
            return None
        return VisualFetchResult(
            url=url,
            final_url=row["final_url"],
            status_code=int(row["status_code"]),
            content=content,
            content_type=row["content_type"],
            from_cache=True,
        )

    def put_http(self, result: VisualFetchResult) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO http_cache(url, final_url, status_code, content_type, content_gzip, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    final_url=excluded.final_url,
                    status_code=excluded.status_code,
                    content_type=excluded.content_type,
                    content_gzip=excluded.content_gzip,
                    fetched_at=excluded.fetched_at
                """,
                (
                    result.url,
                    result.final_url,
                    result.status_code,
                    result.content_type,
                    gzip.compress(result.content),
                    utc_now(),
                ),
            )

    def get_image(self, source_url: str) -> VisualImage | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM image_urls WHERE source_url = ?", (source_url,)
            ).fetchone()
        if not row or not Path(row["local_path"]).exists():
            return None
        return VisualImage(
            row["image_hash"],
            source_url,
            row["local_path"],
            int(row["width"]),
            int(row["height"]),
            int(row["byte_size"]),
            row["content_type"],
        )

    def put_image(self, image: VisualImage) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO image_urls(source_url, image_hash, local_path, content_type, width, height, byte_size, saved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_url) DO UPDATE SET
                    image_hash=excluded.image_hash, local_path=excluded.local_path, content_type=excluded.content_type,
                    width=excluded.width, height=excluded.height, byte_size=excluded.byte_size, saved_at=excluded.saved_at
                """,
                (
                    image.source_url,
                    image.image_hash,
                    image.local_path,
                    image.content_type,
                    image.width,
                    image.height,
                    image.byte_size,
                    utc_now(),
                ),
            )

    def link_image_product(
        self, image_hash: str, supplier: str, canonical_url: str, position: int
    ) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO image_products(image_hash, supplier, canonical_url, position) VALUES (?, ?, ?, ?)",
                (image_hash, supplier, canonical_url, position),
            )


class VisualFetcher:
    """Polite, resumable HTTP fetcher that writes only to visual-spike cache."""

    def __init__(
        self,
        cache: VisualCache,
        *,
        timeout: float = 20.0,
        delay: float = 0.08,
        retries: int = 3,
    ) -> None:
        self.cache = cache
        self.delay = delay
        self.retries = retries
        self.client = httpx.Client(
            headers={
                "User-Agent": "LumiMatch-VisualSpike/0.1 (+public-catalog-research)"
            },
            timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
            follow_redirects=True,
        )
        self._last_request: dict[str, float] = {}
        self._request_lock = threading.Lock()
        self._robots: dict[str, RobotFileParser | None] = {}
        self.errors: list[str] = []

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

    def _rate_limit(self, url: str) -> None:
        domain = urlparse(url).netloc.lower()
        with self._request_lock:
            previous = self._last_request.get(domain)
            if previous is not None:
                remaining = self.delay - (time.monotonic() - previous)
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request[domain] = time.monotonic()

    def get(self, url: str, *, use_cache: bool = True) -> VisualFetchResult | None:
        if use_cache:
            cached = self.cache.get_http(url)
            if cached:
                return cached
        if not self._allowed(url):
            self.errors.append(f"robots_disallowed:{url}")
            return None
        for attempt in range(self.retries):
            self._rate_limit(url)
            try:
                response = self.client.get(url)
                response.raise_for_status()
                result = VisualFetchResult(
                    url,
                    str(response.url),
                    response.status_code,
                    response.content,
                    response.headers.get("content-type", "application/octet-stream"),
                )
                if (
                    result.content_type.startswith(("text/", "application/json"))
                    or "xml" in result.content_type
                ) and len(result.content) <= 8 * 1024 * 1024:
                    self.cache.put_http(result)
                return result
            except (httpx.HTTPError, OSError) as exc:
                if attempt + 1 == self.retries:
                    self.errors.append(f"{url}:{type(exc).__name__}:{exc}")
                else:
                    time.sleep(min(2.0, 0.4 * (2**attempt)))
        return None

    def save_image(self, url: str) -> VisualImage | None:
        if not url or url.startswith("data:") or url.lower().endswith(".svg"):
            return None
        cached = self.cache.get_image(url)
        if cached:
            return cached
        result = self.get(url, use_cache=False)
        if not result or not result.content_type.casefold().startswith("image/"):
            return None
        try:
            with Image.open(BytesIO(result.content)) as image:
                image.load()
                width, height = image.size
                image_hash = sha256_bytes(result.content)
                extension = (
                    mimetypes.guess_extension(result.content_type.split(";", 1)[0])
                    or ".img"
                ).lower()
                target = SPIKE_DATA / "images" / f"{image_hash}{extension}"
                if not target.exists():
                    target.write_bytes(result.content)
        except (OSError, ValueError):
            return None
        saved = VisualImage(
            image_hash,
            url,
            str(target),
            width,
            height,
            len(result.content),
            result.content_type,
        )
        self.cache.put_image(saved)
        return saved


class VisualCorpusStore:
    """Persistent natural/oracle corpus state and product-to-image mapping."""

    def __init__(self, db_path: Path | None = None) -> None:
        ensure_spike_dirs()
        self.db_path = db_path or (SPIKE_DATA / "visual_corpus.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    scope TEXT NOT NULL, canonical_url TEXT NOT NULL, supplier TEXT NOT NULL, product_url TEXT NOT NULL,
                    sku TEXT, title TEXT, brand TEXT, category TEXT, primary_image_url TEXT, local_image_path TEXT,
                    image_hash TEXT, image_source TEXT, gallery_urls_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL,
                    error TEXT, attempted_at TEXT, PRIMARY KEY(scope, canonical_url)
                );
                CREATE INDEX IF NOT EXISTS idx_visual_products_scope ON products(scope, status);
                CREATE INDEX IF NOT EXISTS idx_visual_products_sku ON products(scope, sku);
                CREATE TABLE IF NOT EXISTS product_images (
                    scope TEXT NOT NULL, canonical_url TEXT NOT NULL, position INTEGER NOT NULL, image_url TEXT,
                    image_hash TEXT, local_image_path TEXT, is_primary INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
                    PRIMARY KEY(scope, canonical_url, position)
                );
                """
            )

    def upsert(
        self,
        product: VisualProduct,
        *,
        scope: str = "natural",
        attempted_at: str | None = None,
    ) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO products(scope, canonical_url, supplier, product_url, sku, title, brand, category,
                    primary_image_url, local_image_path, image_hash, image_source, gallery_urls_json, status, error, attempted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, canonical_url) DO UPDATE SET
                    supplier=excluded.supplier, product_url=excluded.product_url, sku=COALESCE(excluded.sku, products.sku),
                    title=COALESCE(excluded.title, products.title), brand=COALESCE(excluded.brand, products.brand),
                    category=COALESCE(excluded.category, products.category), primary_image_url=COALESCE(excluded.primary_image_url, products.primary_image_url),
                    local_image_path=COALESCE(excluded.local_image_path, products.local_image_path), image_hash=COALESCE(excluded.image_hash, products.image_hash),
                    image_source=COALESCE(excluded.image_source, products.image_source), gallery_urls_json=excluded.gallery_urls_json,
                    status=excluded.status, error=excluded.error, attempted_at=excluded.attempted_at
                """,
                (
                    scope,
                    product.canonical_url,
                    product.supplier,
                    product.product_url,
                    product.sku,
                    product.title,
                    product.brand,
                    product.category,
                    product.primary_image_url,
                    product.local_image_path,
                    product.image_hash,
                    product.image_source,
                    json.dumps(list(product.gallery_urls), ensure_ascii=False),
                    product.status,
                    product.error,
                    attempted_at or utc_now(),
                ),
            )

    def upsert_image(
        self,
        scope: str,
        canonical_url: str,
        position: int,
        image_url: str | None,
        image: VisualImage | None,
        *,
        is_primary: bool,
        status: str = "ready",
    ) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO product_images(scope, canonical_url, position, image_url, image_hash, local_image_path, is_primary, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, canonical_url, position) DO UPDATE SET
                    image_url=excluded.image_url, image_hash=excluded.image_hash, local_image_path=excluded.local_image_path,
                    is_primary=excluded.is_primary, status=excluded.status
                """,
                (
                    scope,
                    canonical_url,
                    position,
                    image_url,
                    image.image_hash if image else None,
                    image.local_path if image else None,
                    int(is_primary),
                    status,
                ),
            )

    def get(self, canonical_url: str, *, scope: str = "natural") -> sqlite3.Row | None:
        with self._connect() as con:
            return con.execute(
                "SELECT * FROM products WHERE scope = ? AND canonical_url = ?",
                (scope, canonical_url),
            ).fetchone()

    def all(
        self, *, scope: str = "natural", ready_only: bool = False
    ) -> list[VisualProduct]:
        query = "SELECT * FROM products WHERE scope = ?"
        params: list[object] = [scope]
        if ready_only:
            query += " AND status = 'ready' AND local_image_path IS NOT NULL"
        query += " ORDER BY supplier, canonical_url"
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [
            VisualProduct(
                row["supplier"],
                row["product_url"],
                row["canonical_url"],
                row["sku"],
                row["title"],
                row["brand"],
                row["category"],
                row["primary_image_url"],
                row["local_image_path"],
                row["image_hash"],
                row["image_source"],
                tuple(json.loads(row["gallery_urls_json"] or "[]")),
                row["status"],
                row["error"],
            )
            for row in rows
        ]

    def images(
        self,
        canonical_url: str,
        *,
        scope: str = "natural",
        max_images: int | None = None,
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM product_images WHERE scope = ? AND canonical_url = ? AND status = 'ready' ORDER BY position"
        params: list[object] = [scope, canonical_url]
        if max_images:
            query += " LIMIT ?"
            params.append(max_images)
        with self._connect() as con:
            return con.execute(query, params).fetchall()

    def counts(self, *, scope: str = "natural") -> dict[str, int]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT status, COUNT(*) AS count FROM products WHERE scope = ? GROUP BY status",
                (scope,),
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}


def _safe_absolute(value: object, base_url: str) -> str | None:
    if not value:
        return None
    candidate = urljoin(base_url, str(value).strip()).split("#", 1)[0]
    if not candidate.startswith(
        ("http://", "https://")
    ) or candidate.casefold().endswith(".svg"):
        return None
    return candidate


_BAD_IMAGE_MARKERS = (
    "logo",
    "icon",
    "banner",
    "recommend",
    "related",
    "certificate",
    "sertifikat",
    "sprite",
    "share",
    "social",
    "counter",
)


def _fallback_visual_metadata(
    html: str, url: str
) -> tuple[str | None, str | None, list[str], str | None]:
    """Minimal image-first fallback when the full product extractor rejects a page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("h1") or soup.find("meta", attrs={"property": "og:title"})
    title = (
        title_tag.get("content")
        if getattr(title_tag, "name", None) == "meta"
        else title_tag.get_text(" ", strip=True)
        if title_tag
        else None
    )
    sku = None
    for tag in soup.select(
        "[itemprop='sku'], meta[name='sku'], meta[property='product:retailer_item_id']"
    ):
        sku = tag.get("content") or tag.get_text(" ", strip=True)
        if sku:
            break
    images: list[str] = []

    def add(value: object) -> None:
        image_url = _safe_absolute(value, url)
        if not image_url or any(
            marker in image_url.casefold() for marker in _BAD_IMAGE_MARKERS
        ):
            return
        if image_url not in images:
            images.append(image_url)

    for script in soup.select("script[type='application/ld+json']"):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        candidates: list[dict[str, object]] = []
        if isinstance(payload, dict):
            candidates.append(payload)
            graph = payload.get("@graph")
            if isinstance(graph, list):
                candidates.extend(item for item in graph if isinstance(item, dict))
        elif isinstance(payload, list):
            candidates.extend(item for item in payload if isinstance(item, dict))
        for item in candidates:
            kind = str(item.get("@type", ""))
            if "Product" not in kind and not item.get("image"):
                continue
            value = item.get("image")
            values = value if isinstance(value, list) else [value]
            for image in values:
                if isinstance(image, dict):
                    image = image.get("url") or image.get("contentUrl")
                add(image)
            sku = sku or str(item.get("sku") or item.get("mpn") or "") or None

    selectors = (
        ".product-gallery img",
        ".product-images img",
        ".gallery img",
        "[data-gallery] img",
        "[class*='product-photo'] img",
        "[class*='product-image'] img",
    )
    for tag in soup.select(",".join(selectors)):
        parent_text = " ".join(tag.parent.get("class", [])) if tag.parent else ""
        if any(marker in parent_text.casefold() for marker in _BAD_IMAGE_MARKERS):
            continue
        for attribute in ("src", "data-src", "data-original", "data-lazy-src"):
            add(tag.get(attribute))
    if not images:
        for tag in soup.select("meta[property='og:image'], meta[name='twitter:image']"):
            add(tag.get("content"))
            if images:
                break
    canonical = soup.find("link", rel="canonical")
    canonical_url = _safe_absolute(canonical.get("href"), url) if canonical else url
    return title, sku, images[:12], canonical_url


def _production_image_lookup(catalog_path: Path) -> dict[str, CatalogProduct]:
    if not catalog_path.exists():
        return {}
    try:
        return {
            product.canonical_url: product
            for product in CatalogStore(catalog_path).all()
        }
    except (OSError, sqlite3.Error, ValueError):
        return {}


def _register_local_image(
    cache: VisualCache, source_url: str, local_path: str
) -> VisualImage | None:
    path = Path(local_path)
    if not path.exists():
        return None
    try:
        with Image.open(path) as image:
            image.load()
            image_hash = sha256_file(path)
            target = (
                SPIKE_DATA / "images" / f"{image_hash}{path.suffix.lower() or '.img'}"
            )
            if not target.exists():
                target.write_bytes(path.read_bytes())
            saved = VisualImage(
                image_hash,
                source_url,
                str(target),
                image.width,
                image.height,
                target.stat().st_size,
                Image.MIME.get(image.format),
            )
        cache.put_image(saved)
        return saved
    except (OSError, ValueError):
        return None


def _inventory_records(
    inventory_db: Path, suppliers: set[str], max_products: int | None
) -> list[InventoryRecord]:
    records = ProductInventoryStore(inventory_db).all(suppliers)
    if max_products is not None and max_products < len(records):
        if max_products <= 0:
            return []
        if max_products == 1:
            return [records[0]]
        # Inventory rows are often grouped by source category.  A deterministic
        # evenly-spaced sample prevents a bounded spike from measuring only the
        # first category while keeping resume behaviour stable.
        indexes = {
            round(index * (len(records) - 1) / (max_products - 1))
            for index in range(max_products)
        }
        return [record for index, record in enumerate(records) if index in indexes]
    return records


def select_natural_records(
    inventory_db: Path, suppliers: Iterable[str] = SPIKE_SUPPLIERS
) -> list[InventoryRecord]:
    """Return natural-corpus inputs from inventory only, without golden access."""
    supplier_set = {
        supplier.lower().removeprefix("https://").removeprefix("http://").rstrip("/")
        for supplier in suppliers
    }
    return _inventory_records(inventory_db, supplier_set, None)


def _visual_product_from_record(
    record: InventoryRecord,
    product: CatalogProduct | None,
    *,
    status: str,
    error: str | None = None,
    title: str | None = None,
    sku: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    primary_url: str | None = None,
    gallery: Iterable[str] = (),
    local: VisualImage | None = None,
    image_source: str | None = None,
) -> VisualProduct:
    return VisualProduct(
        record.supplier,
        record.product_url,
        record.canonical_url,
        sku or (product.sku if product else None) or record.sku,
        title or (product.name if product else None) or record.title,
        brand or (product.brand if product else None) or record.brand,
        category or (product.category if product else None) or record.category,
        primary_url
        or (product.primary_image_url if product else None)
        or record.image_url,
        local.local_path if local else (product.local_image_path if product else None),
        local.image_hash if local else None,
        image_source or (product.image_source if product else None),
        tuple(dict.fromkeys(value for value in gallery if value)),
        status,
        error,
    )


def _seed_existing_catalog_images(
    store: VisualCorpusStore,
    cache: VisualCache,
    records: list[InventoryRecord],
    catalog_products: dict[str, CatalogProduct],
) -> int:
    """Reuse already hydrated inventory cards without reading golden data."""
    record_by_url = {record.canonical_url: record for record in records}
    seeded = 0
    for canonical_url, product in catalog_products.items():
        record = record_by_url.get(canonical_url)
        if not record or not product.local_image_path or not product.primary_image_url:
            continue
        saved = _register_local_image(
            cache, product.primary_image_url, product.local_image_path
        )
        if not saved:
            continue
        visual = _visual_product_from_record(
            record,
            product,
            status="ready",
            title=product.name,
            sku=product.sku,
            brand=product.brand,
            category=product.category,
            primary_url=product.primary_image_url,
            gallery=product.image_urls,
            local=saved,
            image_source=product.image_source or "existing_production_catalog_image",
        )
        store.upsert(visual, scope="natural")
        store.upsert_image(
            "natural",
            canonical_url,
            1,
            product.primary_image_url,
            saved,
            is_primary=True,
        )
        cache.link_image_product(saved.image_hash, record.supplier, canonical_url, 1)
        seeded += 1
    return seeded


def build_natural_corpus(
    inventory_db: Path = DEFAULT_INVENTORY,
    corpus_db: Path | None = None,
    *,
    suppliers: Iterable[str] = SPIKE_SUPPLIERS,
    catalog_db: Path = DEFAULT_CATALOG,
    max_products: int | None = None,
    gallery_images: int = 1,
    fresh: bool = False,
    timeout: float = 20.0,
    delay: float = 0.08,
    seed_only: bool = False,
    workers: int = 4,
) -> dict[str, object]:
    """Build or resume the natural visual corpus from inventory only."""
    ensure_spike_dirs()
    started = time.monotonic()
    supplier_set = {
        supplier.lower().removeprefix("https://").removeprefix("http://").rstrip("/")
        for supplier in suppliers
    }
    records = _inventory_records(inventory_db, supplier_set, max_products)
    store = VisualCorpusStore(corpus_db)
    cache = VisualCache()
    fetcher = VisualFetcher(cache, timeout=timeout, delay=delay)
    existing_products = _production_image_lookup(catalog_db)
    stats: dict[str, Any] = {
        "inventory_urls": len(records),
        "pages_attempted": 0,
        "pages_successful": 0,
        "product_images_found": 0,
        "images_downloaded": 0,
        "images_reused": 0,
        "failed": 0,
        "skipped_cached": 0,
        "per_supplier": {},
        "gallery_images_requested": max(1, min(gallery_images, 3)),
        "started_at": utc_now(),
    }
    stats["seeded_from_existing_catalog"] = _seed_existing_catalog_images(
        store, cache, records, existing_products
    )
    stats["images_reused"] += stats["seeded_from_existing_catalog"]

    def supplier_stats(supplier: str) -> dict[str, int]:
        return stats["per_supplier"].setdefault(
            supplier,
            {
                "inventory_urls": 0,
                "pages_attempted": 0,
                "pages_successful": 0,
                "images_found": 0,
                "images_downloaded": 0,
                "failed": 0,
            },
        )

    process_records = [] if seed_only else records
    page_futures: dict[str, Future[VisualFetchResult | None]] = {}
    executor: ThreadPoolExecutor | None = None
    if process_records and workers > 1:
        executor = ThreadPoolExecutor(max_workers=max(1, min(workers, 8)))
        for record in process_records:
            existing = store.get(record.canonical_url)
            if (
                existing
                and not fresh
                and existing["status"] == "ready"
                and existing["local_image_path"]
                and Path(existing["local_image_path"]).exists()
                and (
                    gallery_images <= 1
                    or len(
                        store.images(
                            record.canonical_url,
                            scope="natural",
                            max_images=min(gallery_images, 3),
                        )
                    )
                    >= min(gallery_images, 3)
                )
            ):
                continue
            existing_product = existing_products.get(record.canonical_url)
            primary = record.image_url or (
                existing_product.primary_image_url if existing_product else None
            )
            if not primary:
                page_futures[record.canonical_url] = executor.submit(
                    fetcher.get, record.product_url
                )
    try:
        for record in process_records:
            sstats = supplier_stats(record.supplier)
            sstats["inventory_urls"] += 1
            existing = store.get(record.canonical_url)
            if (
                existing
                and not fresh
                and existing["status"] == "ready"
                and existing["local_image_path"]
                and Path(existing["local_image_path"]).exists()
                and (
                    gallery_images <= 1
                    or len(
                        store.images(
                            record.canonical_url,
                            scope="natural",
                            max_images=min(gallery_images, 3),
                        )
                    )
                    >= min(gallery_images, 3)
                )
            ):
                stats["skipped_cached"] += 1
                continue
            product = existing_products.get(record.canonical_url)
            title = product.name if product else record.title
            sku = product.sku if product else record.sku
            brand = product.brand if product else record.brand
            category = product.category if product else record.category
            image_urls: list[str] = []
            image_source: str | None = None
            primary_url = record.image_url or (
                product.primary_image_url if product else None
            )
            if not primary_url:
                future = page_futures.get(record.canonical_url)
                page = future.result() if future else fetcher.get(record.product_url)
                stats["pages_attempted"] += 1
                sstats["pages_attempted"] += 1
                if page:
                    stats["pages_successful"] += 1
                    sstats["pages_successful"] += 1
                    html = page.content.decode("utf-8", "replace")
                    parsed = parse_product_page(html, page.final_url, record.supplier)
                    if parsed:
                        product = parsed
                        title, sku, brand, category = (
                            parsed.name,
                            parsed.sku,
                            parsed.brand,
                            parsed.category,
                        )
                        primary_url = parsed.primary_image_url
                        image_urls = list(parsed.image_urls)
                        image_source = parsed.image_source
                    else:
                        title, sku, image_urls, _ = _fallback_visual_metadata(
                            html, page.final_url
                        )
                        primary_url = image_urls[0] if image_urls else None
                        image_source = "fallback_image_metadata"
            if primary_url and not image_urls:
                image_urls = [primary_url]
            if primary_url and primary_url not in image_urls:
                image_urls.insert(0, primary_url)
            image_urls = list(dict.fromkeys(image_urls))[:12]
            if not primary_url:
                stats["failed"] += 1
                sstats["failed"] += 1
                store.upsert(
                    _visual_product_from_record(
                        record,
                        product,
                        status="no_image",
                        error="no_primary_image_found",
                    )
                )
                continue
            stats["product_images_found"] += 1
            sstats["images_found"] += 1
            selected_urls = image_urls[: max(1, min(gallery_images, 3))]
            saved_images: list[VisualImage | None] = []
            for position, image_url in enumerate(selected_urls, start=1):
                saved = cache.get_image(image_url)
                if not saved and position == 1 and product and product.local_image_path:
                    saved = _register_local_image(
                        cache, image_url, product.local_image_path
                    )
                    if saved:
                        stats["images_reused"] += 1
                if not saved:
                    saved = fetcher.save_image(image_url)
                    if saved:
                        stats["images_downloaded"] += 1
                        sstats["images_downloaded"] += 1
                saved_images.append(saved)
                store.upsert_image(
                    "natural",
                    record.canonical_url,
                    position,
                    image_url,
                    saved,
                    is_primary=position == 1,
                    status="ready" if saved else "failed",
                )
                if saved:
                    cache.link_image_product(
                        saved.image_hash,
                        record.supplier,
                        record.canonical_url,
                        position,
                    )
            primary_saved = saved_images[0] if saved_images else None
            if not primary_saved:
                stats["failed"] += 1
                sstats["failed"] += 1
                store.upsert(
                    _visual_product_from_record(
                        record,
                        product,
                        status="image_failed",
                        error="primary_image_download_failed",
                        title=title,
                        sku=sku,
                        brand=brand,
                        category=category,
                        primary_url=primary_url,
                        gallery=image_urls,
                        image_source=image_source,
                    )
                )
                continue
            store.upsert(
                _visual_product_from_record(
                    record,
                    product,
                    status="ready",
                    title=title,
                    sku=sku,
                    brand=brand,
                    category=category,
                    primary_url=primary_url,
                    gallery=image_urls,
                    local=primary_saved,
                    image_source=image_source or "inventory_or_product_metadata",
                )
            )
    finally:
        if executor is not None:
            executor.shutdown(wait=True)
        fetcher.close()
    stats["finished_at"] = utc_now()
    stats["elapsed_seconds"] = round(time.monotonic() - started, 3)
    stats["corpus_db"] = str(store.db_path)
    stats["seed_only"] = seed_only
    stats["ready_products"] = len(store.all(ready_only=True))
    stats["status_counts"] = store.counts()
    return stats


def load_requirements(path: Path = DEFAULT_REQUIREMENTS) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def query_paths(requirement: dict[str, object]) -> list[Path]:
    """Use only project reference crops; expected_kp/golden assets are rejected."""
    values = requirement.get("reference_crop_paths") or []
    paths: list[Path] = []
    for value in values:
        path = Path(str(value))
        folded = str(path).casefold().replace("/", "\\")
        if "expected_kp" in folded or "golden" in folded:
            continue
        if path.exists():
            paths.append(path)
    return paths
