"""Embedding caches, pure image retrieval and golden-set evaluation."""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import (
    SPIKE_DATA,
    VisualCorpusStore,
    VisualProduct,
    normalize_sku,
    query_paths,
    sha256_file,
    utc_now,
)
from .encoders import Encoder, model_metadata


def _np() -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "numpy is required for embedding and retrieval commands"
        ) from exc
    return np


class EmbeddingCache:
    """One normalized `.npy` file per image/query hash for resumable encoding."""

    def __init__(self, root: Path, model: str) -> None:
        self.root = root / model / "image_cache"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, image_hash: str) -> Path:
        return self.root / f"{image_hash}.npy"

    def get(self, image_hash: str) -> Any | None:
        path = self.path(image_hash)
        if not path.exists():
            return None
        try:
            return _np().load(path, allow_pickle=False)
        except (OSError, ValueError):
            return None

    def put(self, image_hash: str, embedding: Any) -> None:
        target = self.path(image_hash)
        temp = target.with_name(f".{target.name}.tmp")
        _np().save(temp, embedding.astype("float32", copy=False), allow_pickle=False)
        generated = temp if temp.exists() else temp.with_suffix(temp.suffix + ".npy")
        generated.replace(target)


@dataclass(frozen=True)
class IndexRow:
    supplier: str
    canonical_url: str
    product_url: str
    sku: str | None
    title: str | None
    brand: str | None
    category: str | None
    image_hash: str
    local_image_path: str
    position: int
    is_primary: bool
    scope: str

    def as_dict(self) -> dict[str, object]:
        return {
            "supplier": self.supplier,
            "canonical_url": self.canonical_url,
            "product_url": self.product_url,
            "sku": self.sku,
            "title": self.title,
            "brand": self.brand,
            "category": self.category,
            "image_hash": self.image_hash,
            "local_image_path": self.local_image_path,
            "position": self.position,
            "is_primary": self.is_primary,
            "scope": self.scope,
        }


def _index_rows(
    store: VisualCorpusStore, *, scope: str, gallery_images: int
) -> list[IndexRow]:
    rows: list[IndexRow] = []
    product_scopes = [(scope, store.all(scope=scope, ready_only=True))]
    if scope == "oracle":
        product_scopes = [
            ("natural", store.all(scope="natural", ready_only=True)),
            ("oracle", store.all(scope="oracle", ready_only=True)),
        ]
    for product_scope, products in product_scopes:
        for product in products:
            image_rows = store.images(
                product.canonical_url,
                scope=product_scope,
                max_images=max(1, gallery_images),
            )
            if not image_rows and product.local_image_path and product.image_hash:
                rows.append(
                    IndexRow(
                        product.supplier,
                        product.canonical_url,
                        product.product_url,
                        product.sku,
                        product.title,
                        product.brand,
                        product.category,
                        product.image_hash,
                        product.local_image_path,
                        1,
                        True,
                        product_scope,
                    )
                )
                continue
            for image in image_rows:
                if (
                    not image["image_hash"]
                    or not image["local_image_path"]
                    or not Path(image["local_image_path"]).exists()
                ):
                    continue
                rows.append(
                    IndexRow(
                        product.supplier,
                        product.canonical_url,
                        product.product_url,
                        product.sku,
                        product.title,
                        product.brand,
                        product.category,
                        image["image_hash"],
                        image["local_image_path"],
                        int(image["position"]),
                        bool(image["is_primary"]),
                        product_scope,
                    )
                )
    return rows


