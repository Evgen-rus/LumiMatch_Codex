"""Bounded post-baseline diagnostics; never writes production artifacts."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from .controlled import (
    OUTPUT, DATA, MODEL_CACHE, TARGETS, _encode_paths, _rank,
    _write_blind_sheet, _write_json, sha256_file, input_fingerprints,
)
from .encoders import load_encoder, model_metadata, write_model_failure


def rerank(sources: list[str]) -> dict:
    """Sources are chosen before label reveal; no positive identity is read."""
    started = time.monotonic()
    try:
        encoder = load_encoder("dreamsim_ensemble", model_cache=MODEL_CACHE, threads=4)
        manifest = json.loads((OUTPUT / "queries/manifest.json").read_text(encoding="utf-8"))
        fingerprints = input_fingerprints()
        results = {}
        for source in sources:
            baseline = json.loads((OUTPUT / "sealed" / f"{source}.json").read_text(encoding="utf-8"))
            if baseline.get("input_fingerprints") != fingerprints:
                raise RuntimeError(f"Baseline must be refreshed before reranking: {source}")
            targets = {}
            for target in TARGETS:
                base = baseline["targets"][target]["rankings"]["max"]
                pool = base[:50]
                paths = [Path(item["image"]) for item in pool]
                matrix = _encode_paths(encoder, paths, batch_size=2)
                query_paths = [Path(item["path"]) for item in manifest if item["requirement_id"] == target]
                queries = _encode_paths(encoder, query_paths, batch_size=1)
                rankings = {mode: _rank(pool, matrix, queries, mode) for mode in ("max", "mean")}
                name = f"{source}__dreamsim"
                _write_blind_sheet(target, name, rankings["max"], OUTPUT / "review" / name / f"{target}_top20.jpg")
                targets[target] = {"pool_size": len(pool), "rankings": rankings, "baseline_top50": base[:50]}
                print(f"DreamSim {source} {target}: {len(pool)} candidates done", flush=True)
            result = {"status": "ready", "model": name, "source_model": source,
                      "runtime": model_metadata(encoder, model_cache=MODEL_CACHE), "targets": targets,
                      "pool_fingerprints": baseline["pool_fingerprints"],
                      "input_fingerprints": fingerprints,
                      "source_fingerprint": sha256_file(OUTPUT / "sealed" / f"{source}.json")}
            result["runtime"]["total_seconds"] = round(time.monotonic() - started, 3)
            result["runtime"]["embedding_dimension"] = int(queries.shape[1])
            _write_json(OUTPUT / "sealed" / f"{name}.json", result)
            results[source] = "ready"
        return results
    except Exception as exc:
        write_model_failure(OUTPUT / "failures/dreamsim_ensemble.json", "dreamsim_ensemble", exc)
        return {"status": "failed", "error": str(exc)}


def performance(model: str) -> dict:
    """Measure warmed inference explicitly, without embedding-cache hits."""
    import psutil
    encoder = load_encoder(model, model_cache=MODEL_CACHE, threads=4)
    manifest = json.loads((OUTPUT / "queries/manifest.json").read_text(encoding="utf-8"))
    paths = [Path(item["path"]) for item in manifest]
    encoder.encode_images(paths[:1], batch_size=1)
    latencies = []
    for path in paths:
        start = time.monotonic()
        vector = encoder.encode_images([path], batch_size=1)
        latencies.append(time.monotonic() - start)
    cache = DATA / "embeddings" / model
    result = model_metadata(encoder, model_cache=MODEL_CACHE)
    result.update(query_latency_seconds_median=float(np.median(latencies)),
                  sec_per_image=float(np.mean(latencies)), embedding_dimension=vector.shape[1],
                  rss_mb=psutil.Process().memory_info().rss / 1024**2,
                  embedding_cache_mb=sum(p.stat().st_size for p in cache.rglob("*.npy")) / 1024**2,
                  cache_images=len(list(cache.rglob("*.npy"))))
    _write_json(OUTPUT / "performance" / f"{model}.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["dreamsim", "performance"])
    parser.add_argument("--sources", nargs="+", default=["dinov2_vits14", "siglip2_base_patch16_224"])
    parser.add_argument("--model", default="siglip2_base_patch16_224")
    args = parser.parse_args()
    result = rerank(args.sources) if args.command == "dreamsim" else performance(args.model)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
