"""Supplier-aware availability policy shared by extraction, filtering and reports."""

from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlparse

from .paths import DATA

AVAILABILITY_STATUSES = (
    "in_stock",
    "out_of_stock",
    "discontinued",
    "preorder",
    "expected",
    "check_availability",
    "unknown",
)
AVAILABILITY_MODES = (
    "stock_tracked",
    "stock_not_published",
    "mixed",
)
NEGATIVE_AVAILABILITY_STATUSES = frozenset(
    {
        "out_of_stock",
        "discontinued",
        "preorder",
        "expected",
        "check_availability",
    }
)

_NEGATIVE_MARKER_RE = re.compile(
    r"out\s*of\s*stock|нет\s+в\s+наличии|нет\s+на\s+складе|"
    r"остат(?:ок|ки)\s*[:=-]?\s*0\b|снят(?:о|а)?\s+с\s+производства|"
    r"не\s+производится|архив(?:ный)?|под\s+заказ|предзаказ|pre[- ]?order|"
    r"ожида(?:ется|ем)\s+(?:поступление|поставк)|expected|скоро\s+в\s+продаже|"
    r"уточня(?:йте|ть)\s+наличие|уточняется\s+наличие|check\s+availability",
    re.IGNORECASE,
)


def _supplier_key(value: str | None) -> str:
    raw = (value or "").strip().casefold()
    if "://" not in raw:
        raw = f"https://{raw}"
    return urlparse(raw).netloc.removeprefix("www.").rstrip(".")


@lru_cache(maxsize=1)
def _supplier_config() -> dict[str, object]:
    path = DATA / "supplier_availability.json"
    if not path.exists():
        return {"default_mode": "stock_tracked", "suppliers": {}}
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {"default_mode": "stock_tracked", "suppliers": {}}
    return payload if isinstance(payload, dict) else {"default_mode": "stock_tracked", "suppliers": {}}


def supplier_availability_capability(supplier: str | None) -> dict[str, object]:
    """Return the manually verified capability for a supplier host.

    A missing or malformed entry is intentionally conservative and behaves as
    ``stock_tracked``.  Parser failure must never turn into permission to show
    an unknown product as available.
    """
    payload = _supplier_config()
    entries = payload.get("suppliers")
    if not isinstance(entries, dict):
        entries = {}
    host = _supplier_key(supplier)
    selected: dict[str, object] | None = None
    for configured_host, value in entries.items():
        if not isinstance(value, dict):
            continue
        key = _supplier_key(str(configured_host))
        if host == key or host.endswith(f".{key}"):
            selected = value
            break
    if selected is None:
        selected = {"availability_mode": payload.get("default_mode", "stock_tracked")}
    mode = selected.get("availability_mode")
    if mode not in AVAILABILITY_MODES:
        mode = "stock_tracked"
    return {**selected, "supplier": host, "availability_mode": mode}


def supplier_availability_mode(supplier: str | None) -> str:
    return str(supplier_availability_capability(supplier)["availability_mode"])


def normalize_availability(value: object | None) -> str:
    """Map supplier/schema text to a conservative, finite status.

    Normalization itself never infers availability from an empty field or a
    positive-looking price.  Supplier capability decides whether ``unknown``
    may enter retrieval; tracked suppliers still require ``in_stock``.
    """
    text = " ".join(str(value or "").split()).strip()
    folded = text.casefold()
    if not folded:
        return "unknown"

    if any(
        marker in folded
        for marker in (
            "outofstock",
            "out of stock",
            "нет в наличии",
            "нет на складе",
            "отсутствует",
            "остаток 0",
            "остаток: 0",
            "остаток - 0",
            "0 шт",
        )
    ):
        return "out_of_stock"
    if any(
        marker in folded
        for marker in (
            "discontinued",
            "снят с производства",
            "снято с производства",
            "не производится",
            "архив",
            "архивный",
        )
    ):
        return "discontinued"
    if any(
        marker in folded
        for marker in (
            "preorder",
            "pre-order",
            "под заказ",
            "по предзаказу",
        )
    ):
        return "preorder"
    if any(
        marker in folded
        for marker in (
            "ожидается",
            "ожидаем поступление",
            "ожидается поступление",
            "expected",
            "скоро в продаже",
        )
    ):
        return "expected"
    if any(
        marker in folded
        for marker in (
            "уточняйте наличие",
            "уточнить наличие",
            "уточняется",
            "по запросу",
            "checkavailability",
            "check availability",
        )
    ):
        return "check_availability"
    if any(
        marker in folded
        for marker in (
            "instock",
            "in stock",
            "in-store-only",
            "in store only",
            "в наличии",
            "на складе",
        )
    ) and not re.search(r"остат(?:ок|ки)\s*[:=-]?\s*0\b", folded):
        return "in_stock"
    if re.search(r"остат(?:ок|ки)\s*[:=-]?\s*[1-9]\d*\b", folded):
        return "in_stock"
    return "unknown"


