# LumiMatch Codex

Помощник для подбора светильников по дизайн-проектам. Проект рассчитан на работу **через Codex как агента**, без отдельного OpenAI API и без `OPENAI_API_KEY`.

## Как запустить

Локальное `.venv` проекта используется без глобального Python. Если окружение отсутствует или изменился `requirements.txt`, выполните:

```powershell
.\setup.ps1
```

Скрипт использует существующее `.venv`, устанавливает/обновляет зависимости из `requirements.txt` и ставит Chromium для Playwright. Если `.venv` вдруг отсутствует, скрипт сможет создать его сам.

После установки полный прогон на реальных sample PDF запускается так:

```powershell
.\.venv\Scripts\python.exe -m lumimatch sample-run
```

Команда выполняет bounded-аудит поставщиков, обновляет локальный SQLite-каталог и кэш фотографий, читает `samples/Dan_dia-2.pdf` и `samples/Dan_vis.pdf`, строит shortlist и сохраняет Markdown/HTML/JSON в `output/`.

Отдельные этапы:

```powershell
.\.venv\Scripts\python.exe -m lumimatch audit
.\.venv\Scripts\python.exe -m lumimatch collect --max-pages 28
.\.venv\Scripts\python.exe -m lumimatch shortlist --requirements data/fixture_requirements.json --top-n 80
```

В `data/visual_review.json` хранится ручная визуальная проверка Codex. Для sample V2 широкие pools и contact sheets находятся в `output/review/<requirement>/`; явный reject никогда не остаётся в финальном отчёте. Если хороших вариантов нет, отчёт намеренно показывает `Ничего не найдено. Попробуйте подобрать вручную.`.

`requirements.txt` — стартовый список зависимостей MVP. Codex может менять его по мере реализации, но зависимости должны устанавливаться только в локальное `.venv`.

## Что уже внутри

- `AGENTS.md` — постоянные правила проекта для Codex.
- `TASK.md` — исходная задача и критерии готовности.
- `WORKFLOW.md` — целевой сценарий работы после первого запуска.
- `suppliers.txt` — разрешённые сайты поставщиков.
- `samples/Dan_dia-2.pdf` — техническая часть дизайн-проекта.
- `samples/Dan_vis.pdf` — визуализации.
- `requirements.txt` — стартовые Python-зависимости.
- `setup.ps1` — установка зависимостей в локальное `.venv`.
- `data/catalog/` — локальные данные каталога.
- `data/supplier_availability.json` — вручную проверенная capability наличия по каждому разрешённому поставщику.
- `output/` — результаты подборов.
- `docs/` — аудит поставщиков и технические заметки.
- `lumimatch/` — модели, HTTP-first discovery/collector, консервативный extractor, availability/taxonomy gates, SQLite/FTS индекс, PDF/reference crops, contact sheets, visual review и отчёты.
- `tests/` — unit-тесты извлечения, discovery и shortlist.

## Важно

AI-часть выполняет сам Codex в рамках своей сессии и подписки. Не подключать OpenAI API только ради vision/LLM.

Python-скрипты нужны для рутинной работы: обход каталогов, извлечение карточек, скачивание фото, локальный индекс, фильтрация, кэширование и формирование отчёта.

Перед финалом система повторно открывает публичную карточку без кэша. Для `stock_tracked` требуется актуальная `in_stock`; для вручную проверенного `stock_not_published` отсутствие статуса допускается, но проверяются URL, SKU и отсутствие явных негативных маркеров. В отчёте такой товар помечается `Поставщик не публикует остатки`, а не подтверждённым наличием.

Если в будущем понадобится полностью автономная программа, которой пользуются без Codex, это будет отдельная задача.
