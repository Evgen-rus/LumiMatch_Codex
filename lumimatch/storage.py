"""SQLite storage and HTTP/image cache for the local catalogue."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .availability import effective_availability_status
from .models import CatalogProduct
from .paths import CATALOG, ensure_dirs
from .taxonomy import classify_product


def _key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CatalogStore:
    def __init__(self, db_path: Path | None = None) -> None:
        ensure_dirs()
        self.db_path = db_path or CATALOG / "catalog.sqlite3"
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
                    canonical_url TEXT PRIMARY KEY,
                    supplier TEXT NOT NULL,
                    sku TEXT,
                    name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_products_supplier ON products(supplier);
                CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
                CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
                    canonical_url UNINDEXED, supplier, sku, name, search_text
                );
                """
            )

    def upsert(self, product: CatalogProduct) -> None:
        product = self._normalize_product(product)
        with self._connect() as con:
            existing_row = con.execute(
                "SELECT payload_json FROM products WHERE canonical_url = ?",
                (product.canonical_url,),
            ).fetchone()
        if existing_row:
            existing = CatalogProduct.model_validate(json.loads(existing_row[0]))
            preserved: dict[str, object] = {}
            for field_name in (
                "sku",
                "brand",
                "primary_image_url",
                "local_image_path",
            ):
                if not getattr(product, field_name) and getattr(existing, field_name):
                    preserved[field_name] = getattr(existing, field_name)
            if preserved:
                product = product.model_copy(update=preserved)

        payload = product.model_dump(mode="json")
        search_text = " ".join(
            str(value)
            for value in (
                product.name,
                product.brand,
                product.category,
                product.collection,
                product.description,
                product.color,
                product.material,
                product.mounting_type,
                product.light_source,
                product.style,
                json.dumps(product.attributes, ensure_ascii=False),
            )
            if value
        )
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO products(canonical_url, supplier, sku, name, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_url) DO UPDATE SET
                    supplier=excluded.supplier,
                    sku=excluded.sku,
                    name=excluded.name,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    product.canonical_url,
                    product.supplier,
                    product.sku,
                    product.name,
                    json.dumps(payload, ensure_ascii=False),
                    product.updated_at,
                ),
            )
            con.execute(
                "DELETE FROM products_fts WHERE canonical_url = ?",
                (product.canonical_url,),
            )
            con.execute(
                "INSERT INTO products_fts(canonical_url, supplier, sku, name, search_text) VALUES (?, ?, ?, ?, ?)",
                (
                    product.canonical_url,
                    product.supplier,
                    product.sku or "",
                    product.name,
                    search_text,
                ),
            )

    def count(self) -> int:
        with self._connect() as con:
            return int(con.execute("SELECT COUNT(*) FROM products").fetchone()[0])

    def delete(self, canonical_url: str) -> None:
        with self._connect() as con:
            con.execute(
                "DELETE FROM products WHERE canonical_url = ?", (canonical_url,)
            )
            con.execute(
                "DELETE FROM products_fts WHERE canonical_url = ?", (canonical_url,)
            )

    def all(self, suppliers: set[str] | None = None) -> list[CatalogProduct]:
        with self._connect() as con:
            if suppliers:
                placeholders = ",".join("?" for _ in suppliers)
                rows = con.execute(
                    f"SELECT payload_json FROM products WHERE supplier IN ({placeholders})",
                    tuple(sorted(suppliers)),
                ).fetchall()
            else:
                rows = con.execute("SELECT payload_json FROM products").fetchall()
        return [self._normalize_product(CatalogProduct.model_validate(json.loads(row[0]))) for row in rows]

    def fts(self, query: str, limit: int = 100) -> list[CatalogProduct]:
        terms = " ".join(token for token in query.split() if token.isalnum())
        if not terms:
            return self.all()[:limit]
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT p.payload_json
                FROM products_fts f JOIN products p ON p.canonical_url=f.canonical_url
                WHERE products_fts MATCH ? ORDER BY rank LIMIT ?
                """,
                (terms, limit),
            ).fetchall()
        return [self._normalize_product(CatalogProduct.model_validate(json.loads(row[0]))) for row in rows]

    @staticmethod
    def _normalize_product(product: CatalogProduct) -> CatalogProduct:
        updates: dict[str, object] = {}
        effective_status = effective_availability_status(product)
        if effective_status != product.availability_status:
            updates["availability_status"] = effective_status
        if not product.availability_source_text and product.availability:
            updates["availability_source_text"] = product.availability
        inferred_family = classify_product(product)
        if (
            not product.product_family
            or product.product_family == "unknown"
            or product.product_family == "wall_sconce" and inferred_family != "wall_sconce"
        ):
            updates["product_family"] = inferred_family
        for short_name, normalized_name in (
            ("width", "width_mm"),
            ("height", "height_mm"),
            ("diameter", "diameter_mm"),
            ("depth", "depth_mm"),
        ):
            if getattr(product, normalized_name) is None and getattr(product, short_name) is not None:
                updates[normalized_name] = getattr(product, short_name)
        return product.model_copy(update=updates) if updates else product

    def response_cache_path(self, url: str) -> Path:
        path = CATALOG / "cache" / f"{_key(url)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def image_cache_path(self, url: str, suffix: str = ".img") -> Path:
        path = CATALOG / "images" / f"{_key(url)}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def get_cached_response(self, url: str) -> dict[str, Any] | None:
        path = self.response_cache_path(url)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put_cached_response(self, url: str, value: dict[str, Any]) -> None:
        self.response_cache_path(url).write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )
