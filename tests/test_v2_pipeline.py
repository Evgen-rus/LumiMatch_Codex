import json

from lumimatch.availability import (
    availability_label,
    diagnostic_availability_label,
    normalize_availability,
    supplier_availability_mode,
)
from lumimatch.extract import parse_product_page
from lumimatch.models import CatalogProduct, FixtureRequirement
from lumimatch.report import write_unavailable_report
from lumimatch.scoring import (
    apply_visual_review,
    color_relation,
    finalize_candidates,
    finalize_unavailable_visual_candidates,
    hard_filter,
    is_final_candidate,
    live_recheck_candidate,
    score_product,
    wide_candidate_pool,
)


def requirement(**updates: object) -> FixtureRequirement:
    values = {"id": "F-test", "room": "гостиная", "fixture_type": "подвесной светильник", "visual_description": "чёрный компактный цилиндрический подвес", "color": "чёрный", "shape": "цилиндрический", "mounting": "подвесной", "confidence": 0.8}
    values.update(updates)
    return FixtureRequirement(**values)


def product(**updates: object) -> CatalogProduct:
    values = {"supplier": "supplier.test", "source_url": "https://supplier.test/product/1", "canonical_url": "https://supplier.test/product/1", "sku": "SKU-1", "name": "Чёрный подвес", "availability": "В наличии", "availability_status": "in_stock", "primary_image_url": "https://supplier.test/img/1.jpg", "color": "чёрный", "mounting_type": "подвесной"}
    values.update(updates)
    return CatalogProduct(**values)


def test_availability_status_is_conservative() -> None:
    cases = [("Нет в наличии", "out_of_stock"), ("OutOfStock", "out_of_stock"), ("Снят с производства", "discontinued"), ("Под заказ", "preorder"), ("Ожидается поступление", "expected"), ("Уточняйте наличие", "check_availability"), (None, "unknown")]
    for raw, expected in cases:
        assert normalize_availability(raw) == expected


def test_hard_filter_rejects_unavailable_and_incompatible_family() -> None:
    req = requirement()
    classic = product(name="Хрустальная люстра многорожковая", availability="В наличии")
    allowed, reasons = hard_filter(req, classic)
    assert not allowed
    assert any(reason.startswith("incompatible_family") for reason in reasons)
    unavailable = product(availability="Нет в наличии", availability_status="out_of_stock")
    allowed, reasons = hard_filter(req, unavailable)
    assert not allowed
    assert "availability:out_of_stock" in reasons


def test_stock_tracked_in_stock_passes() -> None:
    allowed, reasons = hard_filter(requirement(), product(), availability_mode="stock_tracked")
    assert allowed
    assert not any(reason.startswith("availability:") for reason in reasons)


def test_stock_tracked_unknown_is_rejected() -> None:
    allowed, reasons = hard_filter(requirement(), product(availability=None, availability_status="unknown"), availability_mode="stock_tracked")
    assert not allowed
    assert "availability:unknown" in reasons


def test_stock_not_published_without_availability_passes() -> None:
    candidate = product(availability=None, availability_source_text=None, availability_status="unknown")
    allowed, reasons = hard_filter(requirement(), candidate, availability_mode="stock_not_published")
    assert allowed
    assert not any(reason.startswith("availability:") for reason in reasons)
    assert availability_label("unknown", "stock_not_published") == "Поставщик не публикует остатки"


def test_stock_not_published_discontinued_is_rejected() -> None:
    allowed, reasons = hard_filter(requirement(), product(availability="Снят с производства", availability_status="discontinued"), availability_mode="stock_not_published")
    assert not allowed
    assert "availability:discontinued" in reasons


def test_stock_not_published_out_of_stock_is_rejected() -> None:
    allowed, reasons = hard_filter(requirement(), product(availability="Нет в наличии", availability_status="out_of_stock"), availability_mode="stock_not_published")
    assert not allowed
    assert "availability:out_of_stock" in reasons


def test_stock_not_published_preorder_is_rejected() -> None:
    allowed, reasons = hard_filter(requirement(), product(availability="Под заказ", availability_status="preorder"), availability_mode="stock_not_published")
    assert not allowed
    assert "availability:preorder" in reasons


def test_stock_not_published_expected_is_rejected() -> None:
    allowed, reasons = hard_filter(requirement(), product(availability="Ожидается", availability_status="expected"), availability_mode="stock_not_published")
    assert not allowed
    assert "availability:expected" in reasons


