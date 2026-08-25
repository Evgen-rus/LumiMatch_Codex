"""Golden benchmark reports kept independent from production ranking."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .models import FixtureRequirement
from .scoring import candidate_set_fingerprint, wide_candidate_pool
from .storage import CatalogStore
from .visual_review import build_contact_sheets

FRESH_REVIEW_ENTRIES: dict[str, dict[str, dict[str, object]]] = {
    "F-01": {
        "CL227011": {"decision": "accept", "visual_similarity": 0.84, "reason": "тонкий чёрный цилиндрический подвес; близкая геометрия"},
        "a040264": {"decision": "accept", "visual_similarity": 0.94, "reason": "чёрный компактный цилиндрический подвес; наиболее близкий визуальный аналог"},
        "CL331111": {"decision": "reject", "visual_similarity": 0.08, "reason": "хрусталь и клетчатая люстра, не цилиндрический современный подвес"},
        "CL444210": {"decision": "reject", "visual_similarity": 0.12, "reason": "витражная классическая форма"},
        "LSP-4016": {"decision": "reject", "visual_similarity": 0.28, "reason": "группа колец/декоративная форма вместо компактного цилиндра"},
    },
    "F-03": {
        "FR2066WL-L40B": {"decision": "accept", "visual_similarity": 0.96, "reason": "компактное бра с тёмным основанием и светлым абажуром; соответствует bedside reference"},
        "2207B,19": {"decision": "reject", "visual_similarity": 0.36, "reason": "ветвящаяся архитектурная форма без светлого локального абажура"},
        "LSP-7187": {"decision": "reject", "visual_similarity": 0.43, "reason": "вертикальная световая петля относится к другой декоративной геометрии"},
        "CL352321": {"decision": "reject", "visual_similarity": 0.05, "reason": "классическая хрустальная люстра"},
    },
    "F-04": {
        "LSP-7187": {"decision": "accept", "visual_similarity": 0.90, "reason": "вертикальный светящийся контур с тёмной центральной частью; близко к reference"},
        "FR2066WL-L40B": {"decision": "reject", "visual_similarity": 0.45, "reason": "абажурное прикроватное бра, нет овального светящегося контура"},
        "CL352321": {"decision": "reject", "visual_similarity": 0.05, "reason": "хрустальная классика"},
        "CL704071": {"decision": "reject", "visual_similarity": 0.39, "reason": "горизонтальный/угловой корпус, не вертикальный контур"},
    },
    "F-05": {
        "LSP-4001": {"decision": "accept", "visual_similarity": 0.78, "reason": "тонкая вертикальная подсветка стены; визуально подходит, но IP/влажная зона не доказаны"},
        "CL330312": {"decision": "reject", "visual_similarity": 0.04, "reason": "хрустальный декоративный светильник вместо mirror-light"},
        "CL704071": {"decision": "reject", "visual_similarity": 0.34, "reason": "корпус не подтверждает подсветку зеркала и не имеет IP"},
    },
    "F-06": {
        "208517": {"decision": "reject", "visual_similarity": 0.08, "reason": "круглый белый шар; не узкий чёрный цилиндрический спот"},
        "080942": {"decision": "reject", "visual_similarity": 0.25, "reason": "крупный круглый многосветный накладной прибор"},
        "225530": {"decision": "reject", "visual_similarity": 0.06, "reason": "плоская круглая декоративная панель"},
    },
}


def _sku_key(value: str | None) -> str:
    return "".join(character.casefold() for character in (value or "") if character.isalnum())


def _fresh_review(requirement_id: str, sku: str | None) -> dict[str, object]:
    reviews = FRESH_REVIEW_ENTRIES.get(requirement_id, {})
    if sku in reviews:
        return reviews[sku]
    target = _sku_key(sku)
    if not target:
        return {}
    for review_sku, review in reviews.items():
        if _sku_key(review_sku) == target:
            return review
    return {}


def _find_product(store: CatalogStore, discovery: dict[str, object]) -> object | None:
    products = store.all()
    target_sku = _sku_key(str(discovery.get("sku") or ""))
    url = str(discovery.get("url") or "")
    for product in products:
        if url and product.canonical_url == url:
            return product
        if target_sku and _sku_key(product.sku) == target_sku:
            return product
    return None


def _rank(pool: list[object], product: object | None) -> int | None:
    if not product:
        return None
    target = (_sku_key(getattr(product, "sku", None)), getattr(product, "canonical_url", ""))
    for index, candidate in enumerate(pool, start=1):
        current = (_sku_key(candidate.product.sku), candidate.product.canonical_url)
        if target == current:
            return index
    return None


def _fresh_review_manifest(requirements: list[FixtureRequirement], pools: dict[str, list[object]], output_dir: Path) -> dict[str, object]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest: dict[str, object] = {"run_id": run_id, "generated_at": datetime.now(timezone.utc).isoformat(), "requirements": {}}
    for requirement in requirements:
        pool = pools.get(requirement.id, [])
        build_contact_sheets(requirement, pool, output_dir / "review")
        manifest["requirements"][requirement.id] = {
            "candidate_set_fingerprint": candidate_set_fingerprint(pool),
            "candidate_count": len(pool),
            "reviews": {
                candidate.product.sku: _fresh_review(requirement.id, candidate.product.sku)
                for candidate in pool
                if _fresh_review(requirement.id, candidate.product.sku)
            },
            "golden_target_reviews": FRESH_REVIEW_ENTRIES.get(requirement.id, {}),
        }
    return manifest


def run_benchmark(
    golden_items: list[dict[str, object]],
    discovery_items: list[dict[str, object]],
    requirements: list[FixtureRequirement],
    store: CatalogStore,
    output_dir: Path,
) -> dict[str, object]:
    requirement_by_id = {requirement.id: requirement for requirement in requirements}
    discovery_by_position = {int(item["kp_position"]): item for item in discovery_items}
    visual_pools: dict[str, list[object]] = {}
    visual_targets: list[dict[str, object]] = []
    system_items: list[dict[str, object]] = []
    for item in golden_items:
        discovery = discovery_by_position.get(int(item["kp_position"]), {})
        target = _find_product(store, discovery) if discovery.get("found") else None
        role = item.get("product_role")
        if role == "SYSTEM_BOM":
            system_items.append(
                {
                    "kp_position": item.get("kp_position"),
                    "sku": item.get("sku"),
                    "category": item.get("golden_category"),
                    "discovered": bool(discovery.get("discovered")),
                    "parsed": bool(discovery.get("parser_success")),
                    "found": bool(discovery.get("found")),
                    "photo": bool(discovery.get("photo")),
                    "supplier": discovery.get("supplier"),
                    "url": discovery.get("url"),
                }
            )
            continue
        requirement_id = item.get("matched_fixture_requirement")
        requirement = requirement_by_id.get(str(requirement_id)) if requirement_id else None
        if not requirement:
            visual_targets.append(
                {
                    "kp_position": item.get("kp_position"),
                    "sku": item.get("sku"),
                    "name": item.get("name"),
                    "status": "no_requirement_mapping",
                    "discovery_found": bool(discovery.get("found")),
                }
            )
            continue
        if requirement.id not in visual_pools:
            visual_pools[requirement.id] = wide_candidate_pool(
                requirement,
                store.all(),
                limit=100,
                include_color_alternatives=True,
                availability_policy="ignore",
            )
        independent_pool = visual_pools[requirement.id]
        production_pool = wide_candidate_pool(
            requirement,
            store.all(),
            limit=100,
            include_color_alternatives=True,
            availability_policy="sellable",
        )
        independent_rank = _rank(independent_pool, target)
        production_rank = _rank(production_pool, target)
        review = _fresh_review(requirement.id, str(item.get("sku") or ""))
        fresh_review_status = review.get("decision") if review else "не проверено"
        visual_approved = bool(discovery.get("found")) and fresh_review_status == "accept"
        visual_targets.append(
            {
                "kp_position": item.get("kp_position"),
                "sku": item.get("sku"),
                "name": item.get("name"),
                "requirement_id": requirement.id,
                "match_confidence": item.get("match_confidence"),
                "discovery_found": bool(discovery.get("found")),
                "discovery_match_type": discovery.get("match_type"),
                "supplier": discovery.get("supplier"),
                "url": discovery.get("url"),
                "availability_status": discovery.get("availability_status"),
                "availability_gate": "passed" if production_rank else "not_in_sellable_pool",
                "independent_retrieval_rank": independent_rank,
                "production_retrieval_rank": production_rank,
                "visual_approved_from_golden_source": visual_approved,
                "fresh_visual_review_status": fresh_review_status,
                "fresh_visual_review_reason": review.get("reason"),
                "visual_at_1": bool(visual_approved and independent_rank and independent_rank <= 1),
                "visual_at_3": bool(visual_approved and independent_rank and independent_rank <= 3),
                "visual_at_5": bool(visual_approved and independent_rank and independent_rank <= 5),
                "visual_at_10": bool(visual_approved and independent_rank and independent_rank <= 10),
                "candidate_set_fingerprint": candidate_set_fingerprint(independent_pool),
                "diagnosis": (
                    "not_discovered"
                    if not discovery.get("found")
                    else "retrieval_or_hard_gate_failure"
                    if independent_rank is None
                    else "availability_gate_only"
                    if production_rank is None
                    else "retrieved"
                ),
            }
        )
    review_manifest = _fresh_review_manifest(requirements, visual_pools, output_dir)
    (output_dir / "visual_review_manifest.json").write_text(json.dumps(review_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    visual_counts = {
        metric: sum(bool(item.get(metric)) for item in visual_targets)
        for metric in ("visual_at_1", "visual_at_3", "visual_at_5", "visual_at_10")
    }
    retrieval_counts = {
        f"retrieval_at_{limit}": sum(
            bool(item.get("independent_retrieval_rank"))
            and int(item["independent_retrieval_rank"]) <= limit
            for item in visual_targets
        )
        for limit in (20, 50, 100)
    }
    by_requirement: dict[str, dict[str, object]] = defaultdict(lambda: {"targets": 0, "found": 0, "retrieved": 0, "availability_gate_only": 0, "not_discovered": 0, **{f"retrieval_at_{limit}": 0 for limit in (20, 50, 100)}, "visual_at_1": 0, "visual_at_3": 0, "visual_at_5": 0, "visual_at_10": 0})
    for item in visual_targets:
        if not item.get("requirement_id"):
            continue
        stats = by_requirement[str(item["requirement_id"])]
        stats["targets"] += 1
        stats["found"] += int(bool(item.get("discovery_found")))
        stats["retrieved"] += int(item.get("independent_retrieval_rank") is not None)
        stats["availability_gate_only"] += int(item.get("diagnosis") == "availability_gate_only")
        stats["not_discovered"] += int(item.get("diagnosis") == "not_discovered")
        for limit in (20, 50, 100):
            rank = item.get("independent_retrieval_rank")
            stats[f"retrieval_at_{limit}"] += int(rank is not None and rank <= limit)
        for metric in visual_counts:
            stats[metric] += int(bool(item.get(metric)))
    bom_summary = {
        "items": len(system_items),
        "discovered": sum(bool(item.get("discovered")) for item in system_items),
        "parsed": sum(bool(item.get("parsed")) for item in system_items),
        "found": sum(bool(item.get("found")) for item in system_items),
        "photo": sum(bool(item.get("photo")) for item in system_items),
        "decorative_visual_metrics_excluded": True,
        "items_by_category": {
            category: sum(item.get("category") == category for item in system_items)
            for category in sorted({str(item.get("category")) for item in system_items})
        },
    }
    supplier_targets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in discovery_items:
        if item.get("supplier"):
            supplier_targets[str(item["supplier"])].append(item)
    supplier_coverage = []
    for supplier, items in sorted(supplier_targets.items()):
        discovered = sum(bool(item.get("discovered")) for item in items)
        parsed = sum(bool(item.get("parser_success")) for item in items)
        found = sum(bool(item.get("found")) for item in items)
        state = "healthy" if found and parsed == discovered else "partial" if parsed else "broken"
        supplier_coverage.append({"supplier": supplier, "golden_targets": len(items), "discovered": discovered, "parsed": parsed, "found": found, "coverage_state": state})
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_source": "samples/golden/dan/expected_kp.docx",
        "golden_items": len(golden_items),
        "visual_selection_items": sum(item.get("product_role") == "VISUAL_SELECTION" for item in golden_items),
        "system_bom_items": sum(item.get("product_role") == "SYSTEM_BOM" for item in golden_items),
        "discovery": {
            "sku_items": sum(bool(item.get("sku")) for item in golden_items),
            "found": sum(bool(item.get("found")) for item in discovery_items),
            "exact_or_page_label_found": sum(bool(item.get("found")) and item.get("match_type") in {"exact_sku", "page_label"} for item in discovery_items),
            "parsed": sum(bool(item.get("parser_success")) for item in discovery_items),
            "photo": sum(bool(item.get("photo")) for item in discovery_items),
        },
        "retrieval": {"visual_targets": visual_targets, "by_requirement": dict(by_requirement), "retrieval_at": retrieval_counts, "visual_at": visual_counts},
        "system_bom_coverage": bom_summary,
        "supplier_coverage": supplier_coverage,
        "fresh_review": {"run_id": review_manifest["run_id"], "manifest": "output/golden/dan/visual_review_manifest.json", "stale_review_rejected": True},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "benchmark.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(payload, output_dir / "benchmark.md")
    return payload


def _write_markdown(payload: dict[str, object], path: Path) -> None:
    lines = [
        "# Golden benchmark — Dan",
        "",
        f"Generated: `{payload['generated_at']}`. Golden source is evaluation-only; it does not alter production scores.",
        "",
        "## Summary",
        "",
        f"- VISUAL_SELECTION: `{payload['visual_selection_items']}`; SYSTEM_BOM: `{payload['system_bom_items']}`.",
        f"- Discovery found: `{payload['discovery']['found']}`; exact/page-label SKU evidence: `{payload['discovery']['exact_or_page_label_found']}`; parsed: `{payload['discovery']['parsed']}`; with photo: `{payload['discovery']['photo']}`.",
        f"- Retrieval: `retrieval@20={payload['retrieval']['retrieval_at']['retrieval_at_20']}`, `retrieval@50={payload['retrieval']['retrieval_at']['retrieval_at_50']}`, `retrieval@100={payload['retrieval']['retrieval_at']['retrieval_at_100']}`; fresh visual: `visual@1={payload['retrieval']['visual_at']['visual_at_1']}`, `visual@3={payload['retrieval']['visual_at']['visual_at_3']}`, `visual@5={payload['retrieval']['visual_at']['visual_at_5']}`, `visual@10={payload['retrieval']['visual_at']['visual_at_10']}`.",
        "",
        "## Visual retrieval",
        "",
        "| F | target | supplier | independent rank | production rank | visual@1 | visual@3 | visual@5 | visual@10 | diagnosis |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in payload["retrieval"]["visual_targets"]:
        values = {key: "" if item.get(key) is None else item.get(key) for key in ("requirement_id", "sku", "supplier", "independent_retrieval_rank", "production_retrieval_rank", "visual_at_1", "visual_at_3", "visual_at_5", "visual_at_10", "diagnosis")}
        lines.append("| {requirement_id} | {sku} | {supplier} | {independent_retrieval_rank} | {production_retrieval_rank} | {visual_at_1} | {visual_at_3} | {visual_at_5} | {visual_at_10} | {diagnosis} |".format(**values))
    lines.extend(["", "## System BOM coverage", "", f"`{json.dumps(payload['system_bom_coverage'], ensure_ascii=False)}`", "", "SYSTEM_BOM items are excluded from decorative visual metrics.", "", "## Supplier golden coverage", "", "| supplier | targets | discovered | parsed | found | state |", "|---|---:|---:|---:|---:|---|"])
    for item in payload["supplier_coverage"]:
        lines.append(f"| {item['supplier']} | {item['golden_targets']} | {item['discovered']} | {item['parsed']} | {item['found']} | {item['coverage_state']} |")
    lines.extend(["", "## Review integrity", "", "Fresh contact sheets and fingerprints are under `output/golden/dan/review/`. A review from a previous candidate pool is not treated as current; a new SKU without a fresh review is not automatically rejected.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
