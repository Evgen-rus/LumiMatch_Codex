"""Machine-readable and human-readable customer-facing result reports."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .availability import availability_label
from .models import FixtureRequirement, ScoredCandidate


def _relative_reference(path: str | None, output_dir: Path) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if not candidate.exists():
        return None
    return os.path.relpath(candidate, output_dir).replace("\\", "/")


def _image_reference(candidate: ScoredCandidate, output_dir: Path) -> str | None:
    local = candidate.product.local_image_path
    return _relative_reference(local, output_dir) or candidate.product.primary_image_url


def _candidate_dict(candidate: ScoredCandidate, output_dir: Path) -> dict[str, object]:
    value = candidate.model_dump(mode="json")
    value["image_reference"] = _image_reference(candidate, output_dir)
    value["availability_label"] = availability_label(candidate.product.availability_status)
    return value


def write_reports(
    requirements: list[FixtureRequirement],
    results: dict[str, list[ScoredCandidate]],
    output_dir: Path,
    stem: str = "lumimatch_sample",
    *,
    search_stats: dict[str, dict[str, object]] | None = None,
    rejected: dict[str, list[ScoredCandidate]] | None = None,
    supplier_stats: list[dict[str, object]] | None = None,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    search_stats = search_stats or {}
    rejected = rejected or {}
    for requirement in requirements:
        records.append(
            {
                "requirement": requirement.model_dump(mode="json"),
                "search_stats": search_stats.get(requirement.id, {}),
                "candidates": [_candidate_dict(candidate, output_dir) for candidate in results.get(requirement.id, [])],
                "rejected_candidates": [_candidate_dict(candidate, output_dir) for candidate in rejected.get(requirement.id, [])],
            }
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requirements": records,
        "supplier_stats": supplier_stats or [],
        "notes": [
            "Финальная выдача содержит только товары с availability_status=in_stock и подтверждённой повторной проверкой карточки.",
            "Товары без визуального подтверждения Codex и отклонённые по визуальному несоответствию не показываются.",
        ],
    }
    json_path = output_dir / f"{stem}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown: list[str] = [
        "# LumiMatch - подбор по sample V2",
        "",
        "В подборку попадают только подтверждённо доступные товары, прошедшие hard filters, визуальный screening Codex и live availability recheck.",
        "",
    ]
    html_parts = [
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>LumiMatch sample V2</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:1380px;margin:30px auto;color:#202124;background:#fafafa}h1{margin-bottom:8px}.muted{color:#5f6368}.req{border-top:3px solid #202124;padding:26px 0}.context{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.context img{width:250px;height:170px;object-fit:contain;background:#fff;border:1px solid #ddd}.stats{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px;margin:12px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px}.card{border:1px solid #d9d9d9;border-radius:10px;padding:14px;background:#fff}.card img{width:100%;height:240px;object-fit:contain;background:#f3f4f6}.tag{display:inline-block;background:#e8f0fe;border-radius:5px;padding:3px 7px;margin:2px}.alternative{background:#fff4e5}.score{font-size:20px;font-weight:bold}.empty{border:1px dashed #9aa0a6;background:#fff;padding:18px;border-radius:8px;font-weight:bold}.diff{color:#7a3e00}</style></head><body>",
        "<h1>LumiMatch - подбор по sample V2</h1>",
        "<p class='muted'>Поставщики ограничены списком suppliers.txt. Наличие не подтверждено - товар не показывается.</p>",
    ]
    for requirement in requirements:
        record_stats = search_stats.get(requirement.id, {})
        candidates = results.get(requirement.id, [])
        crop_refs = [_relative_reference(path, output_dir) for path in requirement.reference_crop_paths]
        context_refs = [_relative_reference(path, output_dir) for path in requirement.reference_image_paths]
        crop_refs = [ref for ref in crop_refs + context_refs if ref]
        markdown.extend([
            f"## {requirement.id}: {requirement.room} - {requirement.fixture_type}",
            "",
            f"**Распознано:** {requirement.visual_description}",
            f"**Количество:** {requirement.quantity or 'не указано'}; **цвет:** {requirement.color or 'неизвестен'}; **монтаж:** {requirement.mounting or 'неизвестен'}; **family:** `{requirement.taxonomy_family or 'unknown'}`.",
            f"**Источники:** {', '.join(requirement.source_pages)}; уверенность {requirement.confidence:.2f}.",
            f"**Search stats:** {json.dumps(record_stats, ensure_ascii=False)}",
            "",
        ])
        html_parts.append(f"<section class='req'><h2>{html.escape(requirement.id)}: {html.escape(requirement.room)} - {html.escape(requirement.fixture_type)}</h2>")
        html_parts.append(f"<p><b>Распознано:</b> {html.escape(requirement.visual_description)}<br><b>Количество:</b> {html.escape(str(requirement.quantity or 'не указано'))}; <b>цвет:</b> {html.escape(str(requirement.color or 'неизвестен'))}; <b>монтаж:</b> {html.escape(str(requirement.mounting or 'неизвестен'))}; <b>family:</b> {html.escape(str(requirement.taxonomy_family or 'unknown'))}.<br><b>Источники:</b> {html.escape(', '.join(requirement.source_pages))}</p>")
        if crop_refs:
            html_parts.append("<div class='context'>" + "".join(f"<img src='{html.escape(ref, quote=True)}' alt='Референс'>" for ref in crop_refs) + "</div>")
        html_parts.append("<div class='stats'><b>Search stats:</b> " + html.escape(json.dumps(record_stats, ensure_ascii=False)) + "</div>")
        if not candidates:
            markdown.append("Ничего не найдено. Попробуйте подобрать вручную.")
            markdown.append("")
            html_parts.append("<div class='empty'>Ничего не найдено. Попробуйте подобрать вручную.</div>")
        else:
            html_parts.append("<div class='cards'>")
        for index, candidate in enumerate(candidates, start=1):
            product = candidate.product
            image_reference = _image_reference(candidate, output_dir)
            image_html = f"<img src='{html.escape(image_reference, quote=True)}' alt='Фото товара'>" if image_reference else "<div class='muted'>Фото товара не извлечено</div>"
            classes = "card alternative" if candidate.color_mode == "color_alternative" else "card"
            title = f"{index}. {product.name} ({'альтернатива по цвету' if candidate.color_mode == 'color_alternative' else candidate.result_class})"
            markdown.extend([
                f"### {title}",
                f"- Поставщик: `{product.supplier}`; артикул: `{product.sku or 'не извлечён'}`",
                f"- Ссылка: [{product.source_url}]({product.source_url})",
                f"- Наличие: `{availability_label(product.availability_status)}`; цена: `{product.price or 'не опубликована'} {product.currency or ''}`",
                f"- Параметры: цвет `{product.color or 'неизвестен'}`, размеры `{product.dimensions or 'неизвестны'}`, family `{product.product_family or 'unknown'}`",
                f"- Оценки: visual `{candidate.visual_similarity:.2f}`, overall `{candidate.overall_score:.2f}`, type `{candidate.type_match:.2f}`, dimensions `{candidate.dimension_match:.2f}`, technical `{candidate.technical_match:.2f}`",
                f"- Почему подходит: {candidate.fit_explanation}",
                f"- Отличия: {', '.join(candidate.differences) or 'не выявлены'}",
                "",
            ])
            link = html.escape(product.source_url, quote=True)
            html_parts.extend([
                f"<article class='{classes}'>", image_html,
                f"<h3>{html.escape(title)}</h3><span class='tag'>{html.escape(product.product_family or 'unknown')}</span> <span class='score'>{candidate.visual_similarity:.2f}</span>",
                f"<p><b>Поставщик:</b> {html.escape(product.supplier)}<br><b>Артикул:</b> {html.escape(product.sku or 'не извлечён')}<br><b>Наличие:</b> {html.escape(availability_label(product.availability_status))}<br><b>Цена:</b> {html.escape(str(product.price or 'не опубликована'))} {html.escape(product.currency or '')}</p>",
                f"<p><b>Параметры:</b> цвет {html.escape(product.color or 'неизвестен')}; размеры {html.escape(product.dimensions or 'неизвестны')}; family {html.escape(product.product_family or 'unknown')}</p>",
                f"<p><b>Оценки:</b> visual {candidate.visual_similarity:.2f}; overall {candidate.overall_score:.2f}; type {candidate.type_match:.2f}; dimensions {candidate.dimension_match:.2f}; technical {candidate.technical_match:.2f}</p>",
                f"<p>{html.escape(candidate.fit_explanation)}</p><p class='diff'>{html.escape(', '.join(candidate.differences) or 'Отличия не выявлены')}</p><p><a href='{link}'>Открыть карточку поставщика</a></p>",
                "</article>",
            ])
        if candidates:
            html_parts.append("</div>")
        html_parts.append("</section>")
    html_parts.append("</body></html>")
    markdown_path = output_dir / f"{stem}.md"
    markdown_path.write_text("\n".join(markdown), encoding="utf-8")
    html_path = output_dir / f"{stem}.html"
    html_path.write_text("".join(html_parts), encoding="utf-8")
    if rejected:
        debug_dir = output_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        rejected_payload: dict[str, list[dict[str, Any]]] = {key: [_candidate_dict(item, output_dir) for item in value] for key, value in rejected.items()}
        (debug_dir / "rejected_candidates.json").write_text(json.dumps(rejected_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, markdown_path, html_path
