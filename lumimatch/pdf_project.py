"""PDF metadata extraction and reference-page rendering for the Codex workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image


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


SAMPLE_CROP_SPECS: dict[str, list[tuple[str, tuple[int, int, int, int]]]] = {
    "F-01": [("Dan_vis_p01.png", (100, 0, 900, 330))],
    "F-02": [("Dan_vis_p11.png", (120, 0, 1050, 280)), ("Dan_vis_p23.png", (250, 0, 900, 300))],
    "F-03": [("Dan_vis_p11.png", (260, 330, 900, 650))],
    "F-04": [("Dan_vis_p18.png", (180, 240, 1000, 650))],
    "F-05": [("Dan_vis_p27.png", (250, 210, 680, 600)), ("Dan_vis_p29.png", (260, 210, 700, 600))],
    "F-06": [("Dan_vis_p29.png", (120, 0, 1050, 260))],
    "F-07": [("Dan_vis_p11.png", (100, 0, 1050, 260))],
    "F-08": [("Dan_vis_p23.png", (250, 0, 900, 330))],
}


def create_sample_reference_crops(
    requirements: list[object], render_dir: Path, output_root: Path
) -> list[object]:
    """Create simple, inspectable crops for the known sample visual references."""
    for requirement in requirements:
        specs = SAMPLE_CROP_SPECS.get(getattr(requirement, "id", ""), [])
        crop_paths: list[str] = []
        target_dir = output_root / getattr(requirement, "id", "unknown")
        target_dir.mkdir(parents=True, exist_ok=True)
        for index, (filename, box) in enumerate(specs, start=1):
            source = render_dir / filename
            if not source.exists():
                continue
            try:
                with Image.open(source) as image:
                    left, top, right, bottom = box
                    bounded = (max(0, left), max(0, top), min(image.width, right), min(image.height, bottom))
                    target = target_dir / f"reference_{index:02d}.png"
                    image.crop(bounded).save(target)
                    crop_paths.append(str(target))
            except OSError:
                continue
        if crop_paths:
            requirement.reference_crop_paths = crop_paths
    return requirements
