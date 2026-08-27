"""Command line entrypoint for the isolated visual retrieval spike."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .common import (
    DEFAULT_CATALOG,
    DEFAULT_DISCOVERY,
    DEFAULT_GOLDEN,
    DEFAULT_INVENTORY,
    DEFAULT_REQUIREMENTS,
    SPIKE_DATA,
    SPIKE_OUTPUT,
    SPIKE_SUPPLIERS,
    VisualCorpusStore,
    build_natural_corpus,
    load_requirements,
)
from .encoders import MODEL_SPECS, load_encoder, model_metadata, write_model_failure
from .oracle import build_oracle_corpus
from .reports import write_benchmark_report, write_contact_sheets, write_corpus_report
from .retrieval import benchmark_index, build_embedding_index


def _path(value: str) -> Path:
    return Path(value)


def _suppliers(value: str | None) -> list[str]:
    if not value:
        return list(SPIKE_SUPPLIERS)
    wanted = {
        part.strip()
        .lower()
        .removeprefix("https://")
        .removeprefix("http://")
        .rstrip("/")
        for part in value.split(",")
        if part.strip()
    }
    return [supplier for supplier in SPIKE_SUPPLIERS if supplier in wanted]


def _index_path(model: str, variant: str, scope: str) -> Path:
    return SPIKE_DATA / "embeddings" / model / variant / scope / "index.json"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _rss_mb() -> float | None:
    try:
        import psutil

        return round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1)
    except (ImportError, OSError):
        return None


def cmd_build_corpus(args: argparse.Namespace) -> int:
    stats = build_natural_corpus(
        _path(args.inventory),
        _path(args.corpus_db) if args.corpus_db else None,
        suppliers=_suppliers(args.suppliers),
        catalog_db=_path(args.catalog),
        max_products=args.max_products,
        gallery_images=args.gallery_images,
        fresh=args.fresh,
        timeout=args.timeout,
        delay=args.delay,
        seed_only=args.seed_existing_only,
        workers=args.workers,
    )
    store = VisualCorpusStore(_path(args.corpus_db) if args.corpus_db else None)
    write_corpus_report(stats, store)
    print(json.dumps(stats, ensure_ascii=False))
    return 0


def cmd_build_oracle(args: argparse.Namespace) -> int:
    payload = build_oracle_corpus(
        _path(args.corpus_db)
        if args.corpus_db
        else SPIKE_DATA / "visual_corpus.sqlite3",
        golden_path=_path(args.golden),
        discovery_path=_path(args.discovery),
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    try:
        encoder = load_encoder(
            args.model, model_cache=_path(args.model_cache), threads=args.threads
        )
        payload = build_embedding_index(
            encoder,
            VisualCorpusStore(_path(args.corpus_db) if args.corpus_db else None),
            scope=args.scope,
            variant=args.variant,
            gallery_images=args.gallery_images,
            batch_size=args.batch_size,
        )
        payload["runtime"] = model_metadata(
            encoder, model_cache=_path(args.model_cache)
        )
        index_json = _index_path(args.model, args.variant, args.scope)
        _write_json(index_json, payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        failure = {
            "status": "failed",
            "model": args.model,
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_model_failure(
            SPIKE_OUTPUT / f"model_failure_{args.model}.json", args.model, exc
        )
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 2


def _run_benchmark(
    args: argparse.Namespace, model: str, variant: str, scope: str
) -> dict[str, object]:
    encoder = load_encoder(
        model, model_cache=_path(args.model_cache), threads=args.threads
    )
    index_json = _index_path(model, variant, scope)
    if not index_json.exists():
        raise FileNotFoundError(f"missing index; run embed first: {index_json}")
    requirements = load_requirements(_path(args.requirements))
    golden = json.loads(_path(args.golden).read_text(encoding="utf-8"))
    text_variants = ["image_only"]
    if args.include_text and encoder.supports_text:
        text_variants.extend(["visual_first_0.85", "mixed_0.70"])
    payload = benchmark_index(
        encoder,
        index_json,
        requirements,
        golden,
        scope=scope,
        variant=variant,
        text_variants=text_variants,
    )
    payload["index"]["build_seconds"] = json.loads(
        index_json.read_text(encoding="utf-8")
    ).get("build_seconds")
    payload["runtime"] = model_metadata(
        encoder, model_cache=_path(args.model_cache)
    )
    for text_variant in text_variants:
        result_map = {
            key.split(":", 1)[1]: value
            for key, value in payload["retrieval"].items()
            if key.startswith(f"{text_variant}:")
        }
        write_contact_sheets(
            result_map,
            model=model,
            variant=f"{variant}_{scope}_{text_variant}",
            output_dir=SPIKE_OUTPUT,
        )
    return payload


def cmd_benchmark(args: argparse.Namespace) -> int:
    try:
        payload = _run_benchmark(args, args.model, args.variant, args.scope)
        target = (
            SPIKE_OUTPUT / f"benchmark_{args.model}_{args.variant}_{args.scope}.json"
        )
        _write_json(target, payload)
        write_benchmark_report([payload], SPIKE_OUTPUT)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        failure = {
            "status": "failed",
            "model": args.model,
            "variant": args.variant,
            "scope": args.scope,
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_model_failure(
            SPIKE_OUTPUT
            / f"benchmark_failure_{args.model}_{args.variant}_{args.scope}.json",
            args.model,
            exc,
        )
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 2


def cmd_benchmark_all(args: argparse.Namespace) -> int:
    payloads: list[dict[str, object]] = []
    for model in args.models.split(",") if args.models else MODEL_SPECS:
        model = model.strip()
        if not model:
            continue
        try:
            index_json = _index_path(model, args.variant, args.scope)
            if args.rebuild_index or not index_json.exists():
                encoder = load_encoder(
                    model, model_cache=_path(args.model_cache), threads=args.threads
                )
                index_payload = build_embedding_index(
                    encoder,
                    VisualCorpusStore(
                        _path(args.corpus_db) if args.corpus_db else None
                    ),
                    scope=args.scope,
                    variant=args.variant,
                    gallery_images=args.gallery_images,
                    batch_size=args.batch_size,
                )
                index_payload["runtime"] = model_metadata(
                    encoder, model_cache=_path(args.model_cache)
                )
                _write_json(index_json, index_payload)
            payload = _run_benchmark(args, model, args.variant, args.scope)
            _write_json(
                SPIKE_OUTPUT / f"benchmark_{model}_{args.variant}_{args.scope}.json",
                payload,
            )
            payloads.append(payload)
            print(f"{model}: completed")
        except Exception as exc:  # noqa: BLE001
            failure = {
                "status": "failed",
                "model": model,
                "variant": args.variant,
                "scope": args.scope,
                "error": f"{type(exc).__name__}: {exc}",
            }
            payloads.append(failure)
            write_model_failure(
                SPIKE_OUTPUT / f"model_failure_{model}.json", model, exc
            )
            print(f"{model}: failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    write_benchmark_report(payloads, SPIKE_OUTPUT)
    return (
        0
        if payloads and all(payload.get("status") == "ready" for payload in payloads)
        else 2
    )


def cmd_smoke(args: argparse.Namespace) -> int:
    if args.from_catalog:
        from lumimatch.storage import CatalogStore

        products = [
            product
            for product in CatalogStore(_path(args.catalog)).all(set(SPIKE_SUPPLIERS))
            if product.local_image_path and Path(product.local_image_path).exists()
        ][: max(1, min(args.limit, 500))]
        images = [Path(str(product.local_image_path)) for product in products]
    else:
        store = VisualCorpusStore(_path(args.corpus_db) if args.corpus_db else None)
        products = store.all(scope=args.scope, ready_only=True)[
            : max(1, min(args.limit, 500))
        ]
        images = [Path(str(product.local_image_path)) for product in products]
    if not products:
        raise RuntimeError(
            "no smoke images available; build corpus or use --from-catalog"
        )
    payloads: list[dict[str, object]] = []
    for model in args.models.split(",") if args.models else MODEL_SPECS:
        started = time.monotonic()
        rss_samples = [_rss_mb()]
        try:
            encoder = load_encoder(
                model, model_cache=_path(args.model_cache), threads=args.threads
            )
            rss_samples.append(_rss_mb())
            embeddings = encoder.encode_images(images, batch_size=args.batch_size)
            rss_samples.append(_rss_mb())
            measured_rss = [value for value in rss_samples if value is not None]
            payloads.append(
                {
                    "status": "ready",
                    "model": model,
                    "images": len(images),
                    "dimension": int(embeddings.shape[1])
                    if embeddings.ndim == 2
                    else 0,
                    "seconds": round(time.monotonic() - started, 3),
                    "images_per_second": round(
                        len(images) / max(time.monotonic() - started, 1e-6), 3
                    ),
                    "rss_before_mb": rss_samples[0],
                    "rss_after_load_mb": rss_samples[1],
                    "rss_after_encode_mb": rss_samples[2],
                    "rss_peak_sampled_mb": max(measured_rss)
                    if measured_rss
                    else None,
                    "runtime": model_metadata(
                        encoder, model_cache=_path(args.model_cache)
                    ),
                }
            )
            print(f"{model}: smoke completed")
        except Exception as exc:  # noqa: BLE001
            payloads.append(
                {
                    "status": "failed",
                    "model": model,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(
                f"{model}: smoke failed: {type(exc).__name__}: {exc}", file=sys.stderr
            )
    _write_json(
        SPIKE_OUTPUT / "smoke.json", {"images": len(products), "models": payloads}
    )
    return (
        0 if payloads and all(item.get("status") == "ready" for item in payloads) else 2
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.visual_retrieval",
        description="Isolated CPU visual retrieval spike",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    corpus = commands.add_parser(
        "build-corpus", help="build/resume natural visual corpus from inventory"
    )
    corpus.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    corpus.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    corpus.add_argument("--corpus-db", default=None)
    corpus.add_argument("--suppliers", default=None)
    corpus.add_argument("--max-products", type=int, default=None)
    corpus.add_argument("--gallery-images", type=int, default=1, choices=(1, 2, 3))
    corpus.add_argument("--fresh", action="store_true")
    corpus.add_argument("--timeout", type=float, default=20.0)
    corpus.add_argument("--delay", type=float, default=0.08)
    corpus.add_argument(
        "--seed-existing-only",
        action="store_true",
        help="seed from already hydrated production images without crawling",
    )
    corpus.add_argument("--workers", type=int, default=4, choices=tuple(range(1, 9)))
    corpus.set_defaults(func=cmd_build_corpus)

    oracle = commands.add_parser(
        "build-oracle", help="build evaluation-only target enrichment"
    )
    oracle.add_argument("--corpus-db", default=None)
    oracle.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    oracle.add_argument("--discovery", default=str(DEFAULT_DISCOVERY))
    oracle.set_defaults(func=cmd_build_oracle)

    def add_model_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--model", choices=sorted(MODEL_SPECS))
        command.add_argument("--model-cache", default=str(SPIKE_DATA / "model_cache"))
        command.add_argument("--corpus-db", default=None)
        command.add_argument(
            "--scope", choices=("natural", "oracle"), default="natural"
        )
        command.add_argument(
            "--variant", choices=("primary", "gallery-3"), default="primary"
        )
        command.add_argument("--gallery-images", type=int, default=3, choices=(1, 2, 3))
        command.add_argument("--batch-size", type=int, default=16)
        command.add_argument("--threads", type=int, default=4)

    embed = commands.add_parser("embed", help="encode corpus images with one model")
    add_model_options(embed)
    embed.set_defaults(func=cmd_embed)

    benchmark = commands.add_parser(
        "benchmark", help="rank all project reference crops and evaluate after ranking"
    )
    add_model_options(benchmark)
    benchmark.add_argument("--requirements", default=str(DEFAULT_REQUIREMENTS))
    benchmark.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    benchmark.add_argument("--include-text", action="store_true")
    benchmark.set_defaults(func=cmd_benchmark)

    all_models = commands.add_parser(
        "benchmark-all", help="run all model baselines; model failures are isolated"
    )
    all_models.add_argument(
        "--models",
        default=None,
        help="comma-separated model names; defaults to all four",
    )
    all_models.add_argument("--model-cache", default=str(SPIKE_DATA / "model_cache"))
    all_models.add_argument("--corpus-db", default=None)
    all_models.add_argument("--scope", choices=("natural", "oracle"), default="natural")
    all_models.add_argument(
        "--variant", choices=("primary", "gallery-3"), default="primary"
    )
    all_models.add_argument("--gallery-images", type=int, default=3, choices=(1, 2, 3))
    all_models.add_argument("--batch-size", type=int, default=16)
    all_models.add_argument("--threads", type=int, default=4)
    all_models.add_argument("--requirements", default=str(DEFAULT_REQUIREMENTS))
    all_models.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    all_models.add_argument("--include-text", action="store_true")
    all_models.add_argument("--rebuild-index", action="store_true")
    all_models.set_defaults(func=cmd_benchmark_all)

    smoke = commands.add_parser(
        "smoke", help="load/encode a bounded sample before long indexing"
    )
    smoke.add_argument("--models", default=None)
    smoke.add_argument("--model-cache", default=str(SPIKE_DATA / "model_cache"))
    smoke.add_argument("--corpus-db", default=None)
    smoke.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    smoke.add_argument(
        "--from-catalog",
        action="store_true",
        help="use existing production catalog images only for bounded smoke",
    )
    smoke.add_argument("--scope", choices=("natural", "oracle"), default="natural")
    smoke.add_argument("--limit", type=int, default=250)
    smoke.add_argument("--batch-size", type=int, default=16)
    smoke.add_argument("--threads", type=int, default=4)
    smoke.set_defaults(func=cmd_smoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