def build_embedding_index(
    encoder: Encoder,
    store: VisualCorpusStore,
    *,
    scope: str = "natural",
    variant: str = "primary",
    gallery_images: int = 1,
    batch_size: int = 16,
    output_root: Path = SPIKE_DATA / "embeddings",
) -> dict[str, object]:
    """Create/rebuild an index while reusing per-image embedding cache."""
    np = _np()
    started = time.monotonic()
    gallery_images = 1 if variant == "primary" else max(1, min(gallery_images, 3))
    rows = _index_rows(store, scope=scope, gallery_images=gallery_images)
    cache = EmbeddingCache(output_root, encoder.name)
    pending_hashes: list[str] = []
    pending_paths: list[Path] = []
    pending_seen: set[str] = set()
    vectors: dict[str, Any] = {}
    for row in rows:
        if row.image_hash in vectors:
            continue
        if row.image_hash in pending_seen:
            continue
        cached = cache.get(row.image_hash)
        if cached is not None:
            vectors[row.image_hash] = cached
        else:
            pending_seen.add(row.image_hash)
            pending_hashes.append(row.image_hash)
            pending_paths.append(Path(row.local_image_path))
    encoded = 0
    for start in range(0, len(pending_paths), max(1, batch_size)):
        paths = pending_paths[start : start + max(1, batch_size)]
        hashes = pending_hashes[start : start + max(1, batch_size)]
        batch = encoder.encode_images(paths, batch_size=len(paths))
        for image_hash, vector in zip(hashes, batch, strict=True):
            vector = vector / max(float(np.linalg.norm(vector)), 1e-12)
            cache.put(image_hash, vector)
            vectors[image_hash] = vector
            encoded += 1
    matrix = (
        np.vstack([vectors[row.image_hash] for row in rows]).astype(
            "float32", copy=False
        )
        if rows
        else np.empty((0, 0), dtype="float32")
    )
    index_dir = output_root / encoder.name / variant / scope
    index_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = index_dir / "matrix.npy"
    np.save(matrix_path, matrix, allow_pickle=False)
    payload = {
        "status": "ready",
        "model": model_metadata(encoder),
        "scope": scope,
        "variant": variant,
        "gallery_images": gallery_images,
        "rows": [row.as_dict() for row in rows],
        "image_rows": len(rows),
        "unique_images": len(vectors),
        "embedding_dimension": int(matrix.shape[1])
        if matrix.ndim == 2 and matrix.size
        else 0,
        "cache_hits": len(vectors) - encoded,
        "encoded_now": encoded,
        "build_seconds": round(time.monotonic() - started, 3),
        "matrix_path": str(matrix_path),
        "created_at": utc_now(),
    }
    (index_dir / "index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    payload["index_disk_mb"] = round(matrix_path.stat().st_size / 1024**2, 3)
    (index_dir / "index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def load_index(index_json: Path) -> tuple[dict[str, object], Any]:
    np = _np()
    payload = json.loads(index_json.read_text(encoding="utf-8"))
    matrix_path = Path(str(payload["matrix_path"]))
    if not matrix_path.is_absolute():
        matrix_path = index_json.parent / matrix_path
    matrix = np.load(matrix_path, allow_pickle=False)
    return payload, matrix


def cosine_similarity(query: Any, matrix: Any) -> Any:
    """Cosine/dot similarity; inputs are normalized defensively."""
    np = _np()
    query_array = np.asarray(query, dtype="float32")
    matrix_array = np.asarray(matrix, dtype="float32")
    query_array = query_array / np.maximum(
        np.linalg.norm(query_array, axis=-1, keepdims=True), 1e-12
    )
    matrix_array = matrix_array / np.maximum(
        np.linalg.norm(matrix_array, axis=-1, keepdims=True), 1e-12
    )
    return query_array @ matrix_array.T


def aggregate_product_scores(
    rows: list[dict[str, object]], image_scores: Any
) -> list[dict[str, object]]:
    """Collapse gallery image hits to one product using maximum similarity."""
    grouped: dict[str, dict[str, object]] = {}
    for row, score in zip(rows, list(image_scores), strict=True):
        key = str(row["canonical_url"])
        score_value = float(score)
        current = grouped.get(key)
        if current is None or score_value > float(current["score"]):
            grouped[key] = {
                **row,
                "score": score_value,
                "best_image_hash": row.get("image_hash"),
                "best_position": row.get("position"),
            }
    return sorted(
        grouped.values(),
        key=lambda item: (-float(item["score"]), str(item.get("canonical_url", ""))),
    )


def _text_for_requirement(requirement: dict[str, object]) -> str:
    return ". ".join(
        str(requirement.get(key) or "")
        for key in ("fixture_type", "visual_description", "color", "shape", "mounting")
        if requirement.get(key)
    )


def _query_cache_path(model: str, path: Path) -> Path:
    target = (
        SPIKE_DATA / "embeddings" / model / "query_cache" / f"{sha256_file(path)}.npy"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _encode_query(encoder: Encoder, path: Path) -> Any:
    np = _np()
    target = _query_cache_path(encoder.name, path)
    if target.exists():
        try:
            return np.load(target, allow_pickle=False)
        except (OSError, ValueError):
            pass
    embedding = encoder.encode_images([path], batch_size=1)[0]
    temp = target.with_name(f".{target.name}.tmp")
    np.save(temp, embedding.astype("float32", copy=False), allow_pickle=False)
    generated = temp if temp.exists() else temp.with_suffix(temp.suffix + ".npy")
    generated.replace(target)
    return embedding


def retrieve_requirement(
    encoder: Encoder,
    index_payload: dict[str, object],
    matrix: Any,
    requirement: dict[str, object],
    *,
    text_variant: str = "image_only",
) -> dict[str, object]:
    paths = query_paths(requirement)
    if not paths:
        return {
            "requirement_id": requirement.get("id"),
            "query_paths": [],
            "results": [],
            "error": "no_project_reference_crops",
        }
    if getattr(matrix, "shape", (0, 0))[0] == 0:
        return {
            "requirement_id": requirement.get("id"),
            "query_paths": [str(path) for path in paths],
            "query_count": len(paths),
            "text_variant": text_variant,
            "results": [],
            "error": "empty_visual_index",
        }
    query_embeddings = [_encode_query(encoder, path) for path in paths]
    image_scores = cosine_similarity(query_embeddings, matrix)
    image_score = (
        image_scores.max(axis=0) if len(query_embeddings) > 1 else image_scores[0]
    )
    final_scores = image_score
    text_weight = None
    text_scores = None
    if text_variant != "image_only":
        if not encoder.supports_text:
            return {
                "requirement_id": requirement.get("id"),
                "query_paths": [str(path) for path in paths],
                "results": [],
                "error": f"{encoder.name}_has_no_text_encoder",
            }
        text_weight = 0.15 if text_variant == "visual_first_0.85" else 0.30
        text_embedding = encoder.encode_text([_text_for_requirement(requirement)])[0]
        text_scores = cosine_similarity([text_embedding], matrix)[0]
        final_scores = (1.0 - text_weight) * image_score + text_weight * text_scores
    rows = list(index_payload.get("rows", []))
    image_results = aggregate_product_scores(rows, image_score)
    image_by_url = {str(result["canonical_url"]): result for result in image_results}
    results = aggregate_product_scores(rows, final_scores)
    for rank, result in enumerate(results, start=1):
        result["rank"] = rank
        image_result = image_by_url[str(result["canonical_url"])]
        result["image_score"] = float(image_result["score"])
        if text_scores is not None:
            result["text_variant"] = text_variant
            result["text_weight"] = text_weight
    return {
        "requirement_id": requirement.get("id"),
        "query_paths": [str(path) for path in paths],
        "query_count": len(paths),
        "text_variant": text_variant,
        "results": results,
    }


def benchmark_targets(
    golden: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    primary: list[dict[str, object]] = []
    exploratory: list[dict[str, object]] = []
    for item in golden:
        if item.get("product_role") == "SYSTEM_BOM":
            continue
        sku = str(item.get("sku") or "") or None
        requirement_id = str(item.get("matched_fixture_requirement") or "") or None
        confidence = float(item.get("match_confidence") or 0.0)
        if not sku or not requirement_id:
            continue
        target = {
            "kp_position": item.get("kp_position"),
            "sku": sku,
            "fixture_requirement": requirement_id,
            "confidence": confidence,
            "name": item.get("name"),
            "supplier": item.get("likely_supplier"),
        }
        if confidence >= 0.60:
            primary.append(target)
        elif confidence >= 0.40:
            exploratory.append(target)
    return {"primary": primary, "exploratory": exploratory}


def _target_rank(results: list[dict[str, object]], sku: str | None) -> int | None:
    key = normalize_sku(sku)
    if not key:
        return None
    for result in results:
        if normalize_sku(result.get("sku")) == key:
            return int(result["rank"])
    return None


def metric_summary(
    targets: list[dict[str, object]], rankings: dict[str, list[dict[str, object]]]
) -> dict[str, object]:
    ranks: list[int | None] = []
    for target in targets:
        ranks.append(
            _target_rank(
                rankings.get(str(target["fixture_requirement"]), []), str(target["sku"])
            )
        )
    total = len(ranks)
    found = [rank for rank in ranks if rank is not None]
    values: dict[str, object] = {"targets": total, "found": len(found)}
    for k in (1, 5, 10, 20, 50, 100):
        values[f"recall_at_{k}"] = (
            round(sum(rank is not None and rank <= k for rank in ranks) / total, 4)
            if total
            else None
        )
    values["mrr"] = (
        round(sum(1.0 / rank if rank else 0.0 for rank in ranks) / total, 4)
        if total
        else None
    )
    values["median_rank"] = statistics.median(found) if found else None
    values["ranks"] = ranks
    return values


def natural_corpus_recall(
    targets: list[dict[str, object]], products: list[VisualProduct]
) -> dict[str, object]:
    product_skus = {normalize_sku(product.sku) for product in products if product.sku}
    present = sum(
        bool(normalize_sku(target["sku"]) in product_skus) for target in targets
    )
    return {
        "present": present,
        "total": len(targets),
        "recall": round(present / len(targets), 4) if targets else None,
    }


def benchmark_index(
    encoder: Encoder,
    index_json: Path,
    requirements: list[dict[str, object]],
    golden: list[dict[str, object]],
    *,
    scope: str,
    variant: str,
    text_variants: Iterable[str] = ("image_only",),
) -> dict[str, object]:
    started = time.monotonic()
    index_payload, matrix = load_index(index_json)
    rankings_by_variant: dict[str, dict[str, list[dict[str, object]]]] = {}
    retrieval_payload: dict[str, dict[str, object]] = {}
    for text_variant in text_variants:
        variant_rankings: dict[str, list[dict[str, object]]] = {}
        for requirement in requirements:
            result = retrieve_requirement(
                encoder, index_payload, matrix, requirement, text_variant=text_variant
            )
            retrieval_payload[f"{text_variant}:{requirement.get('id')}"] = result
            variant_rankings[str(requirement.get("id"))] = list(
                result.get("results", [])
            )
        rankings_by_variant[text_variant] = variant_rankings
    targets = benchmark_targets(golden)
    rows = list(index_payload.get("rows", []))
    natural_rows = (
        [row for row in rows if row.get("scope") == "natural"]
        if scope == "oracle"
        else rows
    )
    natural_skus = {
        normalize_sku(row.get("sku")) for row in natural_rows if row.get("sku")
    }
    all_skus = {normalize_sku(row.get("sku")) for row in rows if row.get("sku")}

    def _recall_for(product_skus: set[str]) -> dict[str, dict[str, object]]:
        return {
            name: {
                "present": sum(
                    normalize_sku(target["sku"]) in product_skus for target in values
                ),
                "total": len(values),
                "recall": round(
                    sum(
                        normalize_sku(target["sku"]) in product_skus
                        for target in values
                    )
                    / len(values),
                    4,
                )
                if values
                else None,
            }
            for name, values in targets.items()
        }

    natural_recall = _recall_for(natural_skus)
    oracle_recall = _recall_for(all_skus) if scope == "oracle" else None
    metrics: dict[str, object] = {}
    per_target: list[dict[str, object]] = []
    for text_variant, variant_rankings in rankings_by_variant.items():
        metrics[text_variant] = {
            name: metric_summary(values, variant_rankings)
            for name, values in targets.items()
        }
        for name, target_list in targets.items():
            for target in target_list:
                per_target.append(
                    {
                        **target,
                        "benchmark": name,
                        "variant": text_variant,
                        "rank": _target_rank(
                            variant_rankings.get(
                                str(target["fixture_requirement"]), []
                            ),
                            str(target["sku"]),
                        ),
                    }
                )
    return {
        "status": "ready",
        "scope": scope,
        "variant": variant,
        "model": index_payload.get("model", {}),
        "index": {
            "image_rows": index_payload.get("image_rows", 0),
            "unique_images": index_payload.get("unique_images", 0),
            "embedding_dimension": index_payload.get("embedding_dimension", 0),
            "build_seconds": index_payload.get("build_seconds"),
            "images_per_second": round(
                float(index_payload.get("unique_images", 0))
                / max(float(index_payload.get("build_seconds", 0.0)), 1e-6),
                3,
            ),
        },
        "natural_visual_corpus_recall": natural_recall,
        "oracle_enriched_recall": oracle_recall,
        "primary_targets": len(targets["primary"]),
        "exploratory_targets": len(targets["exploratory"]),
        "metrics": metrics,
        "per_target": per_target,
        "retrieval": retrieval_payload,
        "benchmark_seconds": round(time.monotonic() - started, 3),
        "golden_policy": "golden is evaluation-only; SYSTEM_BOM and unmapped rows are excluded; queries use project reference crops",
        "created_at": utc_now(),
    }


def run_model_safely(load: Any, model: str) -> dict[str, object]:
    """Convert a single model failure into a payload so benchmark-all continues."""
    try:
        return {"status": "ready", "value": load()}
    except Exception as exc:  # noqa: BLE001  # model-specific failures are isolated
        return {
            "status": "failed",
            "model": model,
            "error": f"{type(exc).__name__}: {exc}",
        }
