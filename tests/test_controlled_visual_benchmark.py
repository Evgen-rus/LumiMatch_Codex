import pytest

pytest.importorskip("numpy", reason="Controlled benchmark runs in .venv-visual")

from experiments.visual_retrieval.controlled import Candidate, _select_pool, classify_family
from experiments.visual_retrieval.controlled import TargetSpec


def test_family_classifier_keeps_same_family_and_rejects_accessories() -> None:
    assert classify_family(title="Бра настенное Bradford", category="bra-dekorativnyie", url="https://example/bra") == "decorative_wall"
    assert classify_family(title="Подвесной светильник", category="podvesnye-svetilniki", url="https://example/podvesnoy-svetilnik") == "pendant_single"
    assert classify_family(title="Трековый светильник 24°", category="potolochnie", url="https://example/track-light") == "track_spot"
    assert classify_family(title="Подвесная люстра", category="lustri", url="https://example/lyustra", explicit="wall_sconce") == "unknown"
    assert classify_family(title="Подвесной светильник", category="lustri", url="https://example/pendant", explicit="wall_sconce") == "pendant_single"
    assert classify_family(title="Коннектор для шинопровода", category="accessories", url="https://example/connector") == "accessory"


def test_pool_selection_is_deterministic_and_contains_positive() -> None:
    target = TargetSpec("F-X", "wall_sconce", ("wall_sconce",), "GOLD", "positive", None, True, "test")
    candidates = [
        Candidate("p", "GOLD", "s", "https://example/positive", "wall_sconce", __file__, image_hash="p"),
        Candidate("a", "A", "s", "https://example/a", "wall_sconce", __file__, image_hash="a"),
        Candidate("b", "B", "s", "https://example/b", "wall_sconce", __file__, image_hash="b"),
        Candidate("x", "X", "s", "https://example/x", "pendant_single", __file__, image_hash="x"),
    ]
    first, positive = _select_pool(target, candidates, limit=3)
    second, _ = _select_pool(target, candidates, limit=3)
    assert [item.candidate_id for item in first] == [item.candidate_id for item in second]
    assert positive.candidate_id == "p"
    assert {item.candidate_id for item in first} == {"p", "a", "b"}


def test_ranking_is_image_only_and_aggregation_is_explicit() -> None:
    import numpy as np
    from experiments.visual_retrieval.controlled import _rank

    pool = [{"candidate_id": x, "image": "unused", "supplier": "s", "sku": "hidden", "url": "unused"} for x in ("a", "b")]
    matrix = np.eye(2)
    queries = np.array([[0.9, 0.4], [0.1, 0.8]])
    assert _rank(pool, matrix, queries, "max")[0]["candidate_id"] == "a"
    assert _rank(pool, matrix, queries, "mean")[0]["candidate_id"] == "b"
    pool[0]["sku"] = "GOLDEN-CHEAT-MARKER"
    assert _rank(pool, matrix, queries, "mean")[0]["candidate_id"] == "b"


def test_missing_positive_is_not_silently_reported_as_success() -> None:
    from experiments.visual_retrieval.controlled import _recall, _target_rank
    assert _target_rank([{"candidate_id": "x", "rank": 1}], "missing") is None
    assert _recall([1, 25, None], 20) == 0.3333


def test_explicit_wrong_taxonomy_cannot_override_accessory() -> None:
    assert classify_family(title="Коннектор", category="tracks", url="https://example/connector", explicit="track_spot") == "accessory"
    assert classify_family(title="Светильник", category="spoty_podvesnye", url="https://example/spoty_podvesnye/x", explicit="spot") == "pendant_single"


def test_empty_production_image_path_is_skipped(tmp_path, monkeypatch) -> None:
    import json
    import sqlite3
    import experiments.visual_retrieval.controlled as controlled
    path = tmp_path / "catalog.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE products(payload_json TEXT)")
        db.execute("INSERT INTO products VALUES (?)", (json.dumps({"local_image_path": ""}),))
    monkeypatch.setattr(controlled, "PRODUCTION_DB", path)
    assert controlled._production_candidates() == []


def test_embedding_cache_resumes_and_recovers_corruption(tmp_path, monkeypatch) -> None:
    import numpy as np
    import experiments.visual_retrieval.controlled as controlled
    monkeypatch.setattr(controlled, "DATA", tmp_path / "cache")
    source = tmp_path / "image.fixture"
    source.write_bytes(b"image fixture")

    class FakeEncoder:
        name = "test_encoder"
        calls = 0

        def encode_images(self, paths, batch_size):
            self.calls += 1
            return np.array([[3.0, 4.0]] * len(paths))

    encoder = FakeEncoder()
    result = controlled._encode_paths(encoder, [source], batch_size=1)
    np.testing.assert_allclose(result, [[0.6, 0.8]])
    controlled._encode_paths(encoder, [source], batch_size=1)
    assert encoder.calls == 1
    cache = controlled._embedding_cache_path(encoder.name, controlled.sha256_file(source))
    cache.write_bytes(b"interrupted")
    controlled._encode_paths(encoder, [source], batch_size=1)
    assert encoder.calls == 2


def test_fingerprint_detects_image_change_without_manifest_change(tmp_path, monkeypatch) -> None:
    import json
    import experiments.visual_retrieval.controlled as controlled
    monkeypatch.setattr(controlled, "OUTPUT", tmp_path)
    monkeypatch.setattr(controlled, "TARGETS", {"F-X": None})
    (tmp_path / "queries").mkdir()
    (tmp_path / "pools").mkdir()
    query, product = tmp_path / "query.fixture", tmp_path / "product.fixture"
    query.write_bytes(b"query")
    product.write_bytes(b"product")
    (tmp_path / "queries/manifest.json").write_text(json.dumps([{"path": str(query)}]))
    (tmp_path / "pools/F-X.json").write_text(json.dumps([{"image": str(product)}]))
    before = controlled.input_fingerprints()
    query.write_bytes(b"changed query")
    assert before != controlled.input_fingerprints()
