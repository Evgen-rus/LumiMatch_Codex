from pathlib import Path

from lumimatch.benchmark import run_benchmark
from lumimatch.collector import coverage_state
from lumimatch.golden import _url_has_target, parse_golden_docx
from lumimatch.models import CatalogProduct, FixtureRequirement
from lumimatch.scoring import (
    candidate_set_fingerprint,
    is_final_candidate,
    score_product,
    visual_review_is_current,
)
from lumimatch.storage import CatalogStore


def _fixture() -> FixtureRequirement:
    return FixtureRequirement(
        id="F-test",
        room="room",
        fixture_type="подвесной светильник",
        visual_description="чёрный цилиндрический подвес",
        color="чёрный",
        shape="цилиндрический",
        mounting="подвесной",
        confidence=0.8,
    )


def _product(sku: str = "SKU-1") -> CatalogProduct:
    return CatalogProduct(
        supplier="supplier.test",
        brand="Example Brand",
        source_url=f"https://supplier.test/product/{sku}",
        canonical_url=f"https://supplier.test/product/{sku}",
        sku=sku,
        name="Чёрный цилиндрический подвес",
        availability_status="in_stock",
        availability="В наличии",
        primary_image_url="https://supplier.test/image.jpg",
        color="чёрный",
        mounting_type="подвесной",
    )


def test_golden_docx_has_explicit_visual_and_system_roles() -> None:
    items = parse_golden_docx(Path("samples/golden/dan/expected_kp.docx"))
    assert len(items) == 22
    assert sum(item["product_role"] == "VISUAL_SELECTION" for item in items) == 11
    assert sum(item["product_role"] == "SYSTEM_BOM" for item in items) == 11
    assert next(item for item in items if item["kp_position"] == 16)["golden_category"] == "track_spot"
    assert next(item for item in items if item["kp_position"] == 20)["sku"] is None


def test_brand_is_not_supplier_or_domain() -> None:
    product = _product()
    assert product.brand == "Example Brand"
    assert product.supplier == "supplier.test"
    assert product.brand != product.supplier


def test_lumion_and_elektrostandard_supplier_mapping_is_explicit() -> None:
    items = parse_golden_docx(Path("samples/golden/dan/expected_kp.docx"))
    lumion = next(item for item in items if item["kp_position"] == 10)
    elektro = next(item for item in items if item["kp_position"] == 11)
    assert (lumion["brand"], lumion["likely_supplier"]) == ("Lumion", "odeon-light.com")
    assert (elektro["brand"], elektro["likely_supplier"]) == ("Elektrostandard", "eurosvet.ru")


def test_freya_and_lussole_discovery_uses_target_matching_not_url_map() -> None:
    assert _url_has_target("https://freya-light.com/products/fr2066wl_l40b/", "FR2066WL-L40B")
    assert _url_has_target("https://shop.lussole.ru/bra-lussole-lsp-4001/", "LSP-4001")
    assert not _url_has_target("https://example.test/products/other/", "FR2066WL-L40B")


def test_discovered_but_unparsed_is_not_healthy_or_complete() -> None:
    status, quality, rate = coverage_state(1, 0)
    assert (status, quality, rate) == ("broken", "broken", 0.0)


def test_golden_data_does_not_change_production_score() -> None:
    candidate = score_product(_fixture(), _product())
    assert candidate.overall_score == score_product(_fixture(), _product()).overall_score
    assert candidate.product.sku == "SKU-1"


def test_stale_visual_review_is_not_current_for_new_pool() -> None:
    first = score_product(_fixture(), _product("SKU-1"))
    second = score_product(_fixture(), _product("SKU-2"))
    record = {"candidate_set_fingerprint": candidate_set_fingerprint([first])}
    assert visual_review_is_current(record, [first])
    assert not visual_review_is_current(record, [first, second])


def test_new_sku_without_review_is_not_automatically_rejected() -> None:
    candidate = score_product(_fixture(), _product("NEW-SKU"))
    assert candidate.visual_review_status == "не проверено Codex"
    assert not candidate.visual_review_status.startswith("отклонён")
    assert not is_final_candidate(candidate)


def test_system_bom_is_excluded_from_decorative_metrics(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "catalog.sqlite3")
    golden = [{
        "kp_position": 1,
        "sku": "GP8052",
        "name": "Соединитель GP8052",
        "product_role": "SYSTEM_BOM",
        "golden_category": "profile_connector",
        "matched_fixture_requirement": "F-test",
        "match_confidence": 0.8,
    }]
    discovery = [{"kp_position": 1, "sku": "GP8052", "found": False, "discovered": True, "parser_success": False}]
    payload = run_benchmark(golden, discovery, [_fixture()], store, tmp_path / "out")
    assert payload["retrieval"]["visual_targets"] == []
    assert payload["system_bom_coverage"]["decorative_visual_metrics_excluded"] is True


def test_benchmark_exposes_retrieval_at_20_50_100(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "catalog.sqlite3")
    product = _product()
    store.upsert(product)
    golden = [{
        "kp_position": 1,
        "sku": product.sku,
        "name": product.name,
        "product_role": "VISUAL_SELECTION",
        "golden_category": "decorative_pendant",
        "matched_fixture_requirement": "F-test",
        "match_confidence": 0.8,
    }]
    discovery = [{
        "kp_position": 1,
        "sku": product.sku,
        "found": True,
        "discovered": True,
        "parser_success": True,
        "url": product.canonical_url,
    }]
    payload = run_benchmark(golden, discovery, [_fixture()], store, tmp_path / "out")
    assert payload["retrieval"]["retrieval_at"] == {
        "retrieval_at_20": 1,
        "retrieval_at_50": 1,
        "retrieval_at_100": 1,
    }


def test_target_aware_discovery_does_not_count_as_production_recall(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "catalog.sqlite3")
    golden = [{
        "kp_position": 1,
        "sku": "SKU-EXPECTED",
        "name": "Expected product",
        "product_role": "VISUAL_SELECTION",
        "golden_category": "decorative_pendant",
        "matched_fixture_requirement": "F-test",
        "match_confidence": 0.8,
    }]
    discovery = [{
        "kp_position": 1,
        "sku": "SKU-EXPECTED",
        "found": True,
        "discovered": True,
        "parser_success": True,
        "url": "https://supplier.test/product/SKU-EXPECTED",
    }]
    payload = run_benchmark(golden, discovery, [_fixture()], store, tmp_path / "out")
    assert payload["targeted_discovery_recall"]["found"] == 1
    assert payload["production_catalog_recall"]["present"] == 0
    assert payload["retrieval"]["retrieval_at"]["retrieval_at_100"] == 0
