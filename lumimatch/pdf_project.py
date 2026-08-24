"""PDF metadata extraction and reference-page rendering for the Codex workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf


def inspect_pdf(path: Path) -> dict[str, Any]:
    document = pymupdf.open(path)
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(document):
        text = " ".join(page.get_text().split())
        pages.append(
            {
                "page": index + 1,
                "text_chars": len(text),
                "text_preview": text[:500],
                "embedded_images": len(page.get_images(full=True)),
            }
        )
    return {
        "file": str(path),
        "page_count": document.page_count,
        "metadata": document.metadata,
        "pages": pages,
    }


def inspect_project(paths: list[Path], output_path: Path) -> dict[str, Any]:
    result = {"files": [inspect_pdf(path) for path in paths]}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def render_pages(
    pdf_path: Path, page_numbers: list[int], output_dir: Path, scale: float = 1.4
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(pdf_path)
    rendered: list[str] = []
    for page_number in page_numbers:
        if page_number < 1 or page_number > document.page_count:
            continue
        target = output_dir / f"{pdf_path.stem}_p{page_number:02d}.png"
        if not target.exists():
            pixmap = document[page_number - 1].get_pixmap(
                matrix=pymupdf.Matrix(scale, scale), alpha=False
            )
            pixmap.save(target)
        rendered.append(str(target))
    return rendered
