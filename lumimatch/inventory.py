"""Production product URL inventory and requirement-driven hydration planning.

The inventory stage deliberately knows nothing about a project golden set.  It
stores lightweight URL evidence only; full product pages are fetched later by
the hydration stage for URLs selected from the current FixtureRequirements.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from .discovery import discover_inventory
from .fetch import PublicFetcher
from .models import FixtureRequirement
from .paths import CATALOG, ensure_dirs
from .taxonomy import classify_requirement


def _supplier_name(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def canonical_inventory_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path, fragment="").geturl()


def _sku_from_url(url: str) -> str | None:
    path = unquote(urlparse(url).path)
    slug = path.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"\.(?:html?|php)$", "", slug, flags=re.IGNORECASE)
    candidates = re.findall(r"[A-Za-zА-Яа-я]{1,10}[-_]?\d{2,}[A-Za-zА-Яа-я0-9_-]*|\d{4,}", slug)
    if not candidates:
        return None
    return candidates[-1]


def _category_from_url(url: str) -> str | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) < 2:
        return None
    return parts[-2]


@dataclass(frozen=True)
class InventoryRecord:
    supplier: str
    product_url: str
    canonical_url: str
    category: str | None = None
    category_url: str | None = None
    title: str | None = None
    sku: str | None = None
    brand: str | None = None
    image_url: str | None = None
    discovery_source: str = "unknown"
    discovered_at: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "supplier": self.supplier,
            "product_url": self.product_url,
            "canonical_url": self.canonical_url,
            "category": self.category,
            "category_url": self.category_url,
            "title": self.title,
            "sku": self.sku,
            "brand": self.brand,
            "image_url": self.image_url,
            "discovery_source": self.discovery_source,
            "discovered_at": self.discovered_at,
        }


class ProductInventoryStore:
    """Small persistent URL inventory independent from the hydrated catalog."""

    def __init__(self, db_path: Path | None = None) -> None:
        ensure_dirs()
        self.db_path = db_path or CATALOG / "product_inventory.sqlite3"
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
                CREATE TABLE IF NOT EXISTS product_inventory (
                    supplier TEXT NOT NULL,
                    product_url TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    category TEXT,
                    category_url TEXT,
                    title TEXT,
                    sku TEXT,
                    brand TEXT,
                    image_url TEXT,
                    discovery_source TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    PRIMARY KEY (supplier, canonical_url)
                );
                CREATE INDEX IF NOT EXISTS idx_inventory_supplier
                    ON product_inventory(supplier);
                CREATE INDEX IF NOT EXISTS idx_inventory_sku
                    ON product_inventory(sku);
                """
            )

    def upsert_many(self, records: list[InventoryRecord]) -> None:
        if not records:
            return
        with self._connect() as con:
            con.executemany(
                """
                INSERT INTO product_inventory(
                    supplier, product_url, canonical_url, category, category_url,
                    title, sku, brand, image_url, discovery_source, discovered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(supplier, canonical_url) DO UPDATE SET
                    product_url=excluded.product_url,
                    category=COALESCE(excluded.category, product_inventory.category),
                    category_url=COALESCE(excluded.category_url, product_inventory.category_url),
                    title=COALESCE(excluded.title, product_inventory.title),
                    sku=COALESCE(excluded.sku, product_inventory.sku),
                    brand=COALESCE(excluded.brand, product_inventory.brand),
                    image_url=COALESCE(excluded.image_url, product_inventory.image_url),
                    discovery_source=excluded.discovery_source,
                    discovered_at=excluded.discovered_at
                """,
                [
                    (
                        record.supplier,
                        record.product_url,
                        record.canonical_url,
                        record.category,
                        record.category_url,
                        record.title,
                        record.sku,
                        record.brand,
                        record.image_url,
                        record.discovery_source,
                        record.discovered_at,
                    )
                    for record in records
                ],
            )

    def all(self, suppliers: set[str] | None = None) -> list[InventoryRecord]:
        with self._connect() as con:
            if suppliers:
                placeholders = ",".join("?" for _ in suppliers)
                rows = con.execute(
                    f"SELECT * FROM product_inventory WHERE supplier IN ({placeholders}) ORDER BY supplier, canonical_url",
                    tuple(sorted(suppliers)),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM product_inventory ORDER BY supplier, canonical_url"
                ).fetchall()
        return [InventoryRecord(**dict(row)) for row in rows]

    def supplier_counts(self) -> dict[str, int]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT supplier, COUNT(*) AS count FROM product_inventory GROUP BY supplier ORDER BY supplier"
            ).fetchall()
        return {str(row["supplier"]): int(row["count"]) for row in rows}

    def count(self) -> int:
        with self._connect() as con:
            return int(con.execute("SELECT COUNT(*) FROM product_inventory").fetchone()[0])


