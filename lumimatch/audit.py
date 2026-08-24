"""Small, repeatable public supplier audit."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .discovery import link_urls, product_url_score, sitemap_urls
from .extract import parse_product_page
from .fetch import PublicFetcher
from .storage import CatalogStore


@dataclass
class SupplierAudit:
    url: str
    home_status: int | None = None
    robots_status: int | None = None
    sitemap_status: int | None = None
    sitemap_urls: int = 0
    jsonld_blocks: int = 0
    jsonld_product: bool = False
    og_fields: int = 0
    canonical: str | None = None
    category_links: int = 0
    pagination_links: int = 0
    product_like_links: int = 0
    images: int = 0
    javascript_dependency: str = "не определена по ограниченному аудиту"
    playwright_needed: str = "не проверялся; HTTP-first достаточен для аудита"
    public_api: str = "не выявлялся отдельно; XHR/API не нужен для MVP-аудита"
    sample_product: str | None = None
    notes: list[str] = field(default_factory=list)


def audit_supplier(fetcher: PublicFetcher, base_url: str) -> SupplierAudit:
    base_url = base_url.rstrip("/")
    audit = SupplierAudit(url=base_url)
    root = urlparse(base_url)
    robots = fetcher.get(f"{root.scheme}://{root.netloc}/robots.txt", use_cache=False)
    audit.robots_status = robots.status_code if robots else None
    sitemap, audit.sitemap_status = sitemap_urls(fetcher, base_url, max_urls=10000)
    audit.sitemap_urls = len(sitemap)
    home = fetcher.get(base_url, use_cache=False)
    if not home:
        audit.notes.append(
            "Главная страница не получена обычным HTTP; сборщик продолжит с другими поставщиками."
        )
        return audit
    audit.home_status = home.status_code
    html = home.content.decode("utf-8", "replace")
    soup = BeautifulSoup(html, "lxml")
    audit.jsonld_blocks = len(soup.find_all("script", type="application/ld+json"))
    audit.og_fields = len(soup.select("meta[property^='og:']"))
    canonical = soup.find("link", rel="canonical")
    audit.canonical = canonical.get("href") if canonical else None
    links = link_urls(html, home.final_url, base_url)
    audit.category_links = sum(
        1 for link in links if "/catalog" in link.lower() or "/category" in link.lower()
    )
    audit.pagination_links = sum(
        1
        for link in links
        if re.search(r"(?:page|p=|next|страниц)", link, re.IGNORECASE)
    )
    audit.product_like_links = sum(1 for link in links if product_url_score(link) >= 7)
    audit.images = len(soup.find_all("img"))
    if len(soup.find_all("script")) > 12 and audit.jsonld_blocks == 0:
        audit.javascript_dependency = (
            "заметная JS-обвязка; JSON-LD на главной не найден"
        )
    candidates = sorted(set(sitemap + links), key=product_url_score, reverse=True)
    for candidate in candidates[:12]:
        product_page = fetcher.get(candidate)
        if not product_page:
            continue
        product = parse_product_page(
            product_page.content.decode("utf-8", "replace"),
            product_page.final_url,
            root.netloc,
        )
        if product:
            audit.jsonld_product = True
            audit.sample_product = (
                f"{product.name} ({product.sku or 'артикул не извлечён'})"
            )
            break
    if not audit.jsonld_product:
        audit.notes.append(
            "В ограниченной выборке карточка Product не распознана; нужен site-specific adapter или browser fallback."
        )
    return audit


def audit_all(
    suppliers: list[str], store: CatalogStore | None = None
) -> list[SupplierAudit]:
    owned_store = store or CatalogStore()
    fetcher = PublicFetcher(owned_store)
    try:
        return [audit_supplier(fetcher, supplier) for supplier in suppliers]
    finally:
        fetcher.close()


def write_audit(path: str, audits: list[SupplierAudit]) -> None:
    lines = [
        "# Аудит поставщиков LumiMatch",
        "",
        f"Дата bounded-аудита: {datetime.now(timezone.utc).date().isoformat()}. Проверены robots.txt, sitemap, главная страница и ограниченная выборка публичных ссылок.",
        "",
        "Сборщик использует HTTP-first и не обходит CAPTCHA, авторизацию или технические защиты. Отсутствие Product в выборке не означает, что каталог недоступен полностью.",
        "",
    ]
    for audit in audits:
        lines.extend(
            [
                f"## {audit.url}",
                "",
                f"- robots.txt: `{audit.robots_status if audit.robots_status is not None else 'ошибка/недоступен'}`",
                f"- sitemap.xml: `{audit.sitemap_status if audit.sitemap_status is not None else 'ошибка/недоступен'}`, URL в карте: `{audit.sitemap_urls}`",
                f"- главная HTTP: `{audit.home_status if audit.home_status is not None else 'ошибка/недоступна'}`",
                f"- JSON-LD blocks на главной: `{audit.jsonld_blocks}`, Product в выборке: `{'да' if audit.jsonld_product else 'нет'}`",
                f"- OpenGraph/meta: `{audit.og_fields}`, canonical: `{audit.canonical or 'не найден'}`",
                f"- category links: `{audit.category_links}`, pagination-like links: `{audit.pagination_links}`, product-like links: `{audit.product_like_links}`",
                f"- изображения на главной: `{audit.images}`",
                f"- JavaScript: {audit.javascript_dependency}",
                f"- Playwright: {audit.playwright_needed}",
                f"- публичный XHR/API: {audit.public_api}",
                f"- пример распознанной карточки: {audit.sample_product or 'нет'}",
            ]
        )
        lines.extend(f"- примечание: {note}" for note in audit.notes)
        lines.append("")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
