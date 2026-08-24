"""Generic HTML and JSON-LD product extraction."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from html import unescape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import CatalogProduct


def clean(value: object | None) -> str | None:
    if value is None:
        return None
    text = unescape(" ".join(str(value).split()))
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
        try:
            payload = json.loads(script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        for item in _jsonld_items(payload):
            types = item.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if any(str(item_type).lower() == "product" for item_type in types):
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
    raw = match.group(0).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _label_value(text: str, labels: list[str]) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?:{label_pattern})\s*[:#№-]?\s*([^\n|;]{{1,120}})", text, re.IGNORECASE
    )
    return clean(match.group(1)) if match else None


def _absolute_images(
    soup: BeautifulSoup, base_url: str, data: dict[str, object]
) -> list[str]:
    values: list[str] = []
    image_value = data.get("image")
    if isinstance(image_value, str):
        values.append(image_value)
    elif isinstance(image_value, list):
        values.extend(str(item) for item in image_value)
    for tag in soup.find_all("meta"):
        if tag.get("property") in {"og:image", "twitter:image"} and tag.get("content"):
            values.append(str(tag["content"]))
    for tag in soup.find_all(["img", "source"]):
        for attribute in ("src", "data-src", "data-original", "data-lazy-src"):
            if tag.get(attribute):
                values.append(str(tag[attribute]))
        srcset = tag.get("srcset")
        if srcset:
            values.extend(part.strip().split(" ", 1)[0] for part in srcset.split(","))
    result: list[str] = []
    for value in values:
        absolute = urljoin(base_url, value.strip())
        if not absolute.startswith(
            ("http://", "https://")
        ) or absolute.lower().endswith(".svg"):
            continue
        if absolute not in result and not any(
            token in absolute.lower() for token in ["logo", "icon", "sprite"]
        ):
            result.append(absolute)
    return result[:30]


def _availability(value: object | None) -> str | None:
    text = clean(value)
    if not text:
        return None
    for marker in (
        "InStock",
        "InStoreOnly",
        "LimitedAvailability",
        "PreOrder",
        "OutOfStock",
    ):
        if marker.lower() in text.lower():
            return marker
    return text


def _price(data: dict[str, object], text: str) -> tuple[float | None, str | None]:
    offers = data.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    price = _number(offers.get("price")) or _number(data.get("price"))
    currency = clean(offers.get("priceCurrency")) or clean(data.get("priceCurrency"))
    if price is None:
        price_match = re.search(
            r"(?<![\w])(\d[\d\s]{2,}(?:[,.]\d{1,2})?)\s*(?:₽|руб(?:\.|лей)?|RUB)",
            text,
            re.IGNORECASE,
        )
        value = price_match.group(0) if price_match else None
        price = _number(price_match.group(1)) if price_match else None
        if price is None:
            value = _label_value(text, ["цена", "стоимость", "price"])
            price = _number(value)
        if price is not None and "€" in (value or ""):
            currency = "EUR"
        elif price is not None and "$" in (value or ""):
            currency = "USD"
        elif price is not None:
            currency = currency or "RUB"
    return price, currency


def _attributes(soup: BeautifulSoup, text: str) -> dict[str, object]:
    attributes: dict[str, object] = {}
    for row in soup.select("tr, li, .property, .characteristic, .param, .product-info"):
        row_text = clean(row.get_text(" ", strip=True))
        if not row_text or len(row_text) > 220:
            continue
        parts = re.split(r"\s*[:|]\s*", row_text, maxsplit=1)
        if len(parts) == 2 and len(parts[0]) <= 70:
            attributes.setdefault(parts[0], parts[1])
    return attributes


def parse_product_page(html: str, url: str, supplier: str) -> CatalogProduct | None:
    soup = BeautifulSoup(html, "lxml")
    data = _jsonld_product(soup)
    text = clean(soup.get_text(" ", strip=True)) or ""
    h1 = soup.find("h1")
    h1_text = clean(h1.get_text(" ", strip=True) if h1 else None)
    path = urlparse(url).path.lower()
    last_segment = path.rstrip("/").rsplit("/", 1)[-1]
    url_signal = any(
        token in path for token in ("/store/", "/product", "/tovar", "/item", ".html")
    ) or bool(re.search(r"\d", last_segment))
    category_signal = bool(
        h1_text
        and re.search(
            r"(?:каталог|\b\d+\s+товар(?:а|ов)?\b|купить .* в официальном)",
            h1_text,
            re.IGNORECASE,
        )
    )
    filter_marker = any(
        marker in last_segment
        for marker in (
            "color_",
            "lamp_",
            "style_",
            "mesto_",
            "light_",
            "armature_",
            "brand_",
            "collection_",
        )
    )
    if category_signal and (not url_signal or filter_marker):
        return None
    title = h1_text or clean(data.get("name")) or _meta(soup, "og:title")
    canonical_tag = soup.find("link", rel="canonical")
    canonical = (
        urljoin(url, canonical_tag.get("href"))
        if canonical_tag and canonical_tag.get("href")
        else url
    )
    sku = (
        clean(data.get("sku")) or clean(data.get("mpn")) or clean(data.get("productID"))
    )
    sku_candidate = sku or _label_value(
        text, ["артикул", "арт.", "код товара", "sku", "модель", "article"]
    )
    if sku_candidate and (len(sku_candidate) > 40 or " " in sku_candidate):
        sku_candidate = None
    sku_match = re.search(r"\b(?:[A-Z]{1,6}\d{3,}[A-Z0-9-]*|\d{5,})\b", h1_text or "")
    sku = sku_candidate or (sku_match.group(0) if sku_match else None)
    if not sku and last_segment.isdigit():
        sku = last_segment
    price, currency = _price(data, text)
    availability = _availability(
        (data.get("offers") or {}).get("availability")
        if isinstance(data.get("offers"), dict)
        else data.get("availability")
    )
    if not availability:
        if re.search(r"нет\s+в\s+наличии", text, re.IGNORECASE):
            availability = "Нет в наличии"
        else:
            stock_match = re.search(
                r"в\s+наличии(?:\s*[>:]?\s*\d+\s*шт\.?)?", text, re.IGNORECASE
            )
            availability = clean(stock_match.group(0)) if stock_match else None
    images = _absolute_images(soup, url, data)
    product_signal = bool(data) or (bool(sku) and (price is not None or bool(images)))
    if not title or not (
        bool(data) or (product_signal and bool(h1_text) and url_signal)
    ):
        return None
    if len(title) > 240:
        title = title[:240]

    dimensions = clean(data.get("size")) or _label_value(
        text, ["размеры", "габариты", "dimensions", "size"]
    )
    color = clean(data.get("color")) or _label_value(text, ["цвет", "color"])
    material = clean(data.get("material")) or _label_value(
        text, ["материал", "material"]
    )
    mounting = _label_value(text, ["тип крепления", "крепление", "монтаж", "mounting"])
    light_source = _label_value(
        text, ["тип лампы", "источник света", "цоколь", "light source"]
    )
    wattage = _number(_label_value(text, ["мощность", "wattage", "power"]))
    temperature = _number(
        _label_value(
            text, ["цветовая температура", "температура света", "color temperature"]
        )
    )
    ip_rating = _label_value(text, ["степень защиты", "ip"])
    category = clean(data.get("category"))
    brand = data.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    attributes = _attributes(soup, text)
    if brand:
        attributes.setdefault("brand", clean(brand))
    return CatalogProduct(
        supplier=supplier,
        source_url=url,
        canonical_url=canonical,
        sku=sku,
        name=title,
        category=category,
        collection=clean(attributes.get("коллекция"))
        or clean(attributes.get("collection")),
        description=clean(data.get("description"))
        or _meta(soup, "description", attr="name"),
        price=price,
        currency=currency,
        availability=availability,
        dimensions=dimensions,
        width=_number(_label_value(text, ["ширина", "width"])),
        height=_number(_label_value(text, ["высота", "height"])),
        diameter=_number(_label_value(text, ["диаметр", "diameter"])),
        depth=_number(_label_value(text, ["глубина", "depth"])),
        color=color,
        material=material,
        mounting_type=mounting,
        light_source=light_source,
        wattage=wattage,
        color_temperature=temperature,
        ip_rating=ip_rating,
        style=_label_value(text, ["стиль", "style"]),
        attributes=attributes,
        image_urls=images,
        primary_image_url=images[0] if images else None,
    )
