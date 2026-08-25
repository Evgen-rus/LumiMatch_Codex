"""Typer CLI for the availability-gated, visual-first local workflow."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import typer

from .audit import audit_all, write_audit
from .availability import effective_availability_status
from .collector import CatalogCollector
from .fetch import PublicFetcher
from .models import FixtureRequirement, ScoredCandidate
from .paths import OUTPUT, ensure_dirs
from .pdf_project import create_sample_reference_crops, inspect_project, render_pages
from .report import write_reports, write_unavailable_report
from .scoring import (
    apply_visual_review,
    candidate_pool_diagnostics,
    finalize_candidates,
    finalize_unavailable_visual_candidates,
    live_recheck_candidate,
    wide_candidate_pool,
)
from .storage import CatalogStore
from .taxonomy import classify_requirement
from .visual_review import build_contact_sheets

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _suppliers(path: Path, value: str | None) -> list[str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not value:
        return lines
    wanted = {part.strip().lower().removeprefix("https://").removeprefix("http://").rstrip("/") for part in value.split(",") if part.strip()}
    return [line for line in lines if line.lower().removeprefix("https://").removeprefix("http://").rstrip("/") in wanted]


def _requirements(path: Path) -> list[FixtureRequirement]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    requirements = [FixtureRequirement.model_validate(item) for item in payload]
    for requirement in requirements:
        if not requirement.taxonomy_family:
            requirement.taxonomy_family = classify_requirement(requirement)
    return requirements


def _sample_coverage(requirements: list[FixtureRequirement]) -> list[FixtureRequirement]:
    existing = {requirement.id for requirement in requirements}
    additions = [
        FixtureRequirement(
            id="F-07",
            room="гостиная / спальни",
            fixture_type="шинопровод трековой системы",
            visual_description="Система/шина, на которую могут устанавливаться направленные приборы; конкретная серия и напряжение в проекте не доказаны.",
            color="чёрный",
            shape="линейный профиль",
            mounting="потолочный",
            technical_constraints=["система трека", "нужна совместимость по типу шины", "серия и напряжение требуют ручной проверки"],
            source_pages=["Dan_dia-2.pdf, лист 10", "Dan_dia-2.pdf, лист 11", "Dan_vis.pdf, страницы 1-8 и 11-22"],
            confidence=0.45,
            coverage_status="ambiguous",
            coverage_note="На визуализациях видны направленные приборы; отдельный шинопровод и его серия не подтверждены.",
            taxonomy_family="track_rail",
        ),
        FixtureRequirement(
            id="F-08",
            room="гардеробная / санузлы",
            fixture_type="светодиодная лента или линейный профиль",
            visual_description="Скрытая непрерывная подсветка ниш, мебели, зеркал и потолочных линий; длину и мощность нужно считать вручную по плану.",
            color="нейтральный белый свет",
            shape="линейный",
            mounting="встроенный / скрытый",
            technical_constraints=["непрерывная линия", "нужен ручной расчёт длины по плану", "профиль и LED-лента не считать взаимозаменяемыми без проверки"],
            source_pages=["Dan_dia-2.pdf, лист 10", "Dan_dia-2.pdf, лист 11", "Dan_vis.pdf, страницы 23-30"],
            confidence=0.58,
            coverage_status="visual_only",
            coverage_note="В проекте есть несколько скрытых световых линий, но нет спецификации профиля/ленты.",
            taxonomy_family="led_strip",
        ),
    ]
    return requirements + [item for item in additions if item.id not in existing]


def _write_requirements(path: Path, requirements: list[FixtureRequirement]) -> None:
    path.write_text(json.dumps([item.model_dump(mode="json") for item in requirements], ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_sample_visual_review(candidates: list[ScoredCandidate], review_path: Path = Path("data/visual_review.json")) -> list[ScoredCandidate]:
    if not review_path.exists():
        return candidates
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    for index, candidate in enumerate(candidates):
        requirement_reviews = payload.get(candidate.requirement_id, {})
        key = candidate.product.sku or candidate.product.source_url
        review = requirement_reviews.get(key)
        if isinstance(review, dict):
            candidates[index] = apply_visual_review(candidate, review)
    return candidates


def _supplier_stats(results: list[object]) -> list[dict[str, object]]:
    return [
        {
            "supplier": result.supplier,
            "availability_mode": result.availability_mode,
            "discovered_product_urls": result.discovered_product_urls,
            "parsed_products": result.parsed_products,
            "in_stock_products": result.in_stock_products,
            "out_of_stock": result.out_of_stock,
            "discontinued": result.discontinued,
            "unknown_products": result.unknown_products,
            "failed_products": result.failed_products,
            "last_refresh": result.last_refresh,
            "status": result.status,
            "errors": result.errors,
        }
        for result in results
    ]


@app.command()
def audit(
    suppliers_file: Path = typer.Option(Path("suppliers.txt"), exists=True),  # noqa: B008
    output: Path = typer.Option(Path("docs/SUPPLIER_AUDIT.md")),  # noqa: B008
) -> None:
    """Audit all allowed public supplier sites."""
    ensure_dirs()
    audits = audit_all(_suppliers(suppliers_file, None))
    output.parent.mkdir(parents=True, exist_ok=True)
    write_audit(str(output), audits)
    typer.echo(f"Аудит сохранён: {output}; сайтов: {len(audits)}")


@app.command()
def collect(
    suppliers_file: Path = typer.Option(Path("suppliers.txt"), exists=True),  # noqa: B008
    suppliers: str | None = typer.Option(None, help="Домены через запятую; по умолчанию все разрешённые сайты."),
    max_pages: int = typer.Option(30, min=1, max=500),
    no_images: bool = typer.Option(False, help="Не скачивать локальные копии фотографий."),
) -> None:
    """Discover and fetch product cards from every allowed supplier."""
    ensure_dirs()
    store = CatalogStore()
    collector = CatalogCollector(store)
    results = collector.collect(_suppliers(suppliers_file, suppliers), max_pages, not no_images)
    removed = collector.refresh_cached()
    for result in results:
        typer.echo(f"{result.supplier} [{result.availability_mode}]: discovered={result.discovered_product_urls}, pages={result.pages_visited}, parsed={result.parsed_products}, in_stock={result.in_stock_products}, unknown={result.unknown_products}, errors={len(result.errors)}")
    typer.echo(f"Всего карточек в SQLite: {store.count()}; удалено категорий: {removed}")


@app.command("shortlist")
def shortlist_command(
    requirements: Path = typer.Option(Path("data/fixture_requirements.json"), exists=True),  # noqa: B008
    output: Path = typer.Option(Path("data/shortlist.json")),  # noqa: B008
    top_n: int = typer.Option(80, min=1, max=200),
) -> None:
    """Build a wide hard-filtered pool; final results require Codex visual review."""
    store = CatalogStore()
    products = store.all()
    if not products:
        raise typer.BadParameter("Каталог пуст. Сначала выполните collect.")
    result: dict[str, list[dict[str, object]]] = {}
    for requirement in _requirements(requirements):
        result[requirement.id] = [item.model_dump(mode="json") for item in wide_candidate_pool(requirement, products, top_n)]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"Широкий candidate pool сохранён: {output}")


@app.command("sample-run")
def sample_run(
    max_pages: int = typer.Option(28, min=1, max=100),
    pool_size: int = typer.Option(80, min=30, max=200),
    skip_audit: bool = typer.Option(False, help="Не повторять аудит поставщиков."),
) -> None:
    """Run the complete availability-gated visual-first workflow on the sample PDFs."""
    ensure_dirs()
    pdf_paths = [Path("samples/Dan_dia-2.pdf"), Path("samples/Dan_vis.pdf")]
    inspect_project(pdf_paths, Path("data/pdf_extraction.json"))
    render_dir = OUTPUT / "sample_references"
    references = {
        "Dan_dia-2.pdf": [10, 11, 14, 15, 16, 17, 18, 19],
        "Dan_vis.pdf": [1, 2, 11, 18, 23, 25, 27, 29, 30],
    }
    for name, pages in references.items():
        rendered = render_pages(Path("samples") / name, pages, render_dir, scale=1.0)
        typer.echo(f"Рендеры {name}: {len(rendered)}")

    requirements_path = Path("data/fixture_requirements.json")
    requirements = _sample_coverage(_requirements(requirements_path))
    requirements = create_sample_reference_crops(requirements, render_dir, OUTPUT / "review")
    _write_requirements(requirements_path, requirements)

    suppliers = _suppliers(Path("suppliers.txt"), None)
    if not skip_audit:
        audits = audit_all(suppliers)
        write_audit("docs/SUPPLIER_AUDIT.md", audits)

    store = CatalogStore()
    collection_fetcher = PublicFetcher(store, timeout=2.5, delay=0.03)
    collector = CatalogCollector(store, collection_fetcher)
    collection_results = collector.collect(suppliers, max_pages, True)
    collection_fetcher.close()
    removed = collector.refresh_cached()
    for result in collection_results:
        typer.echo(f"{result.supplier} [{result.availability_mode}]: discovered={result.discovered_product_urls}, pages={result.pages_visited}, parsed={result.parsed_products}, in_stock={result.in_stock_products}, unknown={result.unknown_products}, errors={len(result.errors)}")

    products = store.all()
    shortlisted: dict[str, list[ScoredCandidate]] = {}
    unavailable_shortlisted: dict[str, list[ScoredCandidate]] = {}
    rejected: dict[str, list[ScoredCandidate]] = {}
    unavailable_rejected: dict[str, list[ScoredCandidate]] = {}
    search_stats: dict[str, dict[str, object]] = {}
    for requirement in requirements:
        diagnostics = candidate_pool_diagnostics(requirement, products, pool_size)
        pool = wide_candidate_pool(requirement, products, pool_size, include_color_alternatives=True, availability_policy="sellable")
        unavailable_diagnostics = candidate_pool_diagnostics(requirement, products, pool_size, availability_policy="unavailable_visual")
        unavailable_pool = wide_candidate_pool(
            requirement,
            products,
            pool_size,
            include_color_alternatives=True,
            availability_policy="unavailable_visual",
        )
        diagnostics.visual_pool = len(pool)
        build_contact_sheets(requirement, pool, OUTPUT / "review")
        build_contact_sheets(requirement, unavailable_pool, OUTPUT / "review_unavailable")
        reviewed = _apply_sample_visual_review(pool)
        unavailable_reviewed = _apply_sample_visual_review(unavailable_pool)
        primary = [item for item in reviewed if item.color_mode == "primary"]
        alternatives = [item for item in reviewed if item.color_mode == "color_alternative"]
        finalists, visual_rejected = finalize_candidates(primary, alternatives)
        unavailable_primary = [item for item in unavailable_reviewed if item.color_mode == "primary"]
        unavailable_alternatives = [item for item in unavailable_reviewed if item.color_mode == "color_alternative"]
        unavailable_finalists, unavailable_visual_rejected = finalize_unavailable_visual_candidates(unavailable_primary, unavailable_alternatives)
        live_rejected = 0
        unavailable_live_rejected = 0
        live_fetcher = PublicFetcher(store)
        live_finalists: list[ScoredCandidate] = []
        live_unavailable_finalists: list[ScoredCandidate] = []
        try:
            for candidate in finalists:
                refreshed, reason = live_recheck_candidate(candidate, live_fetcher, availability_policy="sellable")
                if refreshed:
                    live_finalists.append(refreshed)
                else:
                    live_rejected += 1
                    candidate.visual_reject_reason = reason
                    visual_rejected.append(candidate)
            for candidate in unavailable_finalists:
                refreshed, reason = live_recheck_candidate(candidate, live_fetcher, availability_policy="unavailable_visual")
                if refreshed:
                    live_unavailable_finalists.append(refreshed)
                else:
                    unavailable_live_rejected += 1
                    candidate.visual_reject_reason = reason
                    unavailable_visual_rejected.append(candidate)
        finally:
            live_fetcher.close()
        shortlisted[requirement.id] = live_finalists[:5]
        unavailable_keys = {(item.product.supplier, item.product.sku or item.product.source_url) for item in live_finalists}
        unavailable_shortlisted[requirement.id] = [
            item for item in live_unavailable_finalists
            if (item.product.supplier, item.product.sku or item.product.source_url) not in unavailable_keys
        ][:5]
        rejected[requirement.id] = visual_rejected
        unavailable_rejected[requirement.id] = unavailable_visual_rejected
        diagnostics.rejected_by_visual = len(visual_rejected) + len(unavailable_visual_rejected)
        diagnostics.finalists = len(live_finalists)
        unavailable_statuses = Counter(effective_availability_status(item.product) for item in unavailable_shortlisted[requirement.id])
        search_stats[requirement.id] = {
            **diagnostics.as_dict(),
            "wide_candidates_considered": len(pool),
            "unavailable_wide_candidates_considered": len(unavailable_pool),
            "live_recheck_rejected": live_rejected,
            "unavailable_live_recheck_rejected": unavailable_live_rejected,
            "in_stock_visual_finalists": len(live_finalists),
            "out_of_stock_visual_finalists": unavailable_statuses.get("out_of_stock", 0),
            "preorder_visual_finalists": unavailable_statuses.get("preorder", 0),
            "expected_visual_finalists": unavailable_statuses.get("expected", 0),
            "check_availability_visual_finalists": unavailable_statuses.get("check_availability", 0),
            "discontinued_rejected": unavailable_diagnostics.discontinued_rejected,
            "visual_rejected": len(visual_rejected) + len(unavailable_visual_rejected),
            "availability_gate": "supplier capability: stock_tracked / stock_not_published / mixed",
            "color_fallback_used": any(item.color_mode == "color_alternative" for item in live_finalists),
        }

    supplier_stats = _supplier_stats(collection_results)
    write_reports(requirements, shortlisted, OUTPUT, "lumimatch_sample", search_stats=search_stats, rejected=rejected, supplier_stats=supplier_stats)
    write_unavailable_report(
        requirements,
        unavailable_shortlisted,
        OUTPUT,
        "lumimatch_sample_unavailable",
        search_stats=search_stats,
        rejected=unavailable_rejected,
    )
    Path("data/shortlist.json").write_text(json.dumps({key: [item.model_dump(mode="json") for item in value] for key, value in shortlisted.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("docs/SAMPLE_RUN.md").write_text(_sample_run_note(collection_results, store.count(), shortlisted, unavailable_shortlisted, search_stats, supplier_stats, removed), encoding="utf-8")
    typer.echo(f"Sample run V2 завершён. Карточек в каталоге: {store.count()}; требований: {len(requirements)}; sellable finalists: {sum(len(items) for items in shortlisted.values())}; unavailable visual finalists: {sum(len(items) for items in unavailable_shortlisted.values())}")


def _sample_run_note(results: list[object], count: int, shortlisted: dict[str, list[ScoredCandidate]], unavailable_shortlisted: dict[str, list[ScoredCandidate]], search_stats: dict[str, dict[str, object]], supplier_stats: list[dict[str, object]], removed: int) -> str:
    lines = [
        "# SAMPLE_RUN V2",
        "",
        "Повторный availability-gated, visual-first прогон на `samples/Dan_dia-2.pdf` и `samples/Dan_vis.pdf`.",
        "",
        f"- FixtureRequirement после coverage pass: `{len(shortlisted)}`",
        f"- карточек в локальном SQLite: `{count}`",
        f"- удалено карточек, переставших быть product pages при refresh: `{removed}`",
        "- reference crops и contact sheets: `output/review/`",
        "- machine source: `output/lumimatch_sample.json`",
        "- reports: `output/lumimatch_sample.md` и `output/lumimatch_sample.html`",
        "- unavailable visual diagnostics: `output/lumimatch_sample_unavailable.md`, `output/lumimatch_sample_unavailable.html` и `output/lumimatch_sample_unavailable.json`",
        "- rejected diagnostics: `output/debug/rejected_candidates.json`",
        "",
        "## Supplier coverage",
        "",
        "| supplier | mode | discovered | parsed | in_stock | unknown | out_of_stock | discontinued | failed | status |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in supplier_stats:
        lines.append(f"| {item['supplier']} | {item['availability_mode']} | {item['discovered_product_urls']} | {item['parsed_products']} | {item['in_stock_products']} | {item['unknown_products']} | {item['out_of_stock']} | {item['discontinued']} | {item['failed_products']} | {item['status']} |")
    lines.extend(["", "## FixtureRequirement coverage and final results", "", "| id | wide pool | availability excluded | visual rejected | in_stock final | unavailable visual final | color fallback |", "|---|---:|---:|---:|---:|---:|---|"])
    for requirement_id, stats in search_stats.items():
        lines.append(f"| {requirement_id} | {stats.get('wide_candidates_considered', 0)} | {stats.get('excluded_availability', 0)} | {stats.get('visual_rejected', stats.get('rejected_by_visual', 0))} | {len(shortlisted.get(requirement_id, []))} | {len(unavailable_shortlisted.get(requirement_id, []))} | {'да' if stats.get('color_fallback_used') else 'нет'} |")
    lines.extend(["", "### Availability diagnostic", "", "| id | in_stock visual | out_of_stock visual | preorder visual | expected visual | check_availability visual | discontinued rejected | visual rejected |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for requirement_id, stats in search_stats.items():
        lines.append(f"| {requirement_id} | {stats.get('in_stock_visual_finalists', 0)} | {stats.get('out_of_stock_visual_finalists', 0)} | {stats.get('preorder_visual_finalists', 0)} | {stats.get('expected_visual_finalists', 0)} | {stats.get('check_availability_visual_finalists', 0)} | {stats.get('discontinued_rejected', 0)} | {stats.get('visual_rejected', 0)} |")
    mode_names = sorted({str(item.get("availability_mode", "stock_tracked")) for item in supplier_stats})
    not_published_suppliers = [item["supplier"] for item in supplier_stats if item.get("availability_mode") == "stock_not_published"]
    lines.extend([
        "",
        "## Comparison with previous V2",
        "",
        f"- Каталог: `206 -> {count}`; FixtureRequirement: `8 -> {len(shortlisted)}`; основные финальные кандидаты: `1 -> {sum(len(items) for items in shortlisted.values())}`; недоступные визуальные финалисты: `{sum(len(items) for items in unavailable_shortlisted.values())}`.",
        f"- Проверенные supplier modes в текущем списке: `{', '.join(mode_names) or 'нет'}`.",
        f"- Новые пулы по `stock_not_published`: `{len(not_published_suppliers)}` supplier(s) ({', '.join(not_published_suppliers) or 'нет'}).",
        "- Новых визуально сильных аналогов в sample не появилось; недоступные/архивные товары в финал не вернулись.",
        "",
        "## Product decision",
        "",
        "Для stock_tracked в подбор попадает только `in_stock`. Для stock_not_published отсутствие статуса допускается, но явные отрицательные маркеры (нет в наличии, архив, под заказ, ожидается, уточнение наличия и аналоги) по-прежнему исключаются. Оба режима проходят live recheck.",
        "",
        "Если по позиции нет достойного кандидата, отчёт показывает: `Ничего не найдено. Попробуйте подобрать вручную.`",
        "",
    ])
    return "\n".join(lines)
