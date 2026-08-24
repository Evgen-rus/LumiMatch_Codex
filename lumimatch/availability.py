"""Availability normalization shared by extraction, filtering and reports."""

from __future__ import annotations

import re

AVAILABILITY_STATUSES = (
    "in_stock",
    "out_of_stock",
    "discontinued",
    "preorder",
    "expected",
    "check_availability",
    "unknown",
)


def normalize_availability(value: object | None) -> str:
    """Map supplier/schema text to a conservative, finite status.

    Only ``in_stock`` is safe for the customer-facing result.  In particular,
    an empty field and a positive-looking price never imply availability.
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


def availability_label(status: str | None) -> str:
    return {
        "in_stock": "Подтверждено в наличии",
        "out_of_stock": "Нет в наличии",
        "discontinued": "Снят с производства",
        "preorder": "Под заказ",
        "expected": "Ожидается поступление",
        "check_availability": "Наличие нужно уточнить",
        "unknown": "Наличие не подтверждено",
    }.get(status or "unknown", "Наличие не подтверждено")