def records_from_discovery(supplier_url: str, inventory: object) -> list[InventoryRecord]:
    supplier = _supplier_name(supplier_url)
    now = datetime.now(timezone.utc).isoformat()
    source = str(getattr(inventory, "discovery_method", "supplier_inventory"))
    urls = list(getattr(inventory, "urls", []))
    return [
        InventoryRecord(
            supplier=supplier,
            product_url=url,
            canonical_url=canonical_inventory_url(url),
            category=_category_from_url(url),
            category_url=url.rsplit("/", 2)[0] if "/" in urlparse(url).path else None,
            sku=_sku_from_url(url),
            discovery_source=source,
            discovered_at=now,
        )
        for url in urls
    ]


def build_product_inventory(
    suppliers: list[str],
    inventory_store: ProductInventoryStore,
    cache_store: object,
    *,
    max_urls: int = 10000,
    fresh: bool = False,
) -> dict[str, object]:
    """Build/reuse URL inventory without fetching product detail pages."""
    existing_by_supplier = {
        supplier: records
        for supplier in {_supplier_name(url) for url in suppliers}
        if (records := inventory_store.all({supplier}))
    }
    missing = [
        url for url in suppliers
        if fresh or _supplier_name(url) not in existing_by_supplier
    ]
    results: list[dict[str, object]] = []
    fetcher = PublicFetcher(cache_store, timeout=20.0, delay=0.08) if missing else None
    try:
        for base_url in suppliers:
            supplier = _supplier_name(base_url)
            if not fresh and supplier in existing_by_supplier:
                records = existing_by_supplier[supplier]
                results.append(
                    {
                        "supplier": supplier,
                        "inventory_urls": len(records),
                        "discovery_method": "cached_inventory",
                        "cached": True,
                    }
                )
                continue
            assert fetcher is not None
            discovered = discover_inventory(fetcher, base_url.rstrip("/"), max_urls=max_urls)
            records = records_from_discovery(base_url, discovered)
            inventory_store.upsert_many(records)
            results.append(
                {
                    "supplier": supplier,
                    "inventory_urls": len(records),
                    "approximate_catalog_urls": discovered.approximate_catalog_urls,
                    "sitemap_urls_total": discovered.sitemap_urls_total,
                    "sitemap_documents": discovered.sitemap_documents,
                    "category_pages_visited": discovered.category_pages_visited,
                    "discovery_method": discovered.discovery_method,
                    "adapter": discovered.adapter_name,
                    "coverage_basis": discovered.coverage_basis,
                    "cached": False,
                    "notes": discovered.notes,
                }
            )
    finally:
        if fetcher is not None:
            fetcher.close()
    all_records = inventory_store.all()
    return {
        "db": str(inventory_store.db_path),
        "fresh": fresh,
        "inventory_total": len(all_records),
        "supplier_counts": inventory_store.supplier_counts(),
        "suppliers": results,
    }


FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "pendant_single": ("подвес", "podves", "pendant", "suspension"),
    "pendant_group": ("подвес", "podves", "pendant", "cluster"),
    "wall_sconce": ("бра", "bra", "настенн", "nastenn", "wall", "sconce"),
    "decorative_wall": ("бра", "bra", "настенн", "nastenn", "wall", "sconce", "декоратив", "oval", "овал"),
    "mirror_light": ("зерк", "zerk", "mirror", "бра", "bra", "настенн", "nastenn", "подсвет", "podsvet"),
    "track_spot": ("трек", "trek", "track", "спот", "spot"),
    "track_rail": ("шинопровод", "шин", "трек", "trek", "track", "rail"),
    "track_connector": ("соедин", "connector", "коннектор"),
    "track_power_component": ("питан", "адаптер", "power"),
    "linear_profile": ("профил", "profil", "profile", "линей", "line", "linear", "led"),
    "linear_fixture": ("линей", "line", "linear", "профил", "profil", "profile"),
    "led_strip": ("лента", "lenta", "strip", "profile", "профил", "profil", "led", "подсвет", "podsvet"),
}


