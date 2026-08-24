"""Contact-sheet preparation for Codex visual screening."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .models import FixtureRequirement, ScoredCandidate


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_contact_sheets(
    requirement: FixtureRequirement,
    candidates: list[ScoredCandidate],
    output_root: Path,
    *,
    per_sheet: int = 20,
    columns: int = 5,
) -> list[Path]:
    """Create review sheets and a manifest without deciding visual similarity."""
    review_dir = output_root / requirement.id
    review_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    sheets: list[Path] = []
    tile_width, image_height, label_height = 230, 190, 72
    rows = (per_sheet + columns - 1) // columns
    for offset in range(0, len(candidates), per_sheet):
        group = candidates[offset : offset + per_sheet]
        sheet_index = offset // per_sheet + 1
        sheet = Image.new("RGB", (columns * tile_width, rows * (image_height + label_height)), "white")
        draw = ImageDraw.Draw(sheet)
        for local_index, candidate in enumerate(group):
            number = offset + local_index + 1
            x = (local_index % columns) * tile_width
            y = (local_index // columns) * (image_height + label_height)
            image_path = Path(candidate.product.local_image_path) if candidate.product.local_image_path else None
            if image_path and image_path.exists():
                try:
                    image = Image.open(image_path).convert("RGB")
                    image = ImageOps.contain(image, (tile_width - 12, image_height - 12))
                    paste_x = x + (tile_width - image.width) // 2
                    paste_y = y + (image_height - image.height) // 2
                    sheet.paste(image, (paste_x, paste_y))
                except OSError:
                    draw.rectangle((x + 6, y + 6, x + tile_width - 6, y + image_height - 6), outline="#cc0000", width=2)
            else:
                draw.rectangle((x + 6, y + 6, x + tile_width - 6, y + image_height - 6), outline="#999999", width=2)
                draw.text((x + 28, y + 85), "нет фото", fill="#666666", font=_font(18))
            label = f"{number}. {candidate.product.supplier} / {candidate.product.sku or '?'}\n{candidate.product.name}"
            for line_index, line in enumerate(textwrap.wrap(label, width=32)[:3]):
                draw.text((x + 6, y + image_height + 4 + line_index * 19), line, fill="#202124", font=_font(14))
            manifest.append({
                "number": number,
                "requirement_id": requirement.id,
                "supplier": candidate.product.supplier,
                "sku": candidate.product.sku,
                "name": candidate.product.name,
                "source_url": candidate.product.source_url,
                "local_image_path": candidate.product.local_image_path,
                "color_mode": candidate.color_mode,
                "sheet": f"sheet_{sheet_index:02d}.jpg",
            })
        target = review_dir / f"sheet_{sheet_index:02d}.jpg"
        sheet.save(target, quality=92)
        sheets.append(target)
    (review_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return sheets
