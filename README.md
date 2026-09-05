# LumiMatch

Codex помогает продавцу подобрать светильники по техническим PDF и интерьерным визуализациям у поставщиков из `suppliers.txt`. Обычный объём — один проект в неделю, до 20 позиций. Результат — локальный HTML/Markdown/JSON с референсами, реальными товарами и объяснением различий; допустим пустой подбор.

Начало работы: [AGENTS.md](AGENTS.md) → карта ниже → нужный документ → исходники. Не загружай все документы на каждом задании.

## Карта проекта и контекста

| Задача | Что читать | Где работать / проверять |
|---|---|---|
| Запуск, окружение, проверки | [DEVELOPMENT](docs/DEVELOPMENT.md) | `setup.ps1`, `requirements.txt`, `lumimatch/cli.py`, `tests/` |
| Pipeline и контракты | [Архитектура](ARCHITECTURE.md), §§3–6 | `lumimatch/models.py`, `data/fixture_requirements.json`, `data/supplier_availability.json`, `data/visual_review.json` |
| PDF и требования | Архитектура §4.1 | `lumimatch/pdf_project.py`, `samples/Dan_dia-2.pdf`, `samples/Dan_vis.pdf`; релевантные golden evidence |
| Сбор и hydration | Архитектура §§4.2–4.4; [референс и протокол аудита](docs/REFERENCE.md); [аудит поставщиков](docs/SUPPLIER_AUDIT.md) | `audit.py`, `discovery.py`, `inventory.py`, `fetch.py`, `collector.py`, `extract.py`, `storage.py` внутри `lumimatch/`; `tests/test_discovery.py`, `tests/test_inventory.py`, `tests/test_extract.py` |
| Отбор, review, отчёты | Архитектура §§4.5–4.9 | `lumimatch/availability.py`, `taxonomy.py`, `scoring.py`, `visual_review.py`, `report.py`; `tests/test_scoring.py`, `tests/test_v2_pipeline.py` |
| Регрессии sample / golden | [SAMPLE_RUN](docs/SAMPLE_RUN.md), [GOLDEN_BENCHMARK](docs/GOLDEN_BENCHMARK.md) | `lumimatch/golden.py`, `benchmark.py`, `tests/test_golden_benchmark.py`, `output/golden/` |
| Image retrieval эксперимент | [Controlled benchmark](docs/CONTROLLED_VISUAL_BENCHMARK.md); по необходимости [ранний spike](docs/VISUAL_RETRIEVAL_SPIKE.md) | `experiments/visual_retrieval/`, `requirements-visual.txt`, `tests/test_visual_retrieval.py`, `tests/test_controlled_visual_benchmark.py` |
| История прежних ошибок | [V2_ROOT_CAUSE](docs/V2_ROOT_CAUSE.md) | Историческое обоснование, не новая спецификация |

Точная карта модулей — архитектура §5. `data/catalog/` содержит SQLite inventory/каталог; `output/review/` — contact sheets; `output/debug/` — исключения. Большие generated artifacts читать выборочно. Аудиты и benchmark-цифры являются снимками, не гарантией текущего состояния сайтов.

## Быстрый старт

```powershell
.\setup.ps1
.\.venv\Scripts\python.exe -m lumimatch --help
```

Новый проект разбирает Codex: PDF → доказательные требования → ограниченный сбор/кэш → широкий пул → визуальная проверка → live recheck → отчёт. Готовой универсальной команды, автоматически разбирающей произвольный новый PDF до финала, нет. Особенности sample и production-команд — в [DEVELOPMENT](docs/DEVELOPMENT.md).
