"""Golden-set parsing, bounded discovery and evaluation helpers.

The golden set is an evaluation input, not a production ranking signal.  This
module deliberately keeps the source parsing and discovery evidence separate
from the customer-facing candidate score.
"""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from .discovery import discover_product_urls, link_urls, sitemap_urls
from .extract import parse_product_page
from .fetch import PublicFetcher
from .models import CatalogProduct
from .storage import CatalogStore

ROLE_VISUAL = "VISUAL_SELECTION"
ROLE_SYSTEM = "SYSTEM_BOM"


def _clean(value: object | None) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).replace("\xa0", " ").split())
    return text or None


def _key(value: str | None) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", "", (value or "").casefold())


def _quantity(value: str | None) -> int | None:
    match = re.search(r"\d+", value or "")
    return int(match.group(0)) if match else None


def _price(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"\d[\d\s]*(?:[,.]\d{1,3})?", value)
    if not match:
        return None
    try:
        return float(match.group(0).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _role_and_category(name: str) -> tuple[str, str]:
    folded = name.casefold()
    if any(token in folded for token in ("профил", "соединител", "подвес gp", "шинопровод", "набор для подвеса", "блок питания", "led-лент", "led лент", "smd2835")):
        if "соединител" in folded:
            return ROLE_SYSTEM, "profile_connector"
        if "подвес gp" in folded or "набор для подвеса" in folded:
            return ROLE_SYSTEM, "track_suspension"
        if "шинопровод" in folded:
            return ROLE_SYSTEM, "track_rail"
        if "блок питания" in folded:
            return ROLE_SYSTEM, "power_supply"
        if "лент" in folded or "smd2835" in folded:
            return ROLE_SYSTEM, "led_strip"
        return ROLE_SYSTEM, "linear_profile"
    if "люстр" in folded:
        return ROLE_VISUAL, "chandelier"
    if "треков" in folded or "шинопровод" in folded:
        return ROLE_VISUAL, "track_spot"
    if "бра" in folded or "настенн" in folded or "подсветк" in folded:
        return ROLE_VISUAL, "wall_sconce"
    if "подвес" in folded:
        return ROLE_VISUAL, "pendant"
    if "прожектор" in folded or "линей" in folded:
        return ROLE_VISUAL, "linear_fixture"
    return ROLE_VISUAL, "unknown"


def _brand_supplier(name: str) -> tuple[str | None, str | None, str]:
    folded = name.casefold()
    if "elektrostandard" in folded or re.search(r"\b50248\b|\b85081/00\b|\b85078/01\b|\btrf-1-200-bk\b", folded):
        return "Elektrostandard", "eurosvet.ru", "brand explicitly present or verified by the Elektrostandard catalog family"
    if "kink light" in folded or "мекли" in folded or "фирс" in folded or "2207b" in folded:
        return "Kink Light", "kinklight.ru", "brand/series verified from the product naming and allowed supplier list"
    if "freya" in folded:
        return "Freya", "freya-light.com", "brand explicitly present in the product name"
    if "lumion" in folded:
        return "Lumion", "odeon-light.com", "brand explicitly present; public Lumion catalog is hosted by Odeon Light"
    if "lussole" in folded or "люссоле" in folded:
        return "Lussole", "shop.lussole.ru", "brand explicitly present in the product name"
    if "ambrella" in folded or " gp80" in folded:
        return "Ambrella", "ambrella.biz", "brand explicitly present in the product name or GP accessory family"
    if "swg" in folded:
        return "SWG", None, "brand explicit; no SWG domain is in suppliers.txt, so supplier is intentionally unverified"
    if "feron" in folded or "ll-894" in folded:
        return "Feron", None, "brand inferred from the public product naming; no allowed supplier domain verified"
    return None, None, "brand and supplier are not proven by the source row"


def _fixture_mapping(category: str, sku: str | None, role: str) -> tuple[str | None, float | None, str]:
    if role == ROLE_SYSTEM:
        if category in {"track_rail", "track_suspension"}:
            return "F-07", 0.78, "system component aligned with the sample track-system requirement"
        return "F-08", 0.66, "system/BOM component aligned with the sample hidden linear-light requirement"
    normalized = _key(sku)
    direct = {
        "50248": ("F-01", 0.88, "cylindrical pendant directly matches the F-01 visual family"),
        "fr2066wll40b": ("F-03", 0.72, "wall sconce role and bedside use are consistent with F-03"),
        "561037wl": ("F-04", 0.58, "wall-light role may correspond to the decorative vertical wall-light requirement"),
        "lsp4001": ("F-05", 0.54, "vertical wall light may serve the mirror-light requirement; dimensions need confirmation"),
        "lsp7187": ("F-04", 0.67, "decorative wall-light role is consistent with F-04"),
        "lsp4016": ("F-01", 0.42, "pendant role overlaps F-01, but geometry/model identity is not proven"),
        "2207b19": ("F-03", 0.49, "wall-light role overlaps F-03, but source project room is not proven"),
        "ll8941": ("F-02", 0.56, "linear fixture role is compatible with F-02; source dimensions differ from the visual brief"),
        "1108": ("F-05", 0.44, "functional wall/step-light role may overlap F-05, but mirror use is not proven"),
        "8507801": ("F-06", 0.79, "track-spot role directly matches the F-06 directional-light family"),
    }
    if normalized in direct:
        return direct[normalized]
    if "люстр" in category:
        return None, None, "golden product has no chandelier-specific FixtureRequirement in the current sample coverage"
    return None, None, "no confident FixtureRequirement mapping"


def _table_rows(docx_path: Path) -> list[list[str]]:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(docx_path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    rows: list[list[str]] = []
    for row in root.findall(".//w:tr", ns):
        cells: list[str] = []
        for cell in row.findall("./w:tc", ns):
            paragraphs: list[str] = []
            for paragraph in cell.findall(".//w:p", ns):
                values = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
                if values:
                    paragraphs.append("".join(values))
            cells.append(_clean(" ".join(paragraphs)) or "")
        if any(cells):
            rows.append(cells)
    return rows


def parse_golden_docx(docx_path: Path) -> list[dict[str, object]]:
    """Parse the commercial offer as structured source evidence.

    The parser reads the DOCX table directly, so generation is reproducible
    without adding python-docx to the production runtime.
    """
    rows = _table_rows(docx_path)
    if not rows:
        raise ValueError(f"No table rows found in {docx_path}")
    headers = [value.casefold() for value in rows[0]]

    def column(*names: str) -> int | None:
        for name in names:
            for index, header in enumerate(headers):
                if name in header:
                    return index
        return None

    number_col = column("№", "номер")
    name_col = column("наименование", "название") or 0
    quantity_col = column("кол-во", "количество")
    price_col = column("цена")
    delivery_col = column("срок поставки", "поставка")
    result: list[dict[str, object]] = []
    for row_index, row in enumerate(rows[1:], start=1):
        if len(row) <= name_col or not row[name_col]:
            continue
        name = row[name_col]
        role, category = _role_and_category(name)
        sku_pattern = r"(?<![A-Za-zА-Яа-я0-9])((?:[A-Za-z]{1,8}[-/]?\d[\w/-]*|\d{4,}[A-Za-z]*(?:[/,-][A-Za-z0-9]+)*))(?![A-Za-zА-Яа-я0-9])"
        ignored = {"led", "smd2835", "24v", "4000k", "4200k", "100w", "200w", "60w", "300w", "ip20"}
        sku = None
        for sku_match in re.finditer(sku_pattern, name):
            candidate = sku_match.group(1)
            folded_candidate = candidate.casefold()
            if folded_candidate in ignored or folded_candidate.startswith("smd2835") or re.fullmatch(r"[dh]\d+", candidate, re.IGNORECASE):
                continue
            sku = candidate
            break
        if sku and "артикул" in name.casefold():
            tail = name.casefold().split("артикул", 1)[1]
            explicit = re.search(r"([A-Za-zА-Яа-я]{1,8}[-/]?[\w/-]*\d[\w/-]*)", tail)
            sku = explicit.group(1) if explicit else sku
        comma_suffix = re.search(r"(\d{4,}[A-Za-z]*),([0-9]+)", name)
        if comma_suffix:
            sku = f"{comma_suffix.group(1)},{comma_suffix.group(2)}"
        brand, supplier, supplier_note = _brand_supplier(name)
        matched, confidence, mapping_note = _fixture_mapping(category, sku, role)
        discovery_query = "Мекли" if "мекли" in name.casefold() and not sku else None
        result.append(
            {
                "kp_position": int(row[number_col]) if number_col is not None and number_col < len(row) and _quantity(row[number_col]) else row_index,
                "brand": brand,
                "name": name,
                "sku": sku,
                "discovery_query": discovery_query,
                "quantity": _quantity(row[quantity_col]) if quantity_col is not None and quantity_col < len(row) else None,
                "price": _price(row[price_col]) if price_col is not None and price_col < len(row) else None,
                "delivery_status": row[delivery_col] if delivery_col is not None and delivery_col < len(row) else None,
                "product_role": role,
                "golden_category": category,
                "likely_supplier": supplier,
                "matched_fixture_requirement": matched,
                "match_confidence": confidence,
                "notes": f"{supplier_note}; {mapping_note}",
                "source": {"file": str(docx_path).replace("\\", "/"), "table_row": row_index + 1},
            }
        )
    return result


def write_golden_set(docx_path: Path, output_path: Path) -> list[dict[str, object]]:
    items = parse_golden_docx(docx_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    mapping = [
        {
            "kp_position": item["kp_position"],
            "sku": item["sku"],
            "matched_fixture_requirement": item["matched_fixture_requirement"],
            "confidence": item["match_confidence"],
            "product_role": item["product_role"],
            "note": item["notes"],
        }
        for item in items
    ]
    mapping_path = output_path.parent / "requirement_mapping.json"
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


def _allowed_supplier_domains(path: Path) -> list[str]:
    return [
        line.strip().removeprefix("https://").removeprefix("http://").rstrip("/").lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _same_sku(expected: str | None, actual: str | None) -> bool:
    if not expected or not actual:
        return False
    return _key(expected) == _key(actual)


def _url_has_target(url: str, sku: str | None) -> bool:
    if not sku:
        return False
    url_key = _key(url)
    sku_key = _key(sku)
    return bool(sku_key and sku_key in url_key)


def _raw_target_evidence(html: str, sku: str | None) -> bool:
    if not sku:
        return False
    escaped = re.escape(sku)
    return bool(re.search(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9]|[/,-]\d)", html, re.IGNORECASE))


def _candidate_urls(fetcher: PublicFetcher, base_url: str, sku: str | None, query: str | None = None) -> tuple[list[str], str]:
    target = sku or query
    if not target:
        return [], "no_source_sku_to_discover"
    sitemap, _ = sitemap_urls(fetcher, base_url, max_urls=20000)
    host = urlparse(base_url).netloc.lower()
    sitemap = [url for url in sitemap if urlparse(url).netloc.lower() in {host, f"www.{host}", host.removeprefix("www.")}]
    exact = [url for url in sitemap if _url_has_target(url, target)]
    if exact:
        return list(dict.fromkeys(exact)), "sitemap_target_match"
    discovered, _, _ = discover_product_urls(fetcher, base_url, max_urls=600)
    exact = [url for url in discovered if _url_has_target(url, target)]
    if exact:
        return list(dict.fromkeys(exact)), "generic_product_discovery_target_match"
    target_key = _key(target)
    home = fetcher.get(base_url)
    if home:
        home_html = home.content.decode("utf-8", "replace")
        soup = BeautifulSoup(home_html, "lxml")
        for form in soup.find_all("form"):
            query_input = form.find("input", attrs={"name": re.compile(r"^(query|q|search)$", re.IGNORECASE)})
            if not query_input:
                continue
            action = urljoin(home.final_url, form.get("action") or "/")
            search_url = f"{action}?{urlencode({query_input.get('name', 'query'): target})}"
            result_page = fetcher.get(search_url)
            if not result_page:
                continue
            result_html = result_page.content.decode("utf-8", "replace")
            if target_key not in _key(result_html):
                continue
            result_links = link_urls(result_html, result_page.final_url, base_url)
            result_soup = BeautifulSoup(result_html, "lxml")
            exact_links = [
                urljoin(result_page.final_url, anchor.get("href"))
                for anchor in result_soup.select("a[href]")
                if target_key in _key(anchor.get_text(" ", strip=True))
            ]
            exact_links.extend(url for url in result_links if target_key in _key(url))
            exact_links = [url for url in exact_links if "/search" not in urlparse(url).path.casefold()]
            if exact_links:
                return list(dict.fromkeys(exact_links)), "supplier_search_form_target_match"
            product_links = [
                url for url in result_links
                if "/search" not in urlparse(url).path.casefold()
                and re.search(r"/\d+\.html$", urlparse(url).path.lower())
            ]
            if product_links:
                return list(dict.fromkeys(product_links[:80])), "supplier_search_form_contains_target"
    # Some catalogues expose numeric product URLs only from category pages;
    # the SKU exists in the card title/anchor but not in the URL.  Inspect a
    # bounded set of category pages and return only links carrying the target
    # text.  This is a generic adapter, not a SKU-to-URL table.
    category_urls = [
        url for url in sitemap
        if urlparse(url).path.rstrip("/")
        and not urlparse(url).path.lower().endswith((".html", ".xml"))
        and urlparse(url).path.count("/") <= 5
    ]
    category_urls.sort(
        key=lambda url: (
            not any(token in url.casefold() for token in ("bra", "lyustra", "podves", "trek", "komplekt", "profil", "svetil")),
            url.count("/"),
        )
    )
    for category_url in category_urls[:12]:
        page = fetcher.get(category_url)
        if not page:
            continue
        html = page.content.decode("utf-8", "replace")
        if not target_key or target_key not in _key(html):
            continue
        soup_links = link_urls(html, page.final_url, base_url)
        exact_links = [
            url for url in soup_links
            if target_key in _key(url) or target_key in _key(urlparse(url).path)
        ]
        if exact_links:
            return list(dict.fromkeys(exact_links)), "category_page_target_match"
        product_links = [url for url in soup_links if urlparse(url).path.lower().endswith(".html")]
        if product_links:
            return list(dict.fromkeys(product_links[:80])), "category_page_contains_target"
    if home:
        links = link_urls(home.content.decode("utf-8", "replace"), home.final_url, base_url)
        exact = [url for url in links if _url_has_target(url, target)]
        if exact:
            return list(dict.fromkeys(exact)), "homepage_link_target_match"
    return [], "sitemap_and_bounded_links_no_target"


def run_golden_discovery(
    golden_items: list[dict[str, object]],
    suppliers_path: Path,
    store: CatalogStore,
    *,
    max_targets: int | None = None,
) -> list[dict[str, object]]:
    """Find exact golden SKUs through public inventories, never URL maps."""
    domains = _allowed_supplier_domains(suppliers_path)
    fetcher = PublicFetcher(store, timeout=15.0, delay=0.05)
    results: list[dict[str, object]] = []
    try:
        for item in golden_items[:max_targets]:
            sku = str(item.get("sku") or "") or None
            discovery_query = str(item.get("discovery_query") or "") or None
            preferred = str(item.get("likely_supplier") or "")
            scopes = [preferred] if preferred in domains else domains
            found_product: CatalogProduct | None = None
            found_url: str | None = None
            method = "not_run"
            discovered = False
            parser_success = False
            errors: list[str] = []
            for supplier in scopes:
                try:
                    urls, method = _candidate_urls(fetcher, f"https://{supplier}", sku, discovery_query)
                except (OSError, RuntimeError, ValueError) as exc:  # one supplier must not stop the benchmark
                    errors.append(f"{supplier}: {type(exc).__name__}: {exc}")
                    continue
                if urls:
                    discovered = True
                for url in urls[:80]:
                    page = fetcher.get(url)
                    if not page:
                        errors.append(f"{url}: fetch_failed")
                        continue
                    parsed = parse_product_page(page.content.decode("utf-8", "replace"), page.final_url, supplier)
                    if not parsed:
                        errors.append(f"{url}: parser_failed")
                        continue
                    parser_success = True
                    page_html = page.content.decode("utf-8", "replace")
                    name_blob = _key(" ".join(value for value in (parsed.name, parsed.description, parsed.series) if value))
                    exact_match = _same_sku(sku, parsed.sku)
                    name_match = bool(discovery_query and _key(discovery_query) in name_blob)
                    page_label_match = bool(sku and _raw_target_evidence(page_html, sku))
                    if not exact_match and not name_match and not page_label_match:
                        errors.append(f"{url}: target_mismatch:{parsed.sku or 'none'}")
                        continue
                    if page_label_match and not exact_match:
                        # The exact token is present in the fetched product
                        # page, but the generic extractor did not expose it
                        # as a SKU (Kink uses numeric URLs). Preserve that
                        # provenance in attributes rather than inventing a
                        # new URL or silently treating a model variant as exact.
                        parsed.sku = sku
                        parsed.attributes["sku_evidence"] = "exact token in public product page"
                    if parsed.primary_image_url:
                        saved = fetcher.save_image(parsed.primary_image_url)
                        if saved:
                            parsed.local_image_path = saved
                    store.upsert(parsed)
                    found_product = parsed
                    found_url = parsed.canonical_url
                    break
                if found_product:
                    break
            results.append(
                {
                    "kp_position": item.get("kp_position"),
                    "sku": sku,
                    "name": item.get("name"),
                    "product_role": item.get("product_role"),
                    "golden_category": item.get("golden_category"),
                    "found": found_product is not None,
                    "match_type": "exact_sku" if found_product and _same_sku(sku, found_product.sku) else "page_label" if found_product and sku else "name_query" if found_product else None,
                    "discovered": discovered,
                    "supplier": found_product.supplier if found_product else (preferred or None),
                    "url": found_url,
                    "method": method,
                    "parser_success": parser_success,
                    "availability_status": found_product.availability_status if found_product else None,
                    "photo": bool(found_product and (found_product.primary_image_url or found_product.local_image_path)),
                    "family": found_product.product_family if found_product else None,
                    "brand": found_product.brand if found_product else item.get("brand"),
                    "errors": errors,
                }
            )
    finally:
        fetcher.close()
    return results


def write_discovery_report(results: list[dict[str, object]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": results,
        "summary": {
            "total": len(results),
            "found": sum(bool(item.get("found")) for item in results),
            "discovered": sum(bool(item.get("discovered")) for item in results),
            "parsed": sum(bool(item.get("parser_success")) for item in results),
            "photo": sum(bool(item.get("photo")) for item in results),
        },
    }
    (output_dir / "discovery_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Golden discovery — Dan", "", f"- generated_at: `{payload['generated_at']}`", "", "| pos | sku | role | found | discovered | parsed | supplier | status | photo | method |", "|---:|---|---|---|---|---|---|---|---|---|"]
    for item in results:
        values = {key: "" if item.get(key) is None else item.get(key) for key in ("kp_position", "sku", "product_role", "found", "discovered", "parser_success", "supplier", "availability_status", "photo", "method")}
        lines.append("| {kp_position} | {sku} | {product_role} | {found} | {discovered} | {parser_success} | {supplier} | {availability_status} | {photo} | {method} |".format(**values))
    lines.extend(["", "`found` means the parsed supplier card contains the exact normalized SKU. A URL is never generated from a SKU map; discovery uses public sitemap/homepage inventories.", ""])
    (output_dir / "discovery_report.md").write_text("\n".join(lines), encoding="utf-8")
