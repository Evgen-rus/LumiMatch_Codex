"""Machine-readable and human-readable customer-facing result reports."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .availability import (
    availability_label,
    diagnostic_availability_label,
    effective_availability_status,
    supplier_availability_mode,
)
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
    mode = supplier_availability_mode(candidate.product.supplier)
    value["availability_mode"] = mode
    value["availability_label"] = availability_label(effective_availability_status(candidate.product), mode)
    return value


def _unavailable_candidate_dict(candidate: ScoredCandidate, output_dir: Path) -> dict[str, object]:
    value = _candidate_dict(candidate, output_dir)
    value["availability_label"] = diagnostic_availability_label(effective_availability_status(candidate.product))
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
            "Основной пользовательский отчёт содержит только подтверждённые in_stock товары; supplier capability не ослабляет этот customer-facing gate.",
            "Товары без визуального подтверждения Codex и отклонённые по визуальному несоответствию не показываются.",
        ],
    }
    json_path = output_dir / f"{stem}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown: list[str] = [
        "# LumiMatch - подбор по sample V2",
        "",
        "В основной подборке показываются только подтверждённые in_stock товары, прошедшие hard filters, визуальный screening Codex и live availability recheck.",
        "",
    ]
    html_parts = [
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>LumiMatch sample V2</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:1380px;margin:30px auto;color:#202124;background:#fafafa}h1{margin-bottom:8px}.muted{color:#5f6368}.req{border-top:3px solid #202124;padding:26px 0}.context{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.context img{width:250px;height:170px;object-fit:contain;background:#fff;border:1px solid #ddd}.stats{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px;margin:12px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px}.card{border:1px solid #d9d9d9;border-radius:10px;padding:14px;background:#fff}.card img{width:100%;height:240px;object-fit:contain;background:#f3f4f6}.tag{display:inline-block;background:#e8f0fe;border-radius:5px;padding:3px 7px;margin:2px}.alternative{background:#fff4e5}.score{font-size:20px;font-weight:bold}.empty{border:1px dashed #9aa0a6;background:#fff;padding:18px;border-radius:8px;font-weight:bold}.diff{color:#7a3e00}</style></head><body>",
        "<h1>LumiMatch - подбор по sample V2</h1>",
        "<p class='muted'>Поставщики ограничены списком suppliers.txt. Этот основной отчёт намеренно содержит только подтверждённые <code>in_stock</code>; отдельная диагностика временно недоступных визуальных кандидатов вынесена в соседний отчёт.</p>",
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
                f"- Наличие: `{availability_label(effective_availability_status(product), supplier_availability_mode(product.supplier))}`; режим поставщика: `{supplier_availability_mode(product.supplier)}`; цена: `{product.price or 'не опубликована'} {product.currency or ''}`",
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
                f"<p><b>Поставщик:</b> {html.escape(product.supplier)}<br><b>Артикул:</b> {html.escape(product.sku or 'не извлечён')}<br><b>Наличие:</b> {html.escape(availability_label(effective_availability_status(product), supplier_availability_mode(product.supplier)))}<br><b>Режим поставщика:</b> {html.escape(supplier_availability_mode(product.supplier))}<br><b>Цена:</b> {html.escape(str(product.price or 'не опубликована'))} {html.escape(product.currency or '')}</p>",
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


def write_unavailable_report(
    requirements: list[FixtureRequirement],
    results: dict[str, list[ScoredCandidate]],
    output_dir: Path,
    stem: str = "lumimatch_sample_unavailable",
    *,
    search_stats: dict[str, dict[str, object]] | None = None,
    rejected: dict[str, list[ScoredCandidate]] | None = None,
) -> tuple[Path, Path, Path]:
    """Write the independent visual-quality diagnostic report.

    The caller has already applied the normal taxonomy, mounting, dimension,
    visual-threshold and Codex-review gates. This report differs only in that
    it accepts the four temporary-unavailability statuses and explicitly
    keeps them out of the customer-facing report.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    search_stats = search_stats or {}
    rejected = rejected or {}
    records: list[dict[str, object]] = []
    for requirement in requirements:
        records.append(
            {
                "requirement": requirement.model_dump(mode="json"),
                "search_stats": search_stats.get(requirement.id, {}),
                "candidates": [_unavailable_candidate_dict(candidate, output_dir) for candidate in results.get(requirement.id, [])],
                "rejected_candidates": [_unavailable_candidate_dict(candidate, output_dir) for candidate in rejected.get(requirement.id, [])],
            }
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requirements": records,
        "notes": [
            "Это независимый диагностический отчёт: в него попадают только out_of_stock, preorder, expected и check_availability.",
            "unknown, discontinued, архивные и снятые с производства товары полностью исключены.",
            "Каждый показанный кандидат прошёл те же taxonomy, mounting, dimension, visual threshold, structural similarity, visual reject и live recheck gates, что и основной отчёт.",
            "В основной подборке не показан только из-за текущего статуса наличия.",
        ],
    }
    json_path = output_dir / f"{stem}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown: list[str] = [
        "# LumiMatch - визуально подходящие, но сейчас недоступны",
        "",
        "Диагностический отчёт качества visual matching. Он не заменяет основной отчёт и не ослабляет его строгую политику: здесь временно показываются только `out_of_stock`, `preorder`, `expected` и `check_availability`.",
        "",
    ]
    html_parts = [
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>LumiMatch - визуально подходящие, но сейчас недоступны</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:1380px;margin:30px auto;color:#202124;background:#fafafa}h1{margin-bottom:8px}.muted{color:#5f6368}.req{border-top:3px solid #7a3e00;padding:26px 0}.context{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.context img{width:250px;height:170px;object-fit:contain;background:#fff;border:1px solid #ddd}.stats{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px;margin:12px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px}.card{border:2px solid #c47c28;border-radius:10px;padding:14px;background:#fff}.card img{width:100%;height:240px;object-fit:contain;background:#f3f4f6}.tag{display:inline-block;background:#fff0d8;border-radius:5px;padding:3px 7px;margin:2px}.availability{font-size:18px;font-weight:bold;color:#9b3d00}.score{font-size:20px;font-weight:bold}.empty{border:1px dashed #9aa0a6;background:#fff;padding:18px;border-radius:8px;font-weight:bold}.diff{color:#7a3e00}</style></head><body>",
        "<h1>LumiMatch - визуально подходящие, но сейчас недоступны</h1>",
        "<p class='muted'>Диагностика retrieval и visual matching. Основной пользовательский отчёт по-прежнему содержит только подтверждённые <code>in_stock</code> товары. <code>unknown</code>, discontinued и архивные статусы сюда не попадают.</p>",
    ]
    for requirement in requirements:
        stats = search_stats.get(requirement.id, {})
        candidates = results.get(requirement.id, [])
        crop_refs = [_relative_reference(path, output_dir) for path in requirement.reference_crop_paths]
        context_refs = [_relative_reference(path, output_dir) for path in requirement.reference_image_paths]
        refs = [ref for ref in crop_refs + context_refs if ref]
        stats_text = (
            f"in_stock visual finalists: {stats.get('in_stock_visual_finalists', 0)}; "
            f"out_of_stock: {stats.get('out_of_stock_visual_finalists', 0)}; "
            f"preorder: {stats.get('preorder_visual_finalists', 0)}; "
            f"expected: {stats.get('expected_visual_finalists', 0)}; "
            f"check_availability: {stats.get('check_availability_visual_finalists', 0)}; "
            f"discontinued rejected: {stats.get('discontinued_rejected', 0)}; "
            f"visual rejected: {stats.get('visual_rejected', 0)}"
        )
        markdown.extend([
            f"## {requirement.id}: {requirement.room} - {requirement.fixture_type}",
            "",
            f"**Распознано:** {requirement.visual_description}",
            f"**Источники:** {', '.join(requirement.source_pages)}; уверенность {requirement.confidence:.2f}.",
            f"**Диагностика:** {stats_text}",
            "",
        ])
        html_parts.append(f"<section class='req'><h2>{html.escape(requirement.id)}: {html.escape(requirement.room)} - {html.escape(requirement.fixture_type)}</h2>")
        html_parts.append(f"<p><b>Распознано:</b> {html.escape(requirement.visual_description)}<br><b>Источники:</b> {html.escape(', '.join(requirement.source_pages))}</p>")
        if refs:
            html_parts.append("<div class='context'>" + "".join(f"<img src='{html.escape(ref, quote=True)}' alt='Референс'>" for ref in refs) + "</div>")
        html_parts.append(f"<div class='stats'><b>Диагностика:</b> {html.escape(stats_text)}</div>")
        if not candidates:
            markdown.extend(["Ничего не найдено. Это означает, что после снятия только availability gate достойного визуального аналога в разрешённых временных статусах нет.", ""])
            html_parts.append("<div class='empty'>Ничего не найдено. После снятия только availability gate достойного визуального аналога нет.</div>")
        else:
            html_parts.append("<div class='cards'>")
        for index, candidate in enumerate(candidates, start=1):
            product = candidate.product
            status = effective_availability_status(product)
            label = diagnostic_availability_label(status)
            image_reference = _image_reference(candidate, output_dir)
            image_html = f"<img src='{html.escape(image_reference, quote=True)}' alt='Фото товара'>" if image_reference else "<div class='muted'>Фото товара не извлечено</div>"
            markdown.extend([
                f"### {index}. {product.name} ({candidate.result_class})",
                f"- Поставщик: `{product.supplier}`; SKU: `{product.sku or 'не извлечён'}`",
                f"- URL: [{product.source_url}]({product.source_url})",
                f"- Availability: `{status}` — **{label}**; цена: `{product.price or 'не опубликована'} {product.currency or ''}`",
                f"- Оценки: visual `{candidate.visual_similarity:.2f}`, overall `{candidate.overall_score:.2f}`, type `{candidate.type_match:.2f}`, dimensions `{candidate.dimension_match:.2f}`, technical `{candidate.technical_match:.2f}`",
                f"- Почему визуально подходит: {candidate.fit_explanation}",
                f"- Существенные отличия: {', '.join(candidate.differences) or 'не выявлены'}",
                "- В основной подборке не показан только из-за текущего статуса наличия.",
                "",
            ])
            link = html.escape(product.source_url, quote=True)
            html_parts.extend([
                "<article class='card'>", image_html,
                f"<h3>{index}. {html.escape(product.name)}</h3><span class='tag'>{html.escape(product.product_family or 'unknown')}</span> <span class='score'>{candidate.visual_similarity:.2f}</span>",
                f"<p><b>Поставщик:</b> {html.escape(product.supplier)}<br><b>SKU:</b> {html.escape(product.sku or 'не извлечён')}<br><span class='availability'>{html.escape(label)}</span><br><b>Статус:</b> {html.escape(status)}<br><b>Цена:</b> {html.escape(str(product.price or 'не опубликована'))} {html.escape(product.currency or '')}</p>",
                f"<p><b>Оценки:</b> visual {candidate.visual_similarity:.2f}; overall {candidate.overall_score:.2f}; type {candidate.type_match:.2f}; dimensions {candidate.dimension_match:.2f}; technical {candidate.technical_match:.2f}</p>",
                f"<p><b>Почему визуально подходит:</b> {html.escape(candidate.fit_explanation)}</p><p class='diff'><b>Существенные отличия:</b> {html.escape(', '.join(candidate.differences) or 'не выявлены')}</p>",
                "<p><b>В основной подборке не показан только из-за текущего статуса наличия.</b></p>",
                f"<p><a href='{link}'>Открыть карточку поставщика</a></p>",
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
        rejected_payload = {key: [_unavailable_candidate_dict(item, output_dir) for item in value] for key, value in rejected.items()}
        (debug_dir / "unavailable_rejected_candidates.json").write_text(json.dumps(rejected_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, markdown_path, html_path