def test_unavailable_visual_pool_allows_temporary_statuses_but_not_unknown_or_discontinued() -> None:
    candidates = wide_candidate_pool(
        requirement(),
        [
            product(sku="OOS", availability="Нет в наличии", availability_status="out_of_stock"),
            product(sku="UNKNOWN", availability=None, availability_status="unknown"),
            product(sku="DISC", availability="Снят с производства", availability_status="discontinued"),
        ],
        availability_policy="unavailable_visual",
    )
    assert [item.product.sku for item in candidates] == ["OOS"]


def test_unavailable_visual_finalist_is_independent_from_sellable_finalist() -> None:
    candidate = apply_visual_review(
        score_product(requirement(), product(availability="Нет в наличии", availability_status="out_of_stock")),
        {"decision": "accept", "visual_similarity": 0.82, "overall_score": 0.76},
    )
    sellable, _ = finalize_candidates([candidate])
    unavailable, _ = finalize_unavailable_visual_candidates([candidate])
    assert sellable == []
    assert [item.product.sku for item in unavailable] == ["SKU-1"]
    assert not is_final_candidate(candidate)


def test_unavailable_report_labels_are_explicit() -> None:
    assert diagnostic_availability_label("out_of_stock") == "Сейчас нет в наличии"
    assert diagnostic_availability_label("preorder") == "Под заказ"
    assert diagnostic_availability_label("expected") == "Ожидается поступление"
    assert diagnostic_availability_label("check_availability") == "Наличие нужно уточнить"


def test_unavailable_report_serializes_diagnostic_label(tmp_path) -> None:
    candidate = apply_visual_review(
        score_product(requirement(), product(availability="Нет в наличии", availability_status="out_of_stock")),
        {"decision": "accept", "visual_similarity": 0.82, "overall_score": 0.76},
    )
    write_unavailable_report(
        [requirement()],
        {"F-test": [candidate]},
        tmp_path,
        search_stats={"F-test": {"out_of_stock_visual_finalists": 1}},
    )
    payload = json.loads((tmp_path / "lumimatch_sample_unavailable.json").read_text(encoding="utf-8"))
    assert payload["requirements"][0]["candidates"][0]["availability_label"] == "Сейчас нет в наличии"


def test_supplier_config_defaults_to_tracked_and_exposes_verified_mode() -> None:
    assert supplier_availability_mode("citilux.ru") == "stock_tracked"
    assert supplier_availability_mode("unknown.example") == "stock_tracked"


def test_rejected_by_vision_never_finalizes() -> None:
    candidate = score_product(requirement(), product())
    rejected = apply_visual_review(candidate, {"visual_similarity": 0.1, "decision": "reject", "reason": "другая геометрия"})
    finalists, rejected_items = finalize_candidates([rejected])
    assert finalists == []
    assert rejected_items[0].visual_reject_reason == "другая геометрия"


def test_zero_final_candidates_is_valid() -> None:
    assert wide_candidate_pool(requirement(), [product(availability_status="unknown")]) == []


def test_preorder_is_not_in_pool() -> None:
    assert wide_candidate_pool(requirement(), [product(availability="Под заказ", availability_status="preorder")]) == []


def test_expected_is_not_in_pool() -> None:
    assert wide_candidate_pool(requirement(), [product(availability="Ожидается", availability_status="expected")]) == []


def test_product_without_photo_is_not_in_pool() -> None:
    assert wide_candidate_pool(requirement(), [product(primary_image_url=None, local_image_path=None)]) == []


def test_track_rail_does_not_match_pendant() -> None:
    assert wide_candidate_pool(requirement(), [product(name="Шинопровод трековой системы", product_family="track_rail")]) == []


def test_live_recheck_requires_confirmed_in_stock() -> None:
    candidate = score_product(requirement(), product())

    class Page:
        status_code = 200
        final_url = "https://supplier.test/product/1"
        content = b"<html><head><script type='application/ld+json'>{\"@type\":\"Product\",\"name\":\"Black pendant\",\"sku\":\"SKU-1\",\"image\":[\"/img.jpg\"],\"offers\":{\"availability\":\"https://schema.org/OutOfStock\"}}</script></head><body><h1>Black pendant</h1></body></html>"

    class Fetcher:
        def get(self, url: str, *, use_cache: bool) -> Page:
            assert use_cache is False
            return Page()

    refreshed, reason = live_recheck_candidate(candidate, Fetcher())
    assert refreshed is None
    assert "out_of_stock" in (reason or "")