def _requirement_search_text(requirement: FixtureRequirement) -> str:
    return " ".join(
        str(value or "")
        for value in (
            requirement.fixture_type,
            requirement.visual_description,
            requirement.shape,
            requirement.mounting,
            requirement.color,
            " ".join(requirement.technical_constraints),
        )
    ).casefold()


def _record_text(record: InventoryRecord) -> str:
    return " ".join(
        str(value or "")
        for value in (
            record.product_url,
            record.category,
            record.category_url,
            record.title,
            record.sku,
            record.brand,
        )
    ).casefold()


def _relevance_score(requirement: FixtureRequirement, record: InventoryRecord) -> tuple[int, str]:
    family = requirement.taxonomy_family or classify_requirement(requirement)
    text = _record_text(record)
    terms = FAMILY_KEYWORDS.get(family, ())
    score = sum(10 for term in terms if term in text)
    requirement_text = _requirement_search_text(requirement)
    for token in re.findall(r"[\wа-яё]+", requirement_text, flags=re.IGNORECASE):
        if len(token) >= 4 and token in text:
            score += 2
    if requirement.mounting and any(
        token in text for token in re.findall(r"[\wа-яё]+", requirement.mounting.casefold()) if len(token) >= 4
    ):
        score += 3
    if requirement.color and any(
        token in text for token in re.findall(r"[\wа-яё]+", requirement.color.casefold()) if len(token) >= 4
    ):
        score += 2
    if not score:
        score = 1
    return score, family


@dataclass
class HydrationPlan:
    by_requirement: dict[str, list[InventoryRecord]] = field(default_factory=dict)
    records: list[InventoryRecord] = field(default_factory=list)
    by_supplier: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "requirements": {
                requirement_id: {
                    "selected_urls": len(records),
                    "suppliers": {
                        supplier: sum(item.supplier == supplier for item in records)
                        for supplier in sorted({item.supplier for item in records})
                    },
                    "urls": [
                        {
                            **item.as_dict(),
                            "selection_reason": "requirement_family_and_public_inventory_metadata",
                        }
                        for item in records
                    ],
                }
                for requirement_id, records in self.by_requirement.items()
            },
            "selected_unique_urls": len(self.records),
            "selected_by_supplier": dict(sorted(self.by_supplier.items())),
        }


def select_hydration_urls(
    requirements: list[FixtureRequirement],
    records: list[InventoryRecord],
    *,
    per_requirement_limit: int = 180,
    per_supplier_limit: int = 30,
) -> HydrationPlan:
    """Select a broad, requirement-derived URL slice instead of first-N URLs."""
    by_requirement: dict[str, list[InventoryRecord]] = {}
    selected_by_url: dict[str, InventoryRecord] = {}
    for requirement in requirements:
        ranked = sorted(
            records,
            key=lambda record: (
                -_relevance_score(requirement, record)[0],
                record.supplier,
                record.canonical_url,
            ),
        )
        selected: list[InventoryRecord] = []
        per_supplier: dict[str, int] = {}
        for record in ranked:
            if per_supplier.get(record.supplier, 0) >= per_supplier_limit:
                continue
            selected.append(record)
            selected_by_url[record.canonical_url] = record
            per_supplier[record.supplier] = per_supplier.get(record.supplier, 0) + 1
            if len(selected) >= per_requirement_limit:
                break
        by_requirement[requirement.id] = selected
    unique = sorted(selected_by_url.values(), key=lambda record: (record.supplier, record.canonical_url))
    return HydrationPlan(
        by_requirement=by_requirement,
        records=unique,
        by_supplier={
            supplier: sum(record.supplier == supplier for record in unique)
            for supplier in sorted({record.supplier for record in unique})
        },
    )
