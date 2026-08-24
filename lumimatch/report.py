"""Machine-readable and human-readable result reports."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .models import FixtureRequirement, ScoredCandidate


def _image_reference(candidate: ScoredCandidate, output_dir: Path) -> str | None:
    local = candidate.product.local_image_path
    if local and Path(local).exists():
        return os.path.relpath(local, output_dir).replace("\\", "/")
    return candidate.product.primary_image_url


def _candidate_dict(candidate: ScoredCandidate, output_dir: Path) -> dict[str, object]:
    value = candidate.model_dump(mode="json")
    value["image_reference"] = _image_reference(candidate, output_dir)
    return value


def write_reports(
    requirements: list[FixtureRequirement],
    results: dict[str, list[ScoredCandidate]],
    output_dir: Path,
    stem: str = "lumimatch_sample",
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for requirement in requirements:
        records.append(
            {
                "requirement": requirement.model_dump(mode="json"),
                "candidates": [
                    _candidate_dict(candidate, output_dir)
                    for candidate in results.get(requirement.id, [])
                ],
            }
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requirements": records,
        "notes": [
            "Структурированный shortlist рассчитан локальным алгоритмом без AI API.",
            "visual_similarity и итоговый класс требуют проверки Codex по настоящим фото кандидатов; неизвестные поля не заполняются догадками.",
        ],
    }
    json_path = output_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    markdown: list[str] = [
        "# LumiMatch - подбор по sample",
        "",
        "Это shortlist для ручной визуальной проверки Codex. Публичные карточки и фотографии взяты только с поставщиков из `suppliers.txt`.",
        "",
    ]
    html_parts = [
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>LumiMatch sample</title>",
        (
            "<style>body{font-family:Arial,sans-serif;max-width:1200px;margin:32px auto;color:#202124}"
            ".req{border-top:2px solid #202124;padding:24px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}"
            ".card{border:1px solid #d9d9d9;border-radius:8px;padding:14px}.card img{width:100%;height:220px;object-fit:contain;background:#f5f5f5}"
            ".muted{color:#666}.score{font-size:20px;font-weight:bold}.tag{display:inline-block;background:#eef2ff;border-radius:4px;padding:3px 6px;margin:2px}</style></head><body>"
        ),
        "<h1>LumiMatch - подбор по sample</h1>",
        "<p class='muted'>Алгоритмический shortlist без внешнего LLM/API. Перед заказом проверить карточку поставщика и визуальное сходство.</p>",
    ]
    for record in records:
        requirement = record["requirement"]
        candidates = record["candidates"]
        markdown.extend(
            [
                f"## {requirement['id']}: {requirement['room']} - {requirement['fixture_type']}",
                "",
                f"**Распознано:** {requirement['visual_description']}",
                f"**Количество:** {requirement.get('quantity') or 'не указано'}; **цвет:** {requirement.get('color') or 'неизвестен'}; **монтаж:** {requirement.get('mounting') or 'неизвестен'}.",
                f"**Источники:** {', '.join(requirement.get('source_pages', []))}; уверенность {requirement['confidence']:.2f}.",
                "",
            ]
        )
        html_parts.extend(
            [
                f"<section class='req'><h2>{html.escape(str(requirement['id']))}: {html.escape(str(requirement['room']))} - {html.escape(str(requirement['fixture_type']))}</h2>",
                f"<p><b>Распознано:</b> {html.escape(str(requirement['visual_description']))}<br><b>Количество:</b> {html.escape(str(requirement.get('quantity') or 'не указано'))}; <b>цвет:</b> {html.escape(str(requirement.get('color') or 'неизвестен'))}; <b>монтаж:</b> {html.escape(str(requirement.get('mounting') or 'неизвестен'))}.<br><b>Источники:</b> {html.escape(', '.join(requirement.get('source_pages', [])))}</p>",
                "<div class='cards'>",
            ]
        )
        if not candidates:
            markdown.append("Кандидаты не найдены.")
            html_parts.append("<p>Кандидаты не найдены.</p>")
        for index, candidate in enumerate(candidates, start=1):
            product = candidate["product"]
            image_reference = candidate.get("image_reference")
            image_html = (
                f"<img src='{html.escape(str(image_reference), quote=True)}' alt='Фото товара'>"
                if image_reference
                else "<div class='muted'>Фото не извлечено</div>"
            )
            markdown.extend(
                [
                    f"### {index}. {product['name']} ({candidate['result_class']})",
                    f"- Поставщик: `{product['supplier']}`; артикул: `{product.get('sku') or 'не извлечён'}`",
                    f"- Ссылка: [{product['source_url']}]({product['source_url']})",
                    f"- Цена/наличие: `{product.get('price') or 'не опубликована'} {product.get('currency') or ''}` / `{product.get('availability') or 'не опубликовано'}`",
                    f"- Параметры: цвет `{product.get('color') or 'неизвестен'}`, материал `{product.get('material') or 'неизвестен'}`, размеры `{product.get('dimensions') or 'неизвестны'}`",
                    f"- Оценки: overall `{candidate['overall_score']:.2f}`, visual `{candidate.get('visual_similarity') if candidate.get('visual_similarity') is not None else 'не проверено'}`, type `{candidate['type_match']:.2f}`, dimensions `{candidate['dimension_match']:.2f}`, technical `{candidate['technical_match']:.2f}`",
                    f"- Почему подходит: {candidate['fit_explanation']}",
                    f"- Отличия/ограничения: {', '.join(candidate.get('differences') or ['не выявлены алгоритмически'])}",
                    "",
                ]
            )
            link = html.escape(str(product["source_url"]), quote=True)
            html_parts.extend(
                [
                    "<article class='card'>",
                    image_html,
                    f"<h3>{index}. {html.escape(str(product['name']))}</h3>",
                    f"<span class='tag'>{html.escape(str(candidate['result_class']))}</span> <span class='score'>{candidate['overall_score']:.2f}</span>",
                    f"<p><b>Поставщик:</b> {html.escape(str(product['supplier']))}<br><b>Артикул:</b> {html.escape(str(product.get('sku') or 'не извлечён'))}<br><b>Цена/наличие:</b> {html.escape(str(product.get('price') or 'не опубликована'))} {html.escape(str(product.get('currency') or ''))} / {html.escape(str(product.get('availability') or 'не опубликовано'))}</p>",
                    f"<p><b>Параметры:</b> цвет {html.escape(str(product.get('color') or 'неизвестен'))}; материал {html.escape(str(product.get('material') or 'неизвестен'))}; размеры {html.escape(str(product.get('dimensions') or 'неизвестны'))}</p>",
                    f"<p><b>Оценки:</b> visual {html.escape(str(candidate.get('visual_similarity') if candidate.get('visual_similarity') is not None else 'не проверено'))}; type {candidate['type_match']:.2f}; dimensions {candidate['dimension_match']:.2f}; technical {candidate['technical_match']:.2f}</p>",
                    f"<p>{html.escape(str(candidate['fit_explanation']))}</p><p><a href='{link}'>Открыть карточку поставщика</a></p>",
                    "</article>",
                ]
            )
        html_parts.append("</div></section>")
    html_parts.append("</body></html>")
    markdown_path = output_dir / f"{stem}.md"
    markdown_path.write_text("\n".join(markdown), encoding="utf-8")
    html_path = output_dir / f"{stem}.html"
    html_path.write_text("".join(html_parts), encoding="utf-8")
    return json_path, markdown_path, html_path