def test_live_recheck_stock_not_published_does_not_require_positive_stock() -> None:
    candidate = score_product(requirement(), product(availability=None, availability_status="unknown"))

    class Page:
        status_code = 200
        final_url = "https://supplier.test/product/1"
        content = b"<html><head><script type='application/ld+json'>{\"@type\":\"Product\",\"name\":\"Black pendant\",\"sku\":\"SKU-1\",\"image\":[\"/img.jpg\"]}</script></head><body><h1>Black pendant</h1><p>SKU-1</p></body></html>"

    class Fetcher:
        def get(self, url: str, *, use_cache: bool) -> Page:
            assert use_cache is False
            return Page()

    refreshed, reason = live_recheck_candidate(candidate, Fetcher(), availability_mode="stock_not_published")
    assert refreshed is not None
    assert reason is None
    assert refreshed.product.availability_status == "unknown"


def test_live_recheck_stock_not_published_rejects_negative_marker() -> None:
    candidate = score_product(requirement(), product(availability=None, availability_status="unknown"))

    class Page:
        status_code = 200
        final_url = "https://supplier.test/product/1"
        content = "<html><head><script type='application/ld+json'>{\"@type\":\"Product\",\"name\":\"Black pendant\",\"sku\":\"SKU-1\",\"image\":[\"/img.jpg\"]}</script></head><body><h1>Black pendant</h1><p>SKU-1</p><p>Нет в наличии</p></body></html>".encode()

    class Fetcher:
        def get(self, url: str, *, use_cache: bool) -> Page:
            return Page()

    refreshed, reason = live_recheck_candidate(candidate, Fetcher(), availability_mode="stock_not_published")
    assert refreshed is None
    assert "out_of_stock" in (reason or "")


def test_mirror_light_requires_ip_in_wet_zone() -> None:
    req = requirement(fixture_type="подсветка зеркала", visual_description="светильник у зеркала", mounting="настенный", technical_constraints=["для влажного помещения", "нужен IP"])
    allowed, reasons = hard_filter(req, product(name="Подсветка зеркала", product_family="mirror_light"))
    assert not allowed
    assert "missing_ip_for_wet_zone" in reasons


def test_single_pendant_and_chandelier_are_different_families() -> None:
    req = requirement()
    allowed, reasons = hard_filter(req, product(name="Люстра многорожковая", product_family="chandelier"))
    assert not allowed
    assert any(reason.startswith("incompatible_family") for reason in reasons)


def test_height_mm_participates_and_packaging_is_ignored() -> None:
    req = requirement(approximate_dimensions={"height_mm": 300})
    close = product(height_mm=300, height=300)
    far = product(height_mm=900, height=900)
    assert score_product(req, close).dimension_match > score_product(req, far).dimension_match
    html = """
    <html><head><script type='application/ld+json'>
    {"@type":"Product","name":"Linear","sku":"L-1","image":["/product.jpg"],"offers":{"availability":"https://schema.org/InStock"}}
    </script></head><body><h1>Linear</h1>
    <div class='product-gallery'><img src='/product.jpg'><img src='/recommendations/other.jpg'></div>
    <table><tr><th>Высота</th><td>300 мм</td></tr><tr><th>Высота упаковки</th><td>900 мм</td></tr></table>
    </body></html>
    """
    parsed = parse_product_page(html, "https://supplier.test/product/l-1", "supplier.test")
    assert parsed is not None
    assert parsed.height_mm == 300
    assert parsed.image_urls == ["https://supplier.test/product.jpg"]


def test_linear_profile_does_not_match_track_spot() -> None:
    req = requirement(fixture_type="линейный потолочный светильник", visual_description="непрерывная линейная линия", shape="линейный", mounting="потолочный")
    track_spot = product(name="Трековый спот цилиндр", product_family="track_spot")
    assert wide_candidate_pool(req, [track_spot]) == []


def test_color_fallback_is_separate() -> None:
    req = requirement()
    black = product(sku="BLACK", color="чёрный")
    white = product(sku="WHITE", color="белый")
    assert [candidate.product.sku for candidate in wide_candidate_pool(req, [black, white])] == ["BLACK"]
    alternatives = wide_candidate_pool(req, [black, white], include_color_alternatives=True)
    assert {candidate.color_mode for candidate in alternatives} == {"primary", "color_alternative"}
    assert color_relation("чёрный", "белый")[0] == "mismatch"
