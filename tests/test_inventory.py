from pathlib import Path

from lumimatch.benchmark import _review_completeness
from lumimatch.inventory import (
    InventoryRecord,
    ProductInventoryStore,
    select_hydration_urls,
)
from lumimatch.models import CatalogProduct, FixtureRequirement
from lumimatch.scoring import hard_filter, score_product
from lumimatch.taxonomy import classify_text


def _requirement(**updates: object) -> FixtureRequirement:
    values = {
        "id": "F-test",
        "room": "спальня",
        "fixture_type": "настенное бра",
        "visual_description": "чёрное вертикальное бра",
        "color": "чёрный",
        "shape": "вертикальный",
        "mounting": "настенный",
        "confidence": 0.8,
    }
    values.update(updates)
    return FixtureRequirement(**values)


def _record(url: str, *, category: str | None = None) -> InventoryRecord:
    return InventoryRecord(
        supplier="supplier.test",
        product_url=url,
        canonical_url=url,
        category=category,
        discovery_source="test",
        discovered_at="2026-01-01T00:00:00+00:00",
    )


def test_inventory_store_round_trips_lightweight_records(tmp_path: Path) -> None:
    store = ProductInventoryStore(tmp_path / "inventory.sqlite3")
    store.upsert_many([_record("https://supplier.test/catalog/bra-black-123")])
    records = store.all()
    assert len(records) == 1
    assert records[0].product_url.endswith("bra-black-123")
    assert store.supplier_counts() == {"supplier.test": 1}


def test_requirement_hydration_prefers_family_metadata_over_inventory_order() -> None:
    records = [
        _record("https://supplier.test/catalog/pendant-001"),
        _record("https://supplier.test/catalog/wall-sconce-black-002", category="wall-sconce"),
        _record("https://supplier.test/catalog/pendant-003"),
    ]
    plan = select_hydration_urls(
        [_requirement()],
        records,
        per_requirement_limit=1,
        per_supplier_limit=10,
    )
    assert [item.product_url for item in plan.by_requirement["F-test"]] == [
        "https://supplier.test/catalog/wall-sconce-black-002"
    ]


def test_visual_stage_can_keep_unknown_ip_without_changing_strict_gate() -> None:
    requirement = _requirement(
        fixture_type="подсветка зеркала",
        visual_description="светильник у зеркала",
        technical_constraints=["для влажного помещения", "нужен IP"],
    )
    product = CatalogProduct(
        supplier="supplier.test",
        source_url="https://supplier.test/product/1",
        canonical_url="https://supplier.test/product/1",
        sku="SKU-1",
        name="Вертикальное бра у зеркала",
        product_family="mirror_light",
        primary_image_url="https://supplier.test/image.jpg",
    )
    strict_allowed, strict_reasons = hard_filter(requirement, product)
    visual_allowed, visual_reasons = hard_filter(
        requirement,
        product,
        availability_policy="ignore",
        allow_unknown_technical=True,
    )
    assert not strict_allowed
    assert "missing_ip_for_wet_zone" in strict_reasons
    assert visual_allowed
    assert visual_reasons == []
    assert score_product(requirement, product).technical_status == "requires_ip_check"


def test_review_completeness_requires_a_decision_for_every_candidate() -> None:
    requirement = _requirement()
    candidates = [
        score_product(
            requirement,
            CatalogProduct(
                supplier="supplier.test",
                source_url=f"https://supplier.test/product/{sku}",
                canonical_url=f"https://supplier.test/product/{sku}",
                sku=sku,
                name="Чёрное бра",
                primary_image_url="https://supplier.test/image.jpg",
                product_family="wall_sconce",
            ),
        )
        for sku in ("A", "B")
    ]
    entry = {"candidates": [{"sku": "A", "decision": "reject"}, {"sku": "B", "decision": "pending"}]}
    incomplete = _review_completeness(entry, candidates)
    assert incomplete["review_complete"] is False
    assert incomplete["pending_count"] == 1
    entry["candidates"][1]["decision"] = "reject"
    complete = _review_completeness(entry, candidates)
    assert complete["review_complete"] is True
    assert complete["reviewed_count"] == 2


def test_ceiling_requirement_rejects_known_pendant_mounting() -> None:
    requirement = _requirement(
        fixture_type="линейный потолочный светильник",
        visual_description="чёрная линейная потолочная система",
        mounting="потолочный",
        taxonomy_family="linear",
    )
    product = CatalogProduct(
        supplier="supplier.test",
        source_url="https://supplier.test/product/pendant",
        canonical_url="https://supplier.test/product/pendant",
        sku="P-1",
        name="Чёрный подвесной линейный светильник",
        product_family="linear",
        mounting_type="подвесной",
        primary_image_url="https://supplier.test/image.jpg",
    )
    allowed, reasons = hard_filter(requirement, product, availability_policy="ignore")
    assert not allowed
    assert "mounting_mismatch" in reasons


def test_ceiling_track_requirement_rejects_known_wall_mounting() -> None:
    requirement = _requirement(
        fixture_type="точечный или трековый светильник",
        visual_description="чёрный цилиндрический потолочный спот",
        mounting="потолочный / трековый",
        taxonomy_family="track_spot",
    )
    product = CatalogProduct(
        supplier="supplier.test",
        source_url="https://supplier.test/product/wall-spot",
        canonical_url="https://supplier.test/product/wall-spot",
        sku="S-1",
        name="Чёрный настенный спот",
        product_family="spot",
        mounting_type="настенный",
        primary_image_url="https://supplier.test/image.jpg",
    )
    allowed, reasons = hard_filter(requirement, product, availability_policy="ignore")
    assert not allowed
    assert "mounting_mismatch" in reasons


def test_pendant_requirement_keeps_known_pendant_mounting() -> None:
    requirement = _requirement(
        fixture_type="подвесной светильник",
        visual_description="чёрный цилиндрический подвес",
        mounting="подвесной, потолочный",
        taxonomy_family="pendant",
    )
    product = CatalogProduct(
        supplier="supplier.test",
        source_url="https://supplier.test/product/pendant",
        canonical_url="https://supplier.test/product/pendant",
        sku="P-2",
        name="Чёрный цилиндрический подвес",
        product_family="pendant",
        mounting_type="подвесной",
        primary_image_url="https://supplier.test/image.jpg",
    )
    allowed, reasons = hard_filter(requirement, product, availability_policy="ignore")
    assert allowed
    assert reasons == []


def test_explicit_track_mounting_hardware_is_not_a_visual_fixture() -> None:
    assert classify_text("Крепеж трековый для корпуса DIY") == "accessory"
    assert classify_text("Профиль для ленты LED") == "linear_profile"
