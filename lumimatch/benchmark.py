"""Golden benchmark reports kept independent from production ranking."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .availability import (
    UNAVAILABLE_VISUAL_STATUSES,
    effective_availability_status,
    explicit_discontinued_availability,
)
from .models import FixtureRequirement
from .scoring import candidate_set_fingerprint, wide_candidate_pool
from .storage import CatalogStore
from .visual_review import build_contact_sheets


def _sku_key(value: str | None) -> str:
    return "".join(character.casefold() for character in (value or "") if character.isalnum())


def _fresh_review(requirement_id: str, sku: str | None) -> dict[str, object]:
    """Compatibility shim for the superseded implementation below."""
    return {}


def _fresh_review_manifest(requirements: list[FixtureRequirement], pools: dict[str, list[object]], output_dir: Path) -> dict[str, object]:
    """Compatibility shim; current code uses prepare_actual_visual_review."""
    return {"run_id": "legacy_disabled", "requirements": {}}


def _find_product_by_sku(store: CatalogStore, sku: str | None) -> object | None:
    target_sku = _sku_key(sku)
    if not target_sku:
        return None
    return next(
        (product for product in store.all() if _sku_key(product.sku) == target_sku),
        None,
    )


def _rank(pool: list[object], product: object | None) -> int | None:
    if not product:
        return None
    target = (_sku_key(getattr(product, "sku", None)), getattr(product, "canonical_url", ""))
    for index, candidate in enumerate(pool, start=1):
        current = (_sku_key(candidate.product.sku), candidate.product.canonical_url)
        if target == current:
            return index
    return None


def _visual_pool(requirement: FixtureRequirement, products: list[object], limit: int = 100) -> list[object]:
    """Relax only availability for diagnostics; keep every other hard gate."""
    broad = wide_candidate_pool(
        requirement,
        products,
        limit=limit,
        include_color_alternatives=True,
        availability_policy="ignore",
    )
    return [
        candidate
        for candidate in broad
        if (
            effective_availability_status(candidate.product) == "in_stock"
            or effective_availability_status(candidate.product) in UNAVAILABLE_VISUAL_STATUSES
        )
        and not explicit_discontinued_availability(candidate.product)
    ]


def prepare_actual_visual_review(
    requirements: list[FixtureRequirement],
    store: CatalogStore,
    output_dir: Path,
    *,
    limit: int = 100,
) -> dict[str, object]:
    """Write current contact sheets and a pending, run-specific review file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest: dict[str, object] = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_type": "actual_codex_visual_review",
        "instructions": "Откройте текущие contact sheets и заполните decision/reason; accepted candidates получают visual_rank.",
        "requirements": {},
    }
    products = store.all()
    for requirement in requirements:
        pool = _visual_pool(requirement, products, limit=limit)
        build_contact_sheets(requirement, pool, output_dir / "review")
        manifest["requirements"][requirement.id] = {
            "candidate_set_fingerprint": candidate_set_fingerprint(pool),
            "candidate_count": len(pool),
            "contact_sheet_dir": str((output_dir / "review" / requirement.id).as_posix()),
            "candidates": [
                {
                    "candidate_rank": index,
                    "supplier": candidate.product.supplier,
                    "sku": candidate.product.sku,
                    "name": candidate.product.name,
                    "canonical_url": candidate.product.canonical_url,
                    "source_url": candidate.product.source_url,
                    "local_image_path": candidate.product.local_image_path,
                    "availability_status": candidate.product.availability_status,
                    "decision": "pending",
                    "visual_rank": None,
                    "reason": None,
                }
                for index, candidate in enumerate(pool, start=1)
            ],
        }
    path = output_dir / "actual_visual_review.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _load_actual_visual_review(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _review_records(
    payload: dict[str, object], requirement: FixtureRequirement, pool: list[object]
) -> tuple[str, dict[str, dict[str, object]]]:
    requirements = payload.get("requirements")
    if not isinstance(requirements, dict):
        return "not_reviewed", {}
    entry = requirements.get(requirement.id)
    if not isinstance(entry, dict):
        return "not_reviewed", {}
    if entry.get("candidate_set_fingerprint") != candidate_set_fingerprint(pool):
        return "stale", {}
    records = entry.get("candidates", entry.get("reviews", []))
    if isinstance(records, dict):
        records = [dict(value, sku=key) if isinstance(value, dict) else {"sku": key} for key, value in records.items()]
    if not isinstance(records, list):
        return "current", {}
    result: dict[str, dict[str, object]] = {}
    for record in records:
        if isinstance(record, dict) and record.get("sku"):
            result[_sku_key(str(record["sku"]))] = record
    return "current", result


