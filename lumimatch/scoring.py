"""Deterministic, explainable shortlist scoring; visual review remains Codex-led."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .models import CatalogProduct, FixtureRequirement, ScoredCandidate

TOKEN_RE = re.compile(r"[\wа-яё]+", re.IGNORECASE)

SYNONYMS = {
    "подвес": {"подвес", "подвесной", "люстра", "suspension", "pendant"},
    "бра": {"бра", "настенный", "настенное", "wall", "sconce"},
    "спот": {"спот", "точечный", "трековый", "spot", "track"},
    "линейный": {
        "линейный",
        "профиль",
        "линия",
        "line",
        "linear",
        "linea",
        "profile",
    },
    "черный": {"черный", "чёрный", "black", "антрацит", "графит"},
    "белый": {"белый", "white"},
    "круглый": {"круглый", "цилиндр", "round", "cylinder"},
    "вертикальный": {"вертикальный", "oval", "овальный", "vertical"},
    "потолок": {"потолочный", "потолок", "встраиваемый", "накладной", "ceiling"},
}


def tokens(value: str | None) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(value or "")}


def expanded_tokens(value: str | None) -> set[str]:
    result = tokens(value)
    for key, values in SYNONYMS.items():
        if result.intersection(values):
            result.update(values)
            result.add(key)
    return result


def product_text(product: CatalogProduct) -> str:
    return " ".join(
        str(value)
        for value in (
            product.name,
            product.category,
            product.collection,
            product.description,
            product.color,
            product.material,
            product.mounting_type,
            product.light_source,
            product.style,
            " ".join(f"{key} {value}" for key, value in product.attributes.items()),
        )
        if value
    )


def _field_match(requirement: str | None, product: str | None) -> float:
    if not requirement:
        return 0.55
    required = expanded_tokens(requirement)
    available = expanded_tokens(product)
    if not required:
        return 0.55
    overlap = len(required & available) / len(required)
    return min(1.0, overlap * 1.2)


def _dimension_match(requirement: FixtureRequirement, product: CatalogProduct) -> float:
    if not requirement.exact_dimensions and not requirement.approximate_dimensions:
        return 0.55
    dimensions = (
        requirement.exact_dimensions or requirement.approximate_dimensions or {}
    )
    checks: list[float] = []
    for key in ("width", "height", "diameter", "depth"):
        expected = dimensions.get(key)
        actual = getattr(product, key, None)
        if expected is None:
            continue
        if actual is None:
            checks.append(0.35)
            continue
        try:
            delta = abs(float(actual) - float(expected)) / max(float(expected), 1)
        except (TypeError, ValueError):
            checks.append(0.35)
        else:
            checks.append(max(0.0, 1.0 - min(delta, 1.0)))
    return sum(checks) / len(checks) if checks else 0.45


def score_product(
    requirement: FixtureRequirement, product: CatalogProduct
) -> ScoredCandidate:
    type_match = _field_match(requirement.fixture_type, product_text(product))
    mounting_match = _field_match(
        requirement.mounting, product.mounting_type or product_text(product)
    )
    color_match = _field_match(
        requirement.color, product.color or product_text(product)
    )
    shape_match = _field_match(requirement.shape, product_text(product))
    lexical = _field_match(
        " ".join(
            [
                requirement.fixture_type,
                requirement.visual_description,
                *requirement.technical_constraints,
            ]
        ),
        product_text(product),
    )
    dimension_match = _dimension_match(requirement, product)
    technical_match = _field_match(
        " ".join(requirement.technical_constraints), product_text(product)
    )
    auto_visual = min(1.0, 0.35 * color_match + 0.35 * shape_match + 0.30 * lexical)
    overall = (
        0.25 * type_match
        + 0.15 * mounting_match
        + 0.15 * color_match
        + 0.10 * shape_match
        + 0.15 * dimension_match
        + 0.15 * technical_match
        + 0.05 * lexical
    )
    if overall >= 0.82 and technical_match >= 0.75:
        result_class = "вероятное точное совпадение"
    elif overall >= 0.60:
        result_class = "очень близкий аналог"
    else:
        result_class = "похожий вариант"
    differences: list[str] = []
    if not product.sku:
        differences.append("артикул не извлечён автоматически")
    if not product.price:
        differences.append("публичная цена не извлечена")
    if not product.availability:
        differences.append("наличие не извлечено")
    if not product.local_image_path:
        differences.append("локальная копия фото не сохранена")
    explanation = (
        f"Алгоритмический shortlist: тип {type_match:.2f}, монтаж {mounting_match:.2f}, "
        f"цвет {color_match:.2f}, форма {shape_match:.2f}, техника {technical_match:.2f}. "
        "Визуальное сходство требует проверки Codex по фото."
    )
    return ScoredCandidate(
        requirement_id=requirement.id,
        product=product,
        visual_similarity=auto_visual,
        type_match=type_match,
        dimension_match=dimension_match,
        technical_match=technical_match,
        overall_score=overall,
        result_class=result_class,
        fit_explanation=explanation,
        differences=differences,
    )


def shortlist(
    requirement: FixtureRequirement, products: Iterable[CatalogProduct], limit: int = 5
) -> list[ScoredCandidate]:
    candidates = [
        score_product(requirement, product) for product in products if product.sku
    ]
    candidates.sort(key=lambda candidate: candidate.overall_score, reverse=True)
    return candidates[:limit]


def apply_visual_review(
    candidate: ScoredCandidate, review: dict[str, object]
) -> ScoredCandidate:
    """Apply a Codex-authored visual check without changing source product facts."""
    updated = candidate.model_copy(deep=True)
    if isinstance(review.get("visual_similarity"), (int, float)):
        updated.visual_similarity = max(
            0.0, min(1.0, float(review["visual_similarity"]))
        )
        if not isinstance(review.get("overall_score"), (int, float)):
            updated.overall_score = round(
                0.55 * updated.overall_score + 0.45 * updated.visual_similarity, 3
            )
    for field in ("type_match", "dimension_match", "technical_match", "overall_score"):
        if isinstance(review.get(field), (int, float)):
            setattr(updated, field, max(0.0, min(1.0, float(review[field]))))
    if isinstance(review.get("result_class"), str):
        updated.result_class = review["result_class"]
    if isinstance(review.get("fit_explanation"), str):
        updated.fit_explanation = review["fit_explanation"]
    if isinstance(review.get("differences"), list):
        updated.differences = [str(item) for item in review["differences"]]
    updated.visual_review_status = "проверено Codex по фото кандидата"
    return updated
