"""Machine-readable reports and Codex-friendly contact sheets."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .common import SPIKE_OUTPUT, SPIKE_SUPPLIERS, VisualCorpusStore, utc_now


def write_corpus_report(
    stats: dict[str, object], store: VisualCorpusStore, output_dir: Path = SPIKE_OUTPUT
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    products = store.all(scope="natural")
    status_counts: dict[str, int] = {}
    ready_by_supplier: dict[str, int] = {}
    for product in products:
        status_counts[product.status] = status_counts.get(product.status, 0) + 1
        if product.status == "ready":
            ready_by_supplier[product.supplier] = (
                ready_by_supplier.get(product.supplier, 0) + 1
            )
    corpus_totals = {
        "products": len(products),
        "ready_products": status_counts.get("ready", 0),
        "status_counts": status_counts,
        "ready_by_supplier": ready_by_supplier,
    }
    payload = {
        **stats,
        "corpus_totals": corpus_totals,
        "products": [product.as_dict() for product in products],
    }
    (output_dir / "corpus.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Visual retrieval spike corpus",
        "",
        "Natural corpus is selected from the production URL inventory for the five configured suppliers. Golden data is not read during selection.",
        "",
        f"- Inventory URLs: {stats.get('inventory_urls', 0)}",
        f"- Ready product images in cumulative corpus: {corpus_totals['ready_products']}",
        f"- Cumulative product statuses: {json.dumps(status_counts, ensure_ascii=False)}",
        f"- Last run pages attempted/successful: {stats.get('pages_attempted', 0)}/{stats.get('pages_successful', 0)}",
        f"- Product images found: {stats.get('product_images_found', 0)}",
        f"- Images downloaded/reused: {stats.get('images_downloaded', 0)}/{stats.get('images_reused', 0)}",
        f"- Failed: {stats.get('failed', 0)}",
        f"- Elapsed: {stats.get('elapsed_seconds', 0)} sec",
        "",
        "| supplier | cumulative ready | last run inventory URLs | last run failed |",
        "|---|---:|---:|---:|",
    ]
    per_supplier = stats.get("per_supplier", {})
    per_supplier_values = per_supplier if isinstance(per_supplier, dict) else {}
    suppliers = set(SPIKE_SUPPLIERS) | set(ready_by_supplier) | set(per_supplier_values)
    for supplier in sorted(suppliers):
        values = per_supplier_values.get(supplier, {})
        if not isinstance(values, dict):
            values = {}
        lines.append(
            f"| {supplier} | {ready_by_supplier.get(supplier, 0)} | {values.get('inventory_urls', 0)} | {values.get('failed', 0)} |"
        )
    lines.extend(
        [
            "",
            "Each image is stored under data/visual_spike/images/ by content hash. The isolated image_products table preserves image-to-product associations.",
            "",
        ]
    )
    (output_dir / "corpus.md").write_text("\n".join(lines), encoding="utf-8")


def _font() -> object:
    try:
        from PIL import ImageFont

        return ImageFont.truetype("arial.ttf", 13)
    except OSError:
        from PIL import ImageFont

        return ImageFont.load_default()


def write_contact_sheets(
    results: dict[str, object],
    *,
    model: str,
    variant: str,
    output_dir: Path = SPIKE_OUTPUT,
    limit: int = 20,
) -> list[str]:
    """Create one labelled Top-K sheet per FixtureRequirement."""
    review_dir = output_dir / "review" / model / variant
    review_dir.mkdir(parents=True, exist_ok=True)
    font = _font()
    paths: list[str] = []
    for requirement_id, value in sorted(results.items()):
        if not isinstance(value, dict):
            continue
        candidates = list(value.get("results", []))[:limit]
        if not candidates:
            continue
        columns, tile_width, image_height, text_height = 5, 220, 180, 58
        rows = (len(candidates) + columns - 1) // columns
        sheet = Image.new(
            "RGB", (columns * tile_width, rows * (image_height + text_height)), "white"
        )
        draw = ImageDraw.Draw(sheet)
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                continue
            left = (index % columns) * tile_width
            top = (index // columns) * (image_height + text_height)
            image_path = Path(str(candidate.get("local_image_path") or ""))
            try:
                with Image.open(image_path) as image:
                    thumbnail = ImageOps.contain(
                        image.convert("RGB"), (tile_width - 8, image_height - 8)
                    )
                    sheet.paste(
                        thumbnail,
                        (
                            left + (tile_width - thumbnail.width) // 2,
                            top + (image_height - thumbnail.height) // 2,
                        ),
                    )
            except (OSError, ValueError):
                draw.rectangle(
                    (left + 4, top + 4, left + tile_width - 4, top + image_height - 4),
                    outline="red",
                    width=2,
                )
                draw.text(
                    (left + 10, top + image_height // 2),
                    "image unavailable",
                    fill="red",
                    font=font,
                )
            sku = str(candidate.get("sku") or "no-sku")
            supplier = str(candidate.get("supplier") or "")
            score = float(candidate.get("score", 0.0))
            draw.text(
                (left + 5, top + image_height + 3),
                f"#{candidate.get('rank')} {score:.3f} {sku[:24]}",
                fill="black",
                font=font,
            )
            draw.text(
                (left + 5, top + image_height + 22),
                supplier[:29],
                fill="black",
                font=font,
            )
            draw.text(
                (left + 5, top + image_height + 39),
                str(candidate.get("title") or "")[:28],
                fill="black",
                font=font,
            )
        target = review_dir / f"{requirement_id}_top{limit}.jpg"
        sheet.save(target, quality=91)
        paths.append(str(target))
        manifest = {
            "model": model,
            "variant": variant,
            "requirement_id": requirement_id,
            "query_paths": value.get("query_paths", []),
            "candidates": candidates,
            "qualitative_status": "pending_codex_review",
        }
        (review_dir / f"{requirement_id}_top{limit}.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return paths


def _metric(payload: dict[str, object], variant: str, name: str, key: str) -> object:
    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        return None
    by_variant = metrics.get(variant, {})
    if not isinstance(by_variant, dict):
        return None
    group = by_variant.get(name, {})
    return group.get(key) if isinstance(group, dict) else None


def write_benchmark_report(
    payloads: list[dict[str, object]], output_dir: Path = SPIKE_OUTPUT
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    review_path = output_dir / "review" / "qualitative_review.json"
    qualitative_review: dict[str, object] | None = None
    if review_path.exists():
        try:
            loaded_review = json.loads(review_path.read_text(encoding="utf-8"))
            if isinstance(loaded_review, dict):
                qualitative_review = loaded_review
        except (OSError, ValueError):
            qualitative_review = None
    compact_runs: list[dict[str, object]] = []
    for payload in payloads:
        compact = dict(payload)
        retrieval = payload.get("retrieval")
        if isinstance(retrieval, dict):
            compact_retrieval: dict[str, object] = {}
            for key, value in retrieval.items():
                if not isinstance(value, dict):
                    compact_retrieval[key] = value
                    continue
                compact_result = dict(value)
                results = value.get("results")
                if isinstance(results, list):
                    compact_result["results"] = results[:100]
                compact_retrieval[key] = compact_result
            compact["retrieval"] = compact_retrieval
            compact["retrieval_note"] = "Aggregate report retains Top-100 per F/model/variant; full rankings are in per-run benchmark_*.json files."
        compact_runs.append(compact)
    final = {
        "status": "ready",
        "generated_at": utc_now(),
        "runs": compact_runs,
        "qualitative_review": qualitative_review,
    }
    (output_dir / "benchmark.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Visual retrieval spike benchmark",
        "",
        "This report evaluates image-to-image retrieval only. Golden mappings are consulted after ranking; SYSTEM_BOM, unmapped rows and low-confidence rows are excluded from PRIMARY metrics.",
        "",
        "## Model comparison",
        "",
        "| model | variant | scope | primary R@10 | R@20 | R@50 | R@100 | MRR | build sec | benchmark sec |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for payload in payloads:
        if payload.get("status") != "ready":
            model = payload.get("model", "unknown")
            lines.append(
                f"| {model} | - | - | failed | failed | failed | failed | failed | - | - |"
            )
            continue
        model = payload.get("model", {})
        model_name = (
            model.get("model", "unknown") if isinstance(model, dict) else "unknown"
        )
        lines.append(
            f"| {model_name} | {payload.get('variant')} | {payload.get('scope')} | {_metric(payload, 'image_only', 'primary', 'recall_at_10')} | {_metric(payload, 'image_only', 'primary', 'recall_at_20')} | {_metric(payload, 'image_only', 'primary', 'recall_at_50')} | {_metric(payload, 'image_only', 'primary', 'recall_at_100')} | {_metric(payload, 'image_only', 'primary', 'mrr')} | {payload.get('index', {}).get('build_seconds', '')} | {payload.get('benchmark_seconds', '')} |"
        )
    lines.extend(
        [
            "",
            "## Natural corpus recall",
            "",
            "| model | scope | primary present/total | exploratory present/total | image rows | dimensions |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for payload in payloads:
        if payload.get("status") != "ready":
            continue
        recall = payload.get("natural_visual_corpus_recall", {})
        primary = recall.get("primary", {}) if isinstance(recall, dict) else {}
        exploratory = recall.get("exploratory", {}) if isinstance(recall, dict) else {}
        index = payload.get("index", {})
        model = payload.get("model", {})
        lines.append(
            f"| {model.get('model', 'unknown') if isinstance(model, dict) else 'unknown'} | {payload.get('scope')} | {primary.get('present', 0)}/{primary.get('total', 0)} | {exploratory.get('present', 0)}/{exploratory.get('total', 0)} | {index.get('image_rows', 0)} | {index.get('embedding_dimension', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Individual golden ranks",
            "",
            "| benchmark | F | golden SKU | supplier | confidence | variant | rank |",
            "|---|---|---|---|---:|---|---:|",
        ]
    )
    for payload in payloads:
        for item in (
            payload.get("per_target", [])
            if isinstance(payload.get("per_target"), list)
            else []
        ):
            lines.append(
                f"| {item.get('benchmark')} | {item.get('fixture_requirement')} | {item.get('sku')} | {item.get('supplier') or ''} | {item.get('confidence')} | {item.get('variant')} | {item.get('rank') or ''} |"
            )
    lines.extend(
        [
            "",
            "## Qualitative review",
            "",
            "Top-20 sheets are under output/visual_spike/review/<model>/<variant>/. Golden SKU rank is not treated as a visual positive.",
            (
                f"Manual Codex review: {qualitative_review.get('decision')}"
                if qualitative_review
                else "Manual Codex review: pending"
            ),
            "",
            "## Integrity",
            "",
            "- Natural corpus selection reads only the selected production inventory and never reads golden data.",
            "- Query paths come from FixtureRequirement.reference_crop_paths; expected_kp.docx and golden assets are rejected.",
            "- Oracle-enriched rows live in the separate oracle scope and are never added to natural.",
            "- A model failure is recorded as a failed run and does not cancel other model runs.",
            "",
        ]
    )
    (output_dir / "benchmark.md").write_text("\n".join(lines), encoding="utf-8")
    return final
