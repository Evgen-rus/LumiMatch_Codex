"""Hard-gated coarse retrieval and Codex-led visual finalization."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .availability import normalize_availability
from .models import CatalogProduct, FixtureRequirement, ScoredCandidate
from .taxonomy import classify_product, classify_requirement, family_relation

TOKEN_RE = re.compile(r"[\wа-яё]+", re.IGNORECASE)
COLOR_GROUPS = {
    "черный": {"черный", "чёрный", "black", "антрацит", "графит", "венге"},
    "белый": {"белый", "white", "молочный"},
    "золотой": {"золотой", "золото", "gold", "латунь", "brass"},
    "серый": {"серый", "grey", "gray"},
    "коричневый": {"коричневый", "венге", "brown"},
    "хром": {"хром", "chrome", "серебро", "серебристый"},
}


@dataclass
class PoolDiagnostics:
    total_catalog: int = 0
    excluded_availability: int = 0
    excluded_family: int = 0
    excluded_missing_photo: int = 0
    excluded_mounting: int = 0
    excluded_dimensions: int = 0
    primary_color_pool: int = 0
    color_alternative_pool: int = 0
    visual_pool: int = 0
    rejected_by_visual: int = 0
    finalists: int = 0
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def tokens(value: str | None) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(value or "")}


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
            product.product_family,
            product.system,
            product.series,
            product.voltage,
            " ".join(f"{key} {value}" for key, value in product.attributes.items()),
        )
        if value
    )


def _field_match(requirement: str | None, product: str | None) -> float:
    required = tokens(requirement)
    available = tokens(product)
    if not required:
        return 0.55
    if not available:
        return 0.25
    return min(1.0, len(required & available) / len(required) * 1.15)


def _color_keys(value: str | None) -> set[str]:
    value_tokens = tokens(value)
    result: set[str] = set()
    for key, synonyms in COLOR_GROUPS.items():
        if value_tokens & synonyms:
            result.add(key)
    return result


def color_relation(requirement: str | None, product: str | None) -> tuple[str, float]:
    required = _color_keys(requirement)
    available = _color_keys(product)
    if not required:
        return "not_required", 0.55
    if not available:
        return "unknown", 0.40
    if required & available:
        return "match", 1.0
    return "mismatch", 0.0


def _dimension_match(requirement: FixtureRequirement, product: CatalogProduct) -> float:
    dimensions = requirement.exact_dimensions or requirement.approximate_dimensions or {}
    if not dimensions:
        return 0.55
    checks: list[float] = []
    key_map = {
        "width": "width_mm",
        "height": "height_mm",
        "length": "length_mm",
        "diameter": "diameter_mm",
        "depth": "depth_mm",
        "width_mm": "width_mm",
        "height_mm": "height_mm",
        "length_mm": "length_mm",
        "diameter_mm": "diameter_mm",
        "depth_mm": "depth_mm",
    }
    for key, expected in dimensions.items():
        actual = getattr(product, key_map.get(key, key), None)
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


def hard_filter(requirement: FixtureRequirement, product: CatalogProduct) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    status = product.availability_status or normalize_availability(product.availability)
    if status != "in_stock":
        reasons.append(f"availability:{status}")
    if not product.sku:
        reasons.append("missing_sku")
    if not product.primary_image_url and not product.local_image_path:
        reasons.append("missing_product_photo")
    req_family = requirement.taxonomy_family or classify_requirement(requirement)
    product_family = product.product_family or classify_product(product)
    relation = family_relation(req_family, product_family)
    if relation == "incompatible":
        reasons.append(f"incompatible_family:{req_family}!={product_family}")
    required_mounting = (requirement.mounting or "").casefold()
    actual_mounting = (product.mounting_type or "").casefold()
    if "настенн" in required_mounting and actual_mounting and not any(token in actual_mounting for token in ("настенн", "wall")):
        reasons.append("mounting_mismatch")
    if "подвес" in required_mounting and product_family in {"wall_sconce", "decorative_wall", "track_spot", "spot"}:
        reasons.append("mounting_mismatch")
    if any(token in " ".join(requirement.technical_constraints).casefold() for token in ("влажн", "сануз", "ip")) and not product.ip_rating:
        reasons.append("missing_ip_for_wet_zone")
    dimensions = requirement.exact_dimensions or requirement.approximate_dimensions or {}
    for key, expected in dimensions.items():
        actual = getattr(product, {"width": "width_mm", "height": "height_mm", "length": "length_mm", "diameter": "diameter_mm", "depth": "depth_mm"}.get(key, key), None)
        if expected and actual and abs(float(actual) - float(expected)) / max(float(expected), 1) > 0.45:
            reasons.append(f"dimension_mismatch:{key}")
    return not reasons, reasons


def score_product(requirement: FixtureRequirement, product: CatalogProduct, *, color_mode: str = "primary") -> ScoredCandidate:
    req_family = requirement.taxonomy_family or classify_requirement(requirement)
    product_family = product.product_family or classify_product(product)
    relation = family_relation(req_family, product_family)
    family_score = {"exact": 1.0, "compatible": 0.74, "unknown": 0.30, "incompatible": 0.0}[relation]
    color_status, color_match = color_relation(requirement.color, product.color or product_text(product))
    mounting_match = _field_match(requirement.mounting, product.mounting_type or product_text(product))
    shape_match = _field_match(requirement.shape, product_text(product))
    dimension_match = _dimension_match(requirement, product)
    technical_match = _field_match(" ".join(requirement.technical_constraints), product_text(product))
    overall = max(0.0, min(1.0, 0.42 * family_score + 0.16 * mounting_match + 0.15 * color_match + 0.12 * shape_match + 0.08 * dimension_match + 0.07 * technical_match))
    differences: list[str] = []
    if color_status == "mismatch":
        differences.append(f"цвет товара {product.color or 'неизвестен'} отличается от {requirement.color or 'требуемого'}")
    if not product.price:
        differences.append("публичная цена не извлечена")
    if not product.availability_source_text:
        differences.append("исходный текст наличия не извлечён")
    if not product.local_image_path:
        differences.append("локальная копия фото не сохранена")
    return ScoredCandidate(
        requirement_id=requirement.id,
        product=product,
        visual_similarity=None,
        color_match=color_match,
        family_relation=relation,
        type_match=family_score,
        dimension_match=dimension_match,
        technical_match=technical_match,
        overall_score=overall,
        result_class="кандидат для визуального просмотра",
        fit_explanation=f"Coarse retrieval: family {relation}, цвет {color_match:.2f}, форма {shape_match:.2f}, размеры {dimension_match:.2f}.",
        differences=differences,
        color_mode=color_mode,
    )


def wide_candidate_pool(requirement: FixtureRequirement, products: Iterable[CatalogProduct], limit: int = 80, *, include_color_alternatives: bool = False) -> list[ScoredCandidate]:
    candidates: list[ScoredCandidate] = []
    for product in products:
        allowed, _ = hard_filter(requirement, product)
        if not allowed:
            continue
        color_status, _ = color_relation(requirement.color, product.color or product_text(product))
        if color_status == "mismatch" and not include_color_alternatives:
            continue
        mode = "color_alternative" if color_status == "mismatch" else "primary"
        candidates.append(score_product(requirement, product, color_mode=mode))
    candidates.sort(key=lambda item: (item.color_mode != "primary", -item.overall_score, item.product.supplier, item.product.sku or ""))
    return candidates[:limit]


def candidate_pool_diagnostics(requirement: FixtureRequirement, products: list[CatalogProduct], limit: int = 80) -> PoolDiagnostics:
    diagnostics = PoolDiagnostics(total_catalog=len(products))
    primary: list[CatalogProduct] = []
    alternatives: list[CatalogProduct] = []
    for product in products:
        allowed, reasons = hard_filter(requirement, product)
        if not allowed:
            if any(reason.startswith("availability:") for reason in reasons):
                diagnostics.excluded_availability += 1
            if any(reason.startswith("incompatible_family") for reason in reasons):
                diagnostics.excluded_family += 1
            if "missing_product_photo" in reasons:
                diagnostics.excluded_missing_photo += 1
            if "mounting_mismatch" in reasons:
                diagnostics.excluded_mounting += 1
            if any(reason.startswith("dimension_mismatch") for reason in reasons):
                diagnostics.excluded_dimensions += 1
            continue
        color_status, _ = color_relation(requirement.color, product.color or product_text(product))
        (alternatives if color_status == "mismatch" else primary).append(product)
    diagnostics.primary_color_pool = min(len(primary), limit)
    diagnostics.color_alternative_pool = min(len(alternatives), limit)
    diagnostics.visual_pool = diagnostics.primary_color_pool
    return diagnostics


def shortlist(requirement: FixtureRequirement, products: Iterable[CatalogProduct], limit: int = 80) -> list[ScoredCandidate]:
    # Kept as a backwards-compatible coarse scorer for library callers. The
    # customer-facing CLI uses wide_candidate_pool(), which applies all hard
    # gates before returning a visual pool.
    candidates = [score_product(requirement, product) for product in products if product.sku]
    candidates.sort(key=lambda item: item.overall_score, reverse=True)
    return candidates[:limit]


def apply_visual_review(candidate: ScoredCandidate, review: dict[str, object]) -> ScoredCandidate:
    """Apply an explicit Codex review; a rejected item cannot reach reports."""
    updated = candidate.model_copy(deep=True)
    if isinstance(review.get("visual_similarity"), (int, float)):
        updated.visual_similarity = max(0.0, min(1.0, float(review["visual_similarity"])))
    for field_name in ("type_match", "dimension_match", "technical_match", "overall_score", "color_match"):
        if isinstance(review.get(field_name), (int, float)):
            setattr(updated, field_name, max(0.0, min(1.0, float(review[field_name]))))
    if isinstance(review.get("result_class"), str):
        updated.result_class = review["result_class"]
    if isinstance(review.get("fit_explanation"), str):
        updated.fit_explanation = review["fit_explanation"]
    if isinstance(review.get("differences"), list):
        updated.differences = [str(item) for item in review["differences"]]
    decision = str(review.get("decision") or review.get("status") or "").casefold()
    reason = str(review.get("reject_reason") or review.get("reason") or "").strip()
    visual = updated.visual_similarity
    overall = updated.overall_score
    rejected = decision in {"reject", "rejected", "отклонён", "отклонен"} or visual is not None and visual < 0.45 or overall < 0.45
    if rejected:
        updated.visual_review_status = "отклонён Codex по визуальному несоответствию"
        updated.visual_reject_reason = reason or "фундаментальное визуальное отличие от референса"
    else:
        updated.visual_review_status = "проверено Codex по фото кандидата"
    return updated


def is_final_candidate(candidate: ScoredCandidate, *, min_visual: float = 0.60, min_overall: float = 0.55) -> bool:
    return (
        candidate.product.availability_status == "in_stock"
        and candidate.family_relation in {"exact", "compatible", "unknown"}
        and candidate.visual_review_status == "проверено Codex по фото кандидата"
        and candidate.visual_similarity is not None
        and candidate.visual_similarity >= min_visual
        and candidate.overall_score >= min_overall
    )


def finalize_candidates(primary: list[ScoredCandidate], alternatives: list[ScoredCandidate] | None = None) -> tuple[list[ScoredCandidate], list[ScoredCandidate]]:
    reviewed = primary + (alternatives or [])
    rejected = [candidate for candidate in reviewed if candidate.visual_review_status.startswith("отклонён")]
    finalists = [candidate for candidate in reviewed if is_final_candidate(candidate)]
    if not finalists and alternatives:
        finalists = [candidate for candidate in alternatives if is_final_candidate(candidate)]
        for candidate in finalists:
            candidate.color_mode = "color_alternative"
            candidate.differences = [f"Альтернатива по цвету: требуется {candidate.differences[0] if candidate.differences else 'другой цвет'}", *candidate.differences]
    finalists.sort(key=lambda item: (item.color_mode != "primary", -(item.visual_similarity or 0), -item.overall_score))
    return finalists[:5], rejected


def live_recheck_candidate(candidate: ScoredCandidate, fetcher: object) -> tuple[ScoredCandidate | None, str | None]:
    """Re-fetch the public product page before it is shown to a user."""
    from .extract import parse_product_page

    page = fetcher.get(candidate.product.source_url, use_cache=False)
    if not page:
        return None, "live availability recheck failed"
    fresh = parse_product_page(page.content.decode("utf-8", "replace"), page.final_url, candidate.product.supplier)
    if not fresh or fresh.availability_status != "in_stock":
        return None, f"live availability is {fresh.availability_status if fresh else 'unknown'}"
    fresh.local_image_path = candidate.product.local_image_path
    fresh.availability_checked_at = datetime.now(timezone.utc).isoformat()
    return candidate.model_copy(update={"product": fresh}), None
