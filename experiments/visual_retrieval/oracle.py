"""Evaluation-only enrichment of missing golden product pages."""

from __future__ import annotations

import json
import re
from pathlib import Path

from lumimatch.extract import parse_product_page

from .common import (
    DEFAULT_DISCOVERY,
    DEFAULT_GOLDEN,
    SPIKE_DATA,
    SPIKE_SUPPLIERS,
    VisualCache,
    VisualCorpusStore,
    VisualFetcher,
    VisualProduct,
    _fallback_visual_metadata,
    normalize_sku,
    utc_now,
)


def _url_contains_sku(url: str, sku: str) -> bool:
    target = normalize_sku(sku)
    value = normalize_sku(url)
    if not target or target not in value:
        return False
    if target.isdigit():
        return bool(re.search(rf"(?<!\d){re.escape(target)}(?!\d)", value))
    return True


def _sitemap_urls(
    fetcher: VisualFetcher, base_url: str, *, limit: int = 20000
) -> list[str]:
    seen: set[str] = set()
    queue = [
        base_url.rstrip("/") + "/sitemap.xml",
        base_url.rstrip("/") + "/sitemap_index.xml",
    ]
    while queue and len(seen) < limit:
        candidate = queue.pop(0)
        if candidate in seen:
            continue
        seen.add(candidate)
        page = fetcher.get(candidate)
        if not page:
            continue
        text = page.content.decode("utf-8", "replace")
        for loc in re.findall(
            r"<loc>\s*(.*?)\s*</loc>", text, flags=re.IGNORECASE | re.DOTALL
        ):
            loc = loc.strip()
            if loc.casefold().endswith((".xml", ".xml.gz")) and loc not in queue:
                queue.append(loc)
            elif loc not in seen:
                seen.add(loc)
    return [
        value for value in seen if not value.casefold().endswith((".xml", ".xml.gz"))
    ]


def _target_page_urls(
    fetcher: VisualFetcher,
    supplier: str,
    sku: str,
    discovery_item: dict[str, object] | None,
) -> list[str]:
    discovered = str(discovery_item.get("url") or "") if discovery_item else ""
    if discovered:
        return [discovered]
    return [
        url
        for url in _sitemap_urls(fetcher, f"https://{supplier}")
        if _url_contains_sku(url, sku)
    ][:30]


def _same_sku_or_evidence(
    product_sku: str | None, sku: str, html: str, title: str | None
) -> bool:
    if normalize_sku(product_sku) == normalize_sku(sku):
        return True
    target = normalize_sku(sku)
    return bool(
        target and target in normalize_sku(html) and target in normalize_sku(title)
    )


def build_oracle_corpus(
    corpus_db: Path,
    *,
    golden_path: Path = DEFAULT_GOLDEN,
    discovery_path: Path = DEFAULT_DISCOVERY,
    model_scope: str = "oracle",
    timeout: float = 20.0,
    delay: float = 0.08,
) -> dict[str, object]:
    """Fetch only evaluation targets absent from the natural corpus."""
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    discovery_items: dict[int, dict[str, object]] = {}
    if discovery_path.exists():
        payload = json.loads(discovery_path.read_text(encoding="utf-8"))
        discovery_items = {
            int(item["kp_position"]): item
            for item in payload.get("items", [])
            if item.get("kp_position") is not None
        }
    store = VisualCorpusStore(corpus_db)
    natural_skus = {
        normalize_sku(product.sku)
        for product in store.all(scope="natural", ready_only=True)
        if product.sku
    }
    cache = VisualCache()
    fetcher = VisualFetcher(cache, timeout=timeout, delay=delay)
    results: list[dict[str, object]] = []
    try:
        for item in golden:
            sku = str(item.get("sku") or "") or None
            confidence = float(item.get("match_confidence") or 0.0)
            if (
                item.get("product_role") != "VISUAL_SELECTION"
                or not sku
                or confidence < 0.40
                or normalize_sku(sku) in natural_skus
            ):
                continue
            supplier = str(item.get("likely_supplier") or "")
            if supplier not in SPIKE_SUPPLIERS:
                results.append(
                    {
                        "kp_position": item.get("kp_position"),
                        "sku": sku,
                        "status": "not_run",
                        "reason": "no_allowed_supplier",
                    }
                )
                continue
            discovery_item = (
                discovery_items.get(int(item["kp_position"]))
                if item.get("kp_position") is not None
                else None
            )
            found: VisualProduct | None = None
            errors: list[str] = []
            for url in _target_page_urls(fetcher, supplier, sku, discovery_item):
                page = fetcher.get(url)
                if not page:
                    errors.append(f"{url}:fetch_failed")
                    continue
                html = page.content.decode("utf-8", "replace")
                parsed = parse_product_page(html, page.final_url, supplier)
                if parsed:
                    title, product_sku, image_urls = (
                        parsed.name,
                        parsed.sku,
                        list(parsed.image_urls),
                    )
                    brand, category, image_source = (
                        parsed.brand,
                        parsed.category,
                        parsed.image_source,
                    )
                else:
                    title, product_sku, image_urls, _ = _fallback_visual_metadata(
                        html, page.final_url
                    )
                    brand, category, image_source = (
                        str(item.get("brand") or "") or None,
                        str(item.get("golden_category") or "") or None,
                        "fallback_image_metadata",
                    )
                if not _same_sku_or_evidence(product_sku, sku, html, title):
                    errors.append(f"{url}:target_mismatch:{product_sku or 'none'}")
                    continue
                if not image_urls:
                    errors.append(f"{url}:no_image")
                    continue
                saved = fetcher.save_image(image_urls[0])
                if not saved:
                    errors.append(f"{url}:image_download_failed")
                    continue
                found = VisualProduct(
                    supplier,
                    page.final_url,
                    page.final_url.split("#", 1)[0],
                    sku,
                    title or str(item.get("name") or ""),
                    brand,
                    category,
                    image_urls[0],
                    saved.local_path,
                    saved.image_hash,
                    image_source or "oracle_target_page",
                    tuple(image_urls),
                    "ready",
                    None,
                )
                store.upsert(found, scope=model_scope)
                store.upsert_image(
                    model_scope,
                    found.canonical_url,
                    1,
                    image_urls[0],
                    saved,
                    is_primary=True,
                )
                cache.link_image_product(
                    saved.image_hash, supplier, found.canonical_url, 1
                )
                break
            results.append(
                {
                    "kp_position": item.get("kp_position"),
                    "sku": sku,
                    "fixture_requirement": item.get("matched_fixture_requirement"),
                    "confidence": confidence,
                    "supplier": supplier,
                    "found": found is not None,
                    "url": found.product_url if found else None,
                    "image": bool(found),
                    "errors": errors,
                }
            )
    finally:
        fetcher.close()
    payload = {
        "scope": model_scope,
        "created_at": utc_now(),
        "targets_considered": len(results),
        "found": sum(bool(item.get("found")) for item in results),
        "items": results,
    }
    target = SPIKE_DATA / "oracle_eval" / "manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload
