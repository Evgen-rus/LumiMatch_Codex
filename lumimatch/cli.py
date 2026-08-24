"""Typer CLI for the local end-to-end workflow."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .audit import audit_all, write_audit
from .collector import CatalogCollector
from .models import FixtureRequirement, ScoredCandidate
from .paths import OUTPUT, ensure_dirs
from .pdf_project import inspect_project, render_pages
from .report import write_reports
from .scoring import apply_visual_review, shortlist
from .storage import CatalogStore

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _suppliers(path: Path, value: str | None) -> list[str]:
    if value:
        wanted = {part.strip().lower() for part in value.split(",") if part.strip()}
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
            and line.strip().rstrip("/").lower().replace("https://", "")
            in {item.replace("https://", "") for item in wanted}
        ]
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _requirements(path: Path) -> list[FixtureRequirement]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [FixtureRequirement.model_validate(item) for item in payload]


def _apply_sample_visual_review(
    shortlisted: dict[str, list[ScoredCandidate]],
    review_path: Path = Path("data/visual_review.json"),
) -> dict[str, list[ScoredCandidate]]:
    if not review_path.exists():
        return shortlisted
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    for requirement_id, candidates in shortlisted.items():
        requirement_reviews = payload.get(requirement_id, {})
        for index, candidate in enumerate(candidates):
            key = candidate.product.sku or candidate.product.source_url
            review = requirement_reviews.get(key)
            if isinstance(review, dict):
                candidates[index] = apply_visual_review(candidate, review)
    return shortlisted


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
    suppliers: str | None = typer.Option(
        None, help="Домены через запятую; по умолчанию все разрешённые сайты."
    ),
    max_pages: int = typer.Option(30, min=1, max=500),
    no_images: bool = typer.Option(
        False, help="Не скачивать локальные копии фотографий."
    ),
) -> None:
    """Collect/update local SQLite catalogue."""
    ensure_dirs()
    store = CatalogStore()
    collector = CatalogCollector(store)
    results = collector.collect(
        _suppliers(suppliers_file, suppliers), max_pages, not no_images
    )
    removed = collector.refresh_cached()
    for result in results:
        typer.echo(
            f"{result.supplier}: pages={result.pages_visited}, products={result.products_found}, images={result.images_saved}, errors={len(result.errors)}"
        )
    typer.echo(
        f"Всего карточек в SQLite: {store.count()}; удалено категорий: {removed}"
    )


@app.command("shortlist")
def shortlist_command(
    requirements: Path = typer.Option(  # noqa: B008
        Path("data/fixture_requirements.json"), exists=True
    ),
    output: Path = typer.Option(Path("data/shortlist.json")),  # noqa: B008
    top_n: int = typer.Option(5, min=1, max=10),
) -> None:
    """Build deterministic shortlists from the local catalogue."""
    store = CatalogStore()
    products = store.all()
    if not products:
        raise typer.BadParameter("Каталог пуст. Сначала выполните collect.")
    result: dict[str, list[dict[str, object]]] = {}
    for requirement in _requirements(requirements):
        result[requirement.id] = [
            candidate.model_dump(mode="json")
            for candidate in shortlist(requirement, products, top_n)
        ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    typer.echo(f"Shortlist сохранён: {output}")


@app.command("sample-run")
def sample_run(
    max_pages: int = typer.Option(28, min=1, max=100),
    top_n: int = typer.Option(5, min=1, max=10),
    skip_audit: bool = typer.Option(False, help="Не повторять аудит поставщиков."),
) -> None:
    """Run the complete workflow on the two real sample PDFs."""
    ensure_dirs()
    pdf_paths = [Path("samples/Dan_dia-2.pdf"), Path("samples/Dan_vis.pdf")]
    inspect_project(pdf_paths, Path("data/pdf_extraction.json"))
    render_dir = OUTPUT / "sample_references"
    references = {
        "Dan_dia-2.pdf": [10, 11, 14, 15, 16, 17, 18, 19],
        "Dan_vis.pdf": [1, 11, 18, 23, 25, 27, 29, 30],
    }
    for name, pages in references.items():
        rendered = render_pages(Path("samples") / name, pages, render_dir, scale=1.0)
        typer.echo(f"Рендеры {name}: {len(rendered)}")
    if not skip_audit:
        audits = audit_all(_suppliers(Path("suppliers.txt"), None))
        write_audit("docs/SUPPLIER_AUDIT.md", audits)
    selected = (
        "artelamp.ru,citilux.ru,lightstar.ru,maytoni.ru,divinare.ru,shop.lussole.ru"
    )
    store = CatalogStore()
    collector = CatalogCollector(store)
    results = collector.collect(
        _suppliers(Path("suppliers.txt"), selected), max_pages, True
    )
    removed = collector.refresh_cached()
    for result in results:
        typer.echo(
            f"{result.supplier}: pages={result.pages_visited}, products={result.products_found}, images={result.images_saved}, errors={len(result.errors)}"
        )
    requirements = _requirements(Path("data/fixture_requirements.json"))
    products = store.all()
    shortlisted: dict[str, list[ScoredCandidate]] = {
        requirement.id: shortlist(requirement, products, top_n)
        for requirement in requirements
    }
    shortlisted = _apply_sample_visual_review(shortlisted)
    write_reports(requirements, shortlisted, OUTPUT, "lumimatch_sample")
    Path("data/shortlist.json").write_text(
        json.dumps(
            {
                key: [item.model_dump(mode="json") for item in value]
                for key, value in shortlisted.items()
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    Path("docs/SAMPLE_RUN.md").write_text(
        _sample_run_note(results, store.count(), shortlisted), encoding="utf-8"
    )
    typer.echo(
        f"Sample run завершён. Карточек в каталоге: {store.count()}; удалено категорий: {removed}; требования: {len(requirements)}"
    )


def _sample_run_note(
    results: list[object], count: int, shortlisted: dict[str, list[ScoredCandidate]]
) -> str:
    lines = [
        "# SAMPLE_RUN",
        "",
        "Запущен `python -m lumimatch sample-run` на `samples/Dan_dia-2.pdf` и `samples/Dan_vis.pdf`.",
        "",
        f"- FixtureRequirement: `{len(shortlisted)}`",
        f"- карточек в локальном SQLite после запуска: `{count}`",
        "- PDF metadata/text cache: `data/pdf_extraction.json`",
        "- reference renders: `output/sample_references/`",
        "- machine source: `output/lumimatch_sample.json`",
        "- reports: `output/lumimatch_sample.md` и `output/lumimatch_sample.html`",
        "- Codex visual review input: `data/visual_review.json`",
        "",
        "## Коллекторы",
        "",
    ]
    for result in results:
        lines.append(
            f"- `{result.supplier}`: pages={result.pages_visited}, products={result.products_found}, images={result.images_saved}, errors={len(result.errors)}"
        )
    lines.extend(
        [
            "",
            "## Ограничения",
            "",
            "Итоговый визуальный класс является предварительным: фотографии кандидатов нужно просмотреть в HTML и подтвердить вручную в Codex. Поля, которых нет на публичной карточке, помечены как неизвестные.",
            "",
        ]
    )
    return "\n".join(lines)