def effective_availability_status(product: object) -> str:
    """Resolve a product status while allowing raw negative evidence to win.

    A stale positive status must not override an explicit negative source text.
    An explicit ``unknown`` remains unknown: this is important for
    ``stock_tracked`` suppliers, where a parser-side positive legacy field is
    not enough evidence.
    """
    source_values = (
        getattr(product, "availability_source_text", None),
        getattr(product, "availability", None),
    )
    source_statuses = [normalize_availability(value) for value in source_values if value]
    negative_source = next(
        (status for status in source_statuses if status in NEGATIVE_AVAILABILITY_STATUSES),
        None,
    )
    if negative_source:
        return negative_source
    stored_value = getattr(product, "availability_status", None)
    stored = stored_value if stored_value in AVAILABILITY_STATUSES else normalize_availability(stored_value)
    if stored != "unknown":
        return stored
    return "unknown"


def explicit_negative_availability(product: object) -> str | None:
    """Return an explicit negative status found on a normalized product."""
    status = effective_availability_status(product)
    if status in NEGATIVE_AVAILABILITY_STATUSES:
        return status
    attributes = getattr(product, "attributes", {})
    if isinstance(attributes, dict):
        for key, value in attributes.items():
            key_text = str(key).casefold()
            if not any(marker in key_text for marker in ("налич", "остат", "stock", "status", "производ")):
                continue
            candidate = normalize_availability(value)
            if candidate in NEGATIVE_AVAILABILITY_STATUSES:
                return candidate
    return None


def negative_availability_from_html(html: str, sku: str | None = None) -> str | None:
    """Find a negative marker close to the current product SKU in a page.

    The SKU proximity check avoids rejecting a live product because a related
    product or footer contains a generic ``Нет в наличии`` label.
    """
    try:
        from bs4 import BeautifulSoup

        text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    except (ImportError, TypeError, ValueError):
        text = re.sub(r"<[^>]+>", " ", html)
    sku_text = re.sub(r"\W+", "", (sku or "").casefold())
    for match in _NEGATIVE_MARKER_RE.finditer(text):
        if sku_text:
            window = text[max(0, match.start() - 900): match.end() + 900]
            if sku_text not in re.sub(r"\W+", "", window.casefold()):
                continue
        status = normalize_availability(match.group(0))
        if status in NEGATIVE_AVAILABILITY_STATUSES:
            return status
    return None


def availability_allowed(product: object, mode: str | None = None) -> bool:
    """Apply the supplier-level availability gate to a product."""
    selected_mode = mode if mode in AVAILABILITY_MODES else supplier_availability_mode(getattr(product, "supplier", None))
    status = effective_availability_status(product)
    if status in NEGATIVE_AVAILABILITY_STATUSES or explicit_negative_availability(product):
        return False
    if selected_mode == "stock_tracked":
        return status == "in_stock"
    return status in {"in_stock", "unknown"}


def availability_label(status: str | None, mode: str | None = None) -> str:
    negative_labels = {
        "out_of_stock": "Нет в наличии",
        "discontinued": "Снят с производства",
        "preorder": "Под заказ",
        "expected": "Ожидается поступление",
        "check_availability": "Наличие нужно уточнить",
    }
    if status in negative_labels:
        return negative_labels[status]
    if mode == "stock_not_published":
        return "Поставщик не публикует остатки"
    if mode == "mixed" and status != "in_stock":
        return "Поставщик не публикует остатки"
    return {
        "in_stock": "Подтверждено в наличии",
        "out_of_stock": "Нет в наличии",
        "discontinued": "Снят с производства",
        "preorder": "Под заказ",
        "expected": "Ожидается поступление",
        "check_availability": "Наличие нужно уточнить",
        "unknown": "Наличие не подтверждено",
    }.get(status or "unknown", "Наличие не подтверждено")
