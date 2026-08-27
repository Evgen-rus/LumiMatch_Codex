from __future__ import annotations

from pathlib import Path

import pytest

from experiments.visual_retrieval.common import (
    InventoryRecord,
    VisualCorpusStore,
    VisualProduct,
    query_paths,
    select_natural_records,
)
from experiments.visual_retrieval.retrieval import (
    EmbeddingCache,
    aggregate_product_scores,
    benchmark_targets,
    cosine_similarity,
    metric_summary,
    run_model_safely,
)
from lumimatch.inventory import ProductInventoryStore


def _inventory_record(sku: str, *, supplier: str = "supplier.test") -> InventoryRecord:
    return InventoryRecord(
        supplier=supplier,
        product_url=f"https://{supplier}/product/{sku}",
        canonical_url=f"https://{supplier}/product/{sku}",
        sku=sku,
        discovery_source="test",
        discovered_at="now",
    )


def _visual_product(sku: str, *, scope: str = "natural") -> VisualProduct:
    return VisualProduct(
        supplier="supplier.test",
        product_url=f"https://supplier.test/product/{sku}",
        canonical_url=f"https://supplier.test/product/{sku}",
        sku=sku,
        title=f"Product {sku}",
        brand="Test",
        category="pendant",
        primary_image_url=f"https://supplier.test/image/{sku}.jpg",
        local_image_path=f"/tmp/{sku}.jpg",
        image_hash=sku,
        image_source="test",
        status="ready",
    )


def test_natural_selection_reads_inventory_only(tmp_path: Path) -> None:
    inventory = ProductInventoryStore(tmp_path / "inventory.sqlite3")
    inventory.upsert_many([_inventory_record("A-1"), _inventory_record("A-2")])
    records = select_natural_records(tmp_path / "inventory.sqlite3", ["supplier.test"])
    assert [record.sku for record in records] == ["A-1", "A-2"]


def test_system_bom_and_unmapped_are_excluded_from_visual_metrics() -> None:
    targets = benchmark_targets(
        [
            {
                "sku": "A",
                "matched_fixture_requirement": "F-01",
                "match_confidence": 0.9,
                "product_role": "VISUAL_SELECTION",
            },
            {
                "sku": "B",
                "matched_fixture_requirement": "F-02",
                "match_confidence": 0.9,
                "product_role": "SYSTEM_BOM",
            },
            {
                "sku": "C",
                "matched_fixture_requirement": None,
                "match_confidence": 0.9,
                "product_role": "VISUAL_SELECTION",
            },
        ]
    )
    assert [item["sku"] for item in targets["primary"]] == ["A"]


def test_low_confidence_mapping_is_exploratory_not_primary() -> None:
    targets = benchmark_targets(
        [
            {
                "sku": "A",
                "matched_fixture_requirement": "F-01",
                "match_confidence": 0.59,
                "product_role": "VISUAL_SELECTION",
            }
        ]
    )
    assert not targets["primary"]
    assert [item["sku"] for item in targets["exploratory"]] == ["A"]


def test_query_images_must_be_project_reference_crops(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"not-an-image")
    expected = tmp_path / "expected_kp.png"
    expected.write_bytes(b"not-an-image")
    assert query_paths({"reference_crop_paths": [str(reference), str(expected)]}) == [
        reference
    ]
    assert (
        query_paths({"reference_crop_paths": [str(tmp_path / "golden" / "query.png")]})
        == []
    )


def test_cosine_similarity_works_for_normalized_embeddings() -> None:
    np = pytest.importorskip("numpy")
    scores = cosine_similarity(
        np.asarray([[1.0, 0.0]]), np.asarray([[1.0, 0.0], [0.0, 1.0]])
    )
    assert scores.shape == (1, 2)
    assert scores[0, 0] == pytest.approx(1.0)
    assert scores[0, 1] == pytest.approx(0.0)


def test_multiple_images_use_max_product_similarity() -> None:
    rows = [
        {"canonical_url": "https://a/1", "image_hash": "a1", "sku": "A"},
        {"canonical_url": "https://a/1", "image_hash": "a2", "sku": "A"},
        {"canonical_url": "https://b/1", "image_hash": "b1", "sku": "B"},
    ]
    results = aggregate_product_scores(rows, [0.2, 0.9, 0.8])
    assert [item["sku"] for item in results] == ["A", "B"]
    assert results[0]["score"] == pytest.approx(0.9)


def test_cached_embeddings_are_reused(tmp_path: Path) -> None:
    np = pytest.importorskip("numpy")
    cache = EmbeddingCache(tmp_path, "test-model")
    cache.put("hash", np.asarray([1.0, 0.0], dtype="float32"))
    assert cache.get("hash").tolist() == [1.0, 0.0]


def test_oracle_products_do_not_enter_natural_scope(tmp_path: Path) -> None:
    store = VisualCorpusStore(tmp_path / "corpus.sqlite3")
    store.upsert(_visual_product("NATURAL"), scope="natural")
    store.upsert(_visual_product("ORACLE"), scope="oracle")
    assert [item.sku for item in store.all(scope="natural")] == ["NATURAL"]
    assert [item.sku for item in store.all(scope="oracle")] == ["ORACLE"]


def test_natural_and_oracle_metrics_are_separate() -> None:
    targets = [{"fixture_requirement": "F-01", "sku": "A"}]
    assert (
        metric_summary(targets, {"F-01": [{"sku": "A", "rank": 3}]})["recall_at_5"]
        == 1.0
    )
    assert metric_summary(targets, {"F-01": []})["recall_at_5"] == 0.0


def test_model_failure_isolated() -> None:
    result = run_model_safely(
        lambda: (_ for _ in ()).throw(RuntimeError("broken")), "broken-model"
    )
    assert result["status"] == "failed"
    assert "broken" in str(result["error"])