def _legacy_run_benchmark(
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
        target = _find_product_by_sku(store, str(discovery.get("sku") or "") or None) if discovery.get("found") else None
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


def _rank_current(pool: list[object], product: object | None) -> int | None:
    if not product:
        return None
    target = (_sku_key(getattr(product, "sku", None)), getattr(product, "canonical_url", ""))
    for index, candidate in enumerate(pool, start=1):
        current = (_sku_key(candidate.product.sku), candidate.product.canonical_url)
        if target == current:
            return index
    return None


def _targeted_recall_current(
    golden_items: list[dict[str, object]], discovery_items: list[dict[str, object]]
) -> dict[str, object]:
    by_position = {
        int(item["kp_position"]): item
        for item in discovery_items
        if item.get("kp_position") is not None
    }
    visual = [item for item in golden_items if item.get("product_role") == "VISUAL_SELECTION"]
    matchable = [item for item in visual if item.get("sku")]
    found = sum(bool(by_position.get(int(item["kp_position"]), {}).get("found")) for item in matchable)
    return {
        "visual_targets": len(visual),
        "matchable_sku_targets": len(matchable),
        "found": found,
        "recall": found / len(matchable) if matchable else None,
        "items": [
            {
                "kp_position": item.get("kp_position"),
                "sku": item.get("sku"),
                "found": bool(by_position.get(int(item["kp_position"]), {}).get("found")),
                "match_type": by_position.get(int(item["kp_position"]), {}).get("match_type"),
                "supplier": by_position.get(int(item["kp_position"]), {}).get("supplier"),
            }
            for item in visual
        ],
        "note": "Target-aware discovery is diagnostic only and may use a known SKU/query.",
    }


def _production_recall_current(
    golden_items: list[dict[str, object]], store: CatalogStore
) -> dict[str, object]:
    visual = [item for item in golden_items if item.get("product_role") == "VISUAL_SELECTION"]
    rows: list[dict[str, object]] = []
    matchable = 0
    present = 0
    for item in visual:
        sku = str(item.get("sku") or "") or None
        product = _find_product_by_sku(store, sku)
        if sku:
            matchable += 1
            present += int(product is not None)
        rows.append({
            "kp_position": item.get("kp_position"),
            "sku": sku,
            "matched_fixture_requirement": item.get("matched_fixture_requirement"),
            "status": "present" if product else "absent" if sku else "not_matchable_no_sku",
            "supplier": product.supplier if product else item.get("likely_supplier"),
            "url": product.canonical_url if product else None,
            "availability_status": effective_availability_status(product) if product else None,
        })
    return {
        "visual_targets": len(visual),
        "matchable_sku_targets": matchable,
        "present": present,
        "recall": present / matchable if matchable else None,
        "not_matchable_no_sku": sum(not item.get("sku") for item in visual),
        "items": rows,
        "note": "Measured only against the clean production catalog; golden discovery never populates it.",
    }


def _write_markdown_current(payload: dict[str, object], path: Path) -> None:
    recall = payload["production_catalog_recall"]
    targeted = payload["targeted_discovery_recall"]
    retrieval = payload["retrieval"]["retrieval_at"]
    visual = payload["retrieval"]["visual_at"]
    lines = [
        "# Golden benchmark — Dan",
        "",
        "Production recall is measured against the clean production catalog. Target-aware golden discovery is reported separately.",
        "",
        f"- Production catalog recall: `{recall['present']}/{recall['matchable_sku_targets']}`; targeted discovery recall: `{targeted['found']}/{targeted['matchable_sku_targets']}`.",
        f"- Retrieval: `retrieval@20={retrieval['retrieval_at_20']}`, `retrieval@50={retrieval['retrieval_at_50']}`, `retrieval@100={retrieval['retrieval_at_100']}`.",
        f"- Actual visual review only: `visual@1={visual['visual_at_1']}`, `visual@3={visual['visual_at_3']}`, `visual@5={visual['visual_at_5']}`, `visual@10={visual['visual_at_10']}`.",
        "",
        "| F | target | supplier | production | independent rank | production rank | visual status | visual rank | diagnosis |",
        "|---|---|---|---|---:|---:|---|---:|---|",
    ]
    for item in payload["retrieval"]["visual_targets"]:
        values = {
            key: "" if item.get(key) is None else item.get(key)
            for key in (
                "requirement_id", "sku", "supplier", "production_catalog_present",
                "independent_retrieval_rank", "production_retrieval_rank",
                "visual_review_status", "visual_rank", "diagnosis",
            )
        }
        lines.append("| {requirement_id} | {sku} | {supplier} | {production_catalog_present} | {independent_retrieval_rank} | {production_retrieval_rank} | {visual_review_status} | {visual_rank} | {diagnosis} |".format(**values))
    lines.extend([
        "",
        "## Production catalog recall",
        "",
        f"`{json.dumps(payload['production_catalog_recall'], ensure_ascii=False)}`",
        "",
        "System BOM is excluded from decorative visual metrics.",
        "",
        "Actual visual metrics are zero until the current run's review manifest is completed; no golden visual annotation is substituted.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def run_benchmark(
    golden_items: list[dict[str, object]],
    discovery_items: list[dict[str, object]],
    requirements: list[FixtureRequirement],
    store: CatalogStore,
    output_dir: Path,
    *,
    actual_review_path: Path | None = None,
) -> dict[str, object]:
    requirement_by_id = {requirement.id: requirement for requirement in requirements}
    discovery_by_position = {
        int(item["kp_position"]): item
        for item in discovery_items
        if item.get("kp_position") is not None
    }
    review_payload = _load_actual_visual_review(actual_review_path)
    visual_pools: dict[str, list[object]] = {}
    review_states: dict[str, str] = {}
    visual_targets: list[dict[str, object]] = []
    system_items: list[dict[str, object]] = []
    for item in golden_items:
        position = int(item["kp_position"])
        discovery = discovery_by_position.get(position, {})
        if item.get("product_role") == "SYSTEM_BOM":
            system_items.append({
                "kp_position": item.get("kp_position"),
                "sku": item.get("sku"),
                "category": item.get("golden_category"),
                "discovered": bool(discovery.get("discovered")),
                "parsed": bool(discovery.get("parser_success")),
                "found": bool(discovery.get("found")),
                "photo": bool(discovery.get("photo")),
                "supplier": discovery.get("supplier"),
                "url": discovery.get("url"),
            })
            continue
        requirement_id = item.get("matched_fixture_requirement")
        requirement = requirement_by_id.get(str(requirement_id)) if requirement_id else None
        if not requirement:
            visual_targets.append({
                "kp_position": item.get("kp_position"),
                "sku": item.get("sku"),
                "name": item.get("name"),
                "status": "no_requirement_mapping",
                "discovery_found": bool(discovery.get("found")),
            })
            continue
        if requirement.id not in visual_pools:
            visual_pools[requirement.id] = _visual_pool(requirement, store.all(), limit=100)
            review_states[requirement.id], _ = _review_records(
                review_payload, requirement, visual_pools[requirement.id]
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            build_contact_sheets(requirement, visual_pools[requirement.id], output_dir / "review")
        independent_pool = visual_pools[requirement.id]
        production_pool = wide_candidate_pool(
            requirement,
            store.all(),
            limit=100,
            include_color_alternatives=True,
            availability_policy="sellable",
        )
        target = _find_product_by_sku(store, str(item.get("sku") or "") or None)
        independent_rank = _rank_current(independent_pool, target)
        production_rank = _rank_current(production_pool, target)
        review_state, reviews = _review_records(review_payload, requirement, independent_pool)
        review = reviews.get(_sku_key(str(item.get("sku") or "")), {})
        decision = str(review.get("decision") or "")
        visual_rank = review.get("visual_rank")
        visual_rank_int = int(visual_rank) if isinstance(visual_rank, int) or (isinstance(visual_rank, str) and visual_rank.isdigit()) else None
        visual_approved = decision == "accept"
        visual_targets.append({
            "kp_position": item.get("kp_position"),
            "sku": item.get("sku"),
            "name": item.get("name"),
            "requirement_id": requirement.id,
            "match_confidence": item.get("match_confidence"),
            "discovery_found": bool(discovery.get("found")),
            "discovery_match_type": discovery.get("match_type"),
            "production_catalog_present": target is not None,
            "supplier": target.supplier if target else discovery.get("supplier"),
            "url": target.canonical_url if target else discovery.get("url"),
            "availability_status": effective_availability_status(target) if target else discovery.get("availability_status"),
            "availability_gate": "passed" if production_rank else "not_in_sellable_pool",
            "independent_retrieval_rank": independent_rank,
            "production_retrieval_rank": production_rank,
            "visual_review_status": decision if decision in {"accept", "reject"} else "not_reviewed" if review_state == "current" else review_state,
            "visual_review_reason": review.get("reason"),
            "visual_rank": visual_rank_int,
            "visual_at_1": bool(visual_approved and visual_rank_int and visual_rank_int <= 1),
            "visual_at_3": bool(visual_approved and visual_rank_int and visual_rank_int <= 3),
            "visual_at_5": bool(visual_approved and visual_rank_int and visual_rank_int <= 5),
            "visual_at_10": bool(visual_approved and visual_rank_int and visual_rank_int <= 10),
            "candidate_set_fingerprint": candidate_set_fingerprint(independent_pool),
            "diagnosis": (
                "targeted_only_not_in_production_catalog"
                if discovery.get("found") and target is None
                else "not_in_production_catalog"
                if target is None
                else "retrieval_or_availability_or_hard_gate_failure"
                if independent_rank is None
                else "availability_gate_only"
                if production_rank is None
                else "retrieved"
            ),
        })
    visual_counts = {
        metric: sum(bool(item.get(metric)) for item in visual_targets)
        for metric in ("visual_at_1", "visual_at_3", "visual_at_5", "visual_at_10")
    }
    retrieval_counts = {
        f"retrieval_at_{limit}": sum(
            bool(item.get("independent_retrieval_rank")) and int(item["independent_retrieval_rank"]) <= limit
            for item in visual_targets
        )
        for limit in (20, 50, 100)
    }
    by_requirement: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "targets": 0, "found": 0, "retrieved": 0,
            "availability_gate_only": 0, "not_discovered": 0,
            **{f"retrieval_at_{limit}": 0 for limit in (20, 50, 100)},
            **{f"visual_at_{limit}": 0 for limit in (1, 3, 5, 10)},
        }
    )
    for item in visual_targets:
        if not item.get("requirement_id"):
            continue
        stats = by_requirement[str(item["requirement_id"])]
        stats["targets"] += 1
        stats["found"] += int(bool(item.get("discovery_found")))
        stats["retrieved"] += int(item.get("independent_retrieval_rank") is not None)
        stats["availability_gate_only"] += int(item.get("diagnosis") == "availability_gate_only")
        stats["not_discovered"] += int(item.get("diagnosis") in {"not_in_production_catalog", "targeted_only_not_in_production_catalog"})
        for limit in (20, 50, 100):
            rank = item.get("independent_retrieval_rank")
            stats[f"retrieval_at_{limit}"] += int(rank is not None and rank <= limit)
        for limit in (1, 3, 5, 10):
            stats[f"visual_at_{limit}"] += int(bool(item.get(f"visual_at_{limit}")))
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
    output_dir.mkdir(parents=True, exist_ok=True)
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
        "targeted_discovery_recall": _targeted_recall_current(golden_items, discovery_items),
        "production_catalog_recall": _production_recall_current(golden_items, store),
        "retrieval": {"visual_targets": visual_targets, "by_requirement": dict(by_requirement), "retrieval_at": retrieval_counts, "visual_at": visual_counts},
        "system_bom_coverage": bom_summary,
        "supplier_coverage": supplier_coverage,
        "actual_visual_review": {
            "path": str(actual_review_path) if actual_review_path else None,
            "run_id": review_payload.get("run_id"),
            "requirements": review_states,
            "visual_metrics_require_actual_review": True,
        },
    }
    (output_dir / "benchmark.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown_current(payload, output_dir / "benchmark.md")
    return payload
