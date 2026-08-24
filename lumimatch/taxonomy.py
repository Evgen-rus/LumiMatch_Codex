"""Small practical product taxonomy used as a hard compatibility gate."""

from __future__ import annotations

import re

PRODUCT_FAMILIES = (
    "pendant_single",
    "pendant_group",
    "chandelier",
    "wall_sconce",
    "decorative_wall",
    "recessed_downlight",
    "surface_downlight",
    "spot",
    "track_spot",
    "magnetic_track_spot",
    "track_linear_module",
    "linear_profile",
    "linear_fixture",
    "led_strip",
    "mirror_light",
    "track_rail",
    "track_connector",
    "track_power_component",
    "accessory",
    "unknown",
)


def _text(*values: object | None) -> str:
    return " ".join(str(value or "") for value in values).casefold()


def classify_text(text: str) -> str:
    value = text.casefold()
    if any(token in value for token in ("шинопровод", "трек-rail", " track rail", "шина трека", "шинная система")):
        return "track_rail"
    if any(token in value for token in ("коннектор", "соединитель", "угловой соединитель")):
        return "track_connector"
    if any(token in value for token in ("блок питания трека", "питание шинопровода", "адаптер питания трека")):
        return "track_power_component"
    if "магнит" in value and any(token in value for token in ("трек", "спот", "светильник")):
        return "magnetic_track_spot"
    if any(token in value for token in ("линейный модуль трека", "трековый линейный", "linear module")):
        return "track_linear_module"
    if any(token in value for token in ("светодиодная лента", "led strip", "лента светодиод")):
        return "led_strip"
    if "профиль" in value and any(token in value for token in ("свет", "led", "линей")):
        return "linear_profile"
    if any(token in value for token in ("подсветка зеркала", "зеркальный светильник", "mirror light")):
        return "mirror_light"
    if any(token in value for token in ("трековый спот", "трековый светильник", "track spot", "трековый")):
        return "track_spot"
    if any(token in value for token in ("точечный", "downlight", "встраиваемый спот", "накладной спот")):
        return "spot"
    if any(token in value for token in ("линейный светильник", "линейная лампа", "linear fixture")) or "линей" in value and "светильник" in value:
        return "linear_fixture"
    if re.search(r"(?<!\w)бра(?!\w)", value) or any(token in value for token in ("настенный светильник", "wall sconce", "sconce")):
        if any(token in value for token in ("контур", "овал", "кольцо", "декоратив", "светящаяся форма")):
            return "decorative_wall"
        return "wall_sconce"
    if any(token in value for token in ("многорожков", "многоярусн", "люстра", "chandelier")):
        return "chandelier"
    if any(token in value for token in ("группа подвесов", "групповой подвес", "cluster pendant", "подвесная группа")):
        return "pendant_group"
    if any(token in value for token in ("подвес", "подвесной", "pendant", "suspension")):
        return "pendant_single"
    if any(token in value for token in ("аксессуар", "комплектующ", "декор")):
        return "accessory"
    return "unknown"


def classify_product(product: object) -> str:
    attrs = getattr(product, "attributes", {}) or {}
    return classify_text(
        _text(
            getattr(product, "name", None),
            getattr(product, "category", None),
            getattr(product, "collection", None),
            getattr(product, "description", None),
            getattr(product, "mounting_type", None),
            getattr(product, "style", None),
            " ".join(f"{key} {value}" for key, value in attrs.items()),
        )
    )


def classify_requirement(requirement: object) -> str:
    attrs = getattr(requirement, "technical_constraints", []) or []
    return classify_text(
        _text(
            getattr(requirement, "fixture_type", None),
            getattr(requirement, "visual_description", None),
            getattr(requirement, "shape", None),
            getattr(requirement, "mounting", None),
            " ".join(attrs),
        )
    )


def family_relation(requirement_family: str, product_family: str) -> str:
    if requirement_family == product_family and requirement_family != "unknown":
        return "exact"
    if "unknown" in {requirement_family, product_family}:
        return "unknown"
    if {requirement_family, product_family} <= {"wall_sconce", "decorative_wall"}:
        return "compatible"
    if {requirement_family, product_family} <= {"track_spot", "magnetic_track_spot"}:
        return "compatible"
    if {requirement_family, product_family} <= {"linear_profile", "linear_fixture"}:
        return "compatible"
    if {requirement_family, product_family} <= {"pendant_single", "pendant_group"}:
        return "compatible"
    if requirement_family == "mirror_light" and product_family in {"wall_sconce", "decorative_wall"}:
        return "compatible"
    return "incompatible"


def is_hard_incompatible(requirement: object, product: object) -> bool:
    req_family = classify_requirement(requirement)
    product_family = getattr(product, "product_family", None) or classify_product(product)
    return family_relation(req_family, product_family) == "incompatible"
