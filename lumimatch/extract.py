"""Conservative product-card extraction.

The extractor deliberately prefers product-scoped structures over flattened
body text. A supplier page often contains recommendations, packaging data
and footer counters; none of those are product facts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from html import unescape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .availability import normalize_availability
from .models import CatalogProduct
from .taxonomy import classify_product

BAD_IMAGE_MARKERS = ("logo", "icon", "sprite", "cert", "certificate", "partner", "banner", "counter", "analytics", "related", "recommend", "similar", "viewed", "update-viewed")
PACKAGING_MARKERS = ("упаков", "package", "box", "packaging")
SUPPLIER_BRAND_HINTS = {
    "kinklight.ru": "Kink Light",
    "freya-light.com": "Freya",
    "odeon-light.com": "Lumion",
    "shop.lussole.ru": "Lussole",
    "ambrella.biz": "Ambrella",
}


def clean(value: object | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", " ", str(value))
    text = unescape(" ".join(text.split()))
    return text or None


def _jsonld_items(value: object) -> Iterable[dict[str, object]]:
    if isinstance(value, list):
        for item in value:
            yield from _jsonld_items(item)
    elif isinstance(value, dict):
        graph = value.get("@graph")
        if graph:
            yield from _jsonld_items(graph)
        else:
            yield value


def _jsonld_product(soup: BeautifulSoup) -> dict[str, object]:
    for script in soup.find_all("script", type="application/ld+json"):
        raw_json = script.get_text()
        try:
            # Some public cards embed literal CR/LF control characters inside
            # JSON-LD descriptions.  They are invalid JSON but do not change
            # the product fields we need, so normalize only those controls.
            safe_json = "".join(
                character if ord(character) >= 32 else " "
                for character in raw_json
            )
            payload = json.loads(safe_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and str(payload.get("@type", "")).casefold() == "product":
            return payload
        for item in _jsonld_items(payload):
            types = item.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if any(str(item_type).casefold() == "product" for item_type in types):
                return item
    return {}


def _meta(soup: BeautifulSoup, key: str, *, attr: str = "property") -> str | None:
    tag = soup.find("meta", attrs={attr: key}) or soup.find("meta", attrs={"name": key})
    return clean(tag.get("content")) if tag else None


def _number(value: object | None) -> float | None:
    text = clean(value)
    if not text:
        return None
    match = re.search(r"\d+(?:[\s.,]\d+)?", text.replace("\u00a0", " "))
    if not match:
        return None
    try:
        return float(match.group(0).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _jsonld_number(value: object | None) -> float | None:
    if isinstance(value, dict):
        return _number(value.get("value"))
    return _number(value)


def _meta_or_data(data: dict[str, object], key: str, soup: BeautifulSoup) -> str | None:
    value = data.get(key)
    if isinstance(value, dict):
        value = value.get("name") or value.get("value")
    return clean(value) or _meta(soup, key, attr="name")


def _is_bad_image(tag: Tag, url: str) -> bool:
    if any(marker in url.casefold() for marker in BAD_IMAGE_MARKERS):
        return True
    for parent in tag.parents:
        if not isinstance(parent, Tag):
            continue
        marker_text = f"{parent.get('id', '')} {' '.join(parent.get('class', []))}".casefold()
        if any(marker in marker_text for marker in BAD_IMAGE_MARKERS):
            return True
        if parent.name in {"body", "html"}:
            break
    return False


def _absolute(value: object, base_url: str) -> str | None:
    absolute = urljoin(base_url, str(value).strip()).split("#", 1)[0]
    if not absolute.startswith(("http://", "https://")) or absolute.casefold().endswith(".svg"):
        return None
    return absolute


def _absolute_images(soup: BeautifulSoup, base_url: str, data: dict[str, object]) -> tuple[list[str], str | None]:
    """Return only JSON-LD or product-gallery images, never page-wide images."""
    result: list[str] = []
    source: str | None = None

    def add(value: object, origin: str, tag: Tag | None = None) -> None:
        nonlocal source
        absolute = _absolute(value, base_url)
        if not absolute or (tag is not None and _is_bad_image(tag, absolute)):
            return
        if absolute not in result:
            result.append(absolute)
            source = source or origin

    image_value = data.get("image")
    values = image_value if isinstance(image_value, list) else [image_value]
    for value in values:
        if value:
            add(value, "jsonld")

    selectors = (".product-gallery img", ".product__gallery img", ".product-images img", ".product-images picture source", ".gallery img", "[data-gallery] img", "[class*='gallery'] img", "[class*='product-photo'] img", "[class*='product-image'] img")
    seen_tags: set[int] = set()
    for selector in selectors:
        for tag in soup.select(selector):
            if id(tag) in seen_tags:
                continue
            seen_tags.add(id(tag))
            for attribute in ("src", "data-src", "data-original", "data-lazy-src"):
                if tag.get(attribute):
                    add(tag[attribute], "product_gallery", tag)
            srcset = tag.get("srcset")
            if srcset:
                add(srcset.split(",")[-1].strip().split(" ", 1)[0], "product_gallery", tag)
    if not result:
        for key in ("og:image", "twitter:image"):
            value = _meta(soup, key)
            if value:
                add(value, "og")
                break
    return result[:12], source


def _spec_rows(soup: BeautifulSoup) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    selectors = ("table tr", ".characteristics li", ".characteristic", ".specifications li", ".specification", ".properties li", ".property", ".params li", ".param", "[class*='characteristic'] li", "[class*='property'] li")
    for row in soup.select(",".join(selectors)):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) >= 2:
            key = clean(cells[0].get_text(" ", strip=True))
            value = clean(cells[1].get_text(" ", strip=True))
        else:
            row_text = clean(row.get_text(" ", strip=True)) or ""
            parts = re.split(r"\s*[:|]\s*", row_text, maxsplit=1)
            key, value = (parts + [None, None])[:2]
        if not key or not value or len(key) > 90 or len(value) > 180:
            continue
        pair = (key, value)
        if pair not in seen and not any(marker in key.casefold() for marker in ("menu", "поделиться")):
            rows.append(pair)
            seen.add(pair)
    return rows


def _spec_value(rows: list[tuple[str, str]], labels: tuple[str, ...]) -> str | None:
    for key, value in rows:
        folded = key.casefold()
        if any(label.casefold() == folded or label.casefold() in folded for label in labels) and not any(marker in folded for marker in PACKAGING_MARKERS):
            return value
    return None


def _dimension_mm(value: object | None) -> float | None:
    text = clean(value)
    if not text:
        return None
    match = re.search(r"(\d+(?:[\s.,]\d+)?)\s*(мм|mm|см|cm|м|m)?\b", text, re.IGNORECASE)
    if not match:
        return None
    number = _number(match.group(1))
    if number is None:
        return None
    unit = (match.group(2) or "мм").casefold()
    return number * 10 if unit in {"см", "cm"} else number * 1000 if unit in {"м", "m"} else number


def _extract_dimensions(data: dict[str, object], rows: list[tuple[str, str]]) -> dict[str, float | None]:
    values: dict[str, float | None] = {"width_mm": _jsonld_number(data.get("width")), "height_mm": _jsonld_number(data.get("height")), "length_mm": _jsonld_number(data.get("length")), "diameter_mm": None, "depth_mm": _jsonld_number(data.get("depth"))}
    labels = {"width_mm": ("ширина", "width"), "height_mm": ("высота", "height"), "length_mm": ("длина", "length"), "diameter_mm": ("диаметр", "diameter"), "depth_mm": ("глубина", "depth")}
    for name, variants in labels.items():
        if values[name] is None:
            values[name] = _dimension_mm(_spec_value(rows, variants))
    return values


def _availability_source(soup: BeautifulSoup, data: dict[str, object], rows: list[tuple[str, str]]) -> str | None:
    offers = data.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if isinstance(offers, dict) and offers.get("availability"):
        return clean(offers.get("availability"))
    if data.get("availability"):
        return clean(data.get("availability"))
    value = _spec_value(rows, ("наличие", "статус", "availability", "stock", "остаток"))
    if value:
        return value
    scoped: list[str] = []
    for tag in soup.select("[class*='availability'], [class*='stock'], [class*='status']"):
        text = clean(tag.get_text(" ", strip=True))
        if text and len(text) < 180:
            scoped.append(text)
    return " | ".join(dict.fromkeys(scoped)) or None


def _availability_value(source: str | None) -> str | None:
    if not source:
        return None
    marker = source.rstrip("/").rsplit("/", 1)[-1]
    return marker if marker in {"InStock", "OutOfStock", "PreOrder", "LimitedAvailability", "InStoreOnly"} else source


def _price(data: dict[str, object], rows: list[tuple[str, str]], text: str) -> tuple[float | None, str | None]:
    offers = data.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    price = _number(offers.get("price")) or _number(data.get("price"))
    currency = clean(offers.get("priceCurrency")) or clean(data.get("priceCurrency"))
    if price is None:
        value = _spec_value(rows, ("цена", "стоимость", "price"))
        price = _number(value)
        if price is not None:
            currency = currency or ("EUR" if "€" in (value or "") else "USD" if "$" in (value or "") else "RUB")
    if price is None:
        match = re.search(r"(?<![\w])(\d[\d\s]{2,}(?:[,.]\d{1,2})?)\s*(?:₽|руб(?:\.|лей)?|RUB)", text, re.IGNORECASE)
        if match:
            price = _number(match.group(1))
            currency = currency or "RUB"
    return price, currency


def _attributes(rows: list[tuple[str, str]], data: dict[str, object]) -> dict[str, object]:
    attributes = {key: value for key, value in rows}
    brand = data.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    if brand:
        attributes.setdefault("brand", clean(brand))
    return attributes


def _brand(rows: list[tuple[str, str]], data: dict[str, object]) -> str | None:
    value = data.get("brand")
    if isinstance(value, dict):
        value = value.get("name")
    if value:
        return clean(value)
    for key, row_value in rows:
        if key.strip().casefold() in {"бренд", "brand", "производитель", "manufacturer"}:
            return row_value
    return None


def _brand_from_title(value: str | None) -> str | None:
    for brand in ("Kink Light", "Elektrostandard", "Eurosvet", "Freya", "Lumion", "Lussole", "Ambrella", "Feron", "SWG"):
        if brand.casefold() in (value or "").casefold():
            return brand
    return None


def parse_product_page(html: str, url: str, supplier: str) -> CatalogProduct | None:
    soup = BeautifulSoup(html, "lxml")
    data = _jsonld_product(soup)
    rows = _spec_rows(soup)
    scoped_text = " ".join(f"{key}: {value}" for key, value in rows)
    h1 = soup.find("h1")
    h1_text = clean(h1.get_text(" ", strip=True) if h1 else None)
    path = urlparse(url).path.lower()
    last_segment = path.rstrip("/").rsplit("/", 1)[-1]
    url_signal = any(token in path for token in ("/store/", "/product", "/tovar", "/item", ".html")) or bool(re.search(r"\d", last_segment))
    category_signal = bool(h1_text and re.search(r"(?:каталог|\b\d+\s+товар(?:а|ов)?\b|купить .* в официальном)", h1_text, re.IGNORECASE))
    filter_marker = any(marker in last_segment for marker in ("color_", "lamp_", "style_", "mesto_", "light_", "armature_", "brand_", "collection_"))
    if category_signal and (not url_signal or filter_marker):
        return None

    title = h1_text or clean(data.get("name")) or _meta(soup, "og:title")
    canonical_tag = soup.find("link", rel="canonical")
    canonical = urljoin(url, canonical_tag.get("href")) if canonical_tag and canonical_tag.get("href") else url
    canonical = canonical.split("#", 1)[0]
    sku = clean(data.get("sku")) or clean(data.get("mpn")) or clean(data.get("productID"))
    sku = sku or _spec_value(rows, ("артикул", "арт.", "код товара", "sku", "модель", "article"))
    if sku and (len(sku) > 40 or " " in sku):
        sku = None
    sku_match = re.search(r"\b(?:[A-ZА-Я]{1,8}[-/]?\d{3,}[A-ZА-Я0-9/-]*|\d{5,})\b", h1_text or "")
    sku = sku or (sku_match.group(0) if sku_match else None)
    if not sku and last_segment.isdigit():
        sku = last_segment

    availability_source_text = _availability_source(soup, data, rows)
    availability_status = normalize_availability(availability_source_text)
    price, currency = _price(data, rows, scoped_text)
    images, image_source = _absolute_images(soup, url, data)
    product_signal = bool(data) or (bool(title) and bool(images) and (bool(sku) or url_signal))
    if not title or not product_signal:
        return None
    title = title[:240]
    dimensions = _extract_dimensions(data, rows)
    dimension_parts = []
    for key, label in (("width_mm", "ширина"), ("height_mm", "высота"), ("length_mm", "длина"), ("diameter_mm", "диаметр"), ("depth_mm", "глубина")):
        if dimensions[key] is not None:
            dimension_parts.append(f"{label}: {dimensions[key]:g} мм")
    attributes = _attributes(rows, data)
    brand = _brand(rows, data) or _brand_from_title(title) or SUPPLIER_BRAND_HINTS.get(supplier.casefold())
    color = _meta_or_data(data, "color", soup) or _spec_value(rows, ("цвет", "color"))
    if not color:
        color_match = re.search(r"(?i)(ч[её]рн(?:ый|ая|ое|ые)|бел(?:ый|ая|ое|ые)|black|white|графит|антрацит|венге)", f"{title} {url}")
        color = color_match.group(1) if color_match else None
    material = _meta_or_data(data, "material", soup) or _spec_value(rows, ("материал", "material"))
    mounting = _spec_value(rows, ("тип крепления", "крепление", "монтаж", "mounting"))
    light_source = _spec_value(rows, ("тип лампы", "источник света", "цоколь", "light source"))
    wattage = _number(_spec_value(rows, ("мощность", "wattage", "power")))
    temperature = _number(_spec_value(rows, ("цветовая температура", "температура света", "color temperature")))
    ip_rating = _spec_value(rows, ("степень защиты", "ip"))
    category = clean(data.get("category")) or _spec_value(rows, ("категория", "category"))
    style = _spec_value(rows, ("стиль", "style"))
    collection = _spec_value(rows, ("коллекция", "collection", "серия", "series"))
    system = _spec_value(rows, ("система", "system", "шинопровод"))
    series = _spec_value(rows, ("серия", "series", "коллекция", "collection"))
    voltage = _spec_value(rows, ("напряжение", "voltage", "вольт"))
    product = CatalogProduct(
        supplier=supplier,
        brand=brand,
        source_url=url,
        canonical_url=canonical,
        sku=sku,
        name=title,
        category=category,
        collection=collection,
        description=clean(data.get("description")) or _meta(soup, "description", attr="name"),
        price=price,
        currency=currency,
        availability=_availability_value(availability_source_text),
        availability_status=availability_status,
        availability_source_text=availability_source_text,
        dimensions="; ".join(dimension_parts) or None,
        width=dimensions["width_mm"],
        height=dimensions["height_mm"],
        diameter=dimensions["diameter_mm"],
        depth=dimensions["depth_mm"],
        width_mm=dimensions["width_mm"],
        height_mm=dimensions["height_mm"],
        length_mm=dimensions["length_mm"],
        diameter_mm=dimensions["diameter_mm"],
        depth_mm=dimensions["depth_mm"],
        color=color,
        material=material,
        mounting_type=mounting,
        light_source=light_source,
        wattage=wattage,
        color_temperature=temperature,
        ip_rating=ip_rating,
        style=style,
        system=system,
        series=series,
        voltage=voltage,
        attributes=attributes,
        image_urls=images,
        primary_image_url=images[0] if images else None,
        image_source=image_source,
    )
    product.product_family = classify_product(product)
    return product
