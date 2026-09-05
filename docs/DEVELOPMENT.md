# Разработка и проверка

## Окружение и команды

Все команды — PowerShell из корня. Python 3.12+, только локальная `.venv`, без глобального pip. `setup.ps1` создаёт окружение, проверяет версию, устанавливает `requirements.txt` и Chromium. Если launcher выбрал старый Python, создай `.venv` подходящим Python 3.12+; глобальную конфигурацию не меняй.

```powershell
.\setup.ps1
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m lumimatch --help
.\.venv\Scripts\python.exe -m playwright install chromium
```

Последняя команда нужна только для установки/восстановления browser fallback. Не добавляй библиотеки заранее. Экспериментальные зависимости перечислены отдельно в `requirements-visual.txt`; старые benchmark-команды используют существующую локальную `.venv-visual` как историческое окружение. Новые установки по умолчанию выполняй в `.venv`, не глобально; не устанавливай visual-стек для production/docs-задач.

| Действие | Команда после `.\.venv\Scripts\python.exe -m` | Побочные эффекты |
|---|---|---|
| Аудит | `lumimatch audit` | Сеть, перезапись `docs/SUPPLIER_AUDIT.md` |
| Прежний ограниченный сбор | `lumimatch collect --max-pages 30` | Сеть, локальный каталог/кэш |
| Inventory + hydration | `lumimatch production-build --max-pages 180 --supplier-budget 30` | Сеть, production SQLite, `output/production_*`; не создаёт готовый клиентский отчёт |
| Широкий пул | `lumimatch shortlist --top-n 80` | Читает стандартный каталог, пишет `data/shortlist.json`; не заменяет visual review |
| Sample workflow | `lumimatch sample-run --skip-audit --max-pages 28 --pool-size 80` | Сеть, PDF render, сбор, сохранённый review, live recheck; перезаписывает требования, sample/review/debug и `docs/SAMPLE_RUN.md` |
| Golden sheets | `lumimatch golden-review-init --limit 100` | Пишет sheets и pending review; не запускать поверх ценного review без сохранения evidence |
| Golden метрики | `lumimatch golden-benchmark` | Читает готовые golden/discovery/inventory/hydration/review, пишет benchmark |

Перед нестандартным запуском смотри `<команда> --help` и реальные входы. `--fresh` / `--fresh-inventory` у production-build удаляют выбранные SQLite: не использовать ради обычной проверки. `golden-prepare` и `golden-discovery` нужны только golden-контуру, не production selection.

`sample-run` вызывает прежний `CatalogCollector.collect`, а не `production-build`, и применяет уже сохранённый `data/visual_review.json`. Новые/изменившиеся карточки требуют отдельной визуальной проверки Codex. Один успешный CLI-запуск не доказывает завершённый review или качество нового проекта.

## Проверки по риску

| Изменение | Минимальная проверка |
|---|---|
| Только документация | Локальные ссылки, реальные CLI options через `--help`, UTF-8, `git diff --check`, итоговый diff; без сетевого sample |
| Локальная логика | Соответствующий `tests/test_*.py`, критичные callers и один релевантный smoke/sample |
| Контракты/availability/scoring/report | `tests/test_scoring.py`, `tests/test_v2_pipeline.py` плюс тесты затронутой стадии; проверить основной/unavailable результат и reject |
| Inventory/extraction/PDF | Тесты стадии, реальные ограниченные входы; для PDF — sample и golden evidence; для сбора — живые страницы затронутых поставщиков |
| Сквозной pipeline | Полный production test suite, реальный sample и при необходимости stage benchmark; Codex visual review не пропускать |

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_scoring.py -q
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check lumimatch/scoring.py
.\.venv\Scripts\python.exe -m mypy lumimatch/scoring.py
git diff --check
```

Ruff/mypy установлены в requirements, но отдельной repo-конфигурации lint/typecheck и CI gate нет: выбирай затронутые файлы, отличай прежние ошибки от регрессий. Отдельных package build, frontend build и deploy-команд нет; `production-build` собирает каталог, не приложение. Не создавай инфраструктуру ради этих названий.

После успешных проверок повторяй их только при новой правке, ошибке или незакрытом риске. Runtime-прогон сохраняй в `docs/SAMPLE_RUN.md` и `output/`: команда, условия, реальный результат, ограничения и выполненный review; не выдавай старые метрики за свежие. Перед окончанием проверь совместимость контрактов, итоговый diff и чужие изменения.

## Уточнения документации при аудите 2026-09-05

- Старое AGENTS содержало первоначальные «сделай модель/каталог» и списки уже реализованных полей. Фактическая схема — `lumimatch/models.py`; её не дублируем как вторую спецификацию.
- Supplier capability допускает отдельное внутреннее поведение, но `sample-run` явно передаёт `availability_policy="sellable"` в pool/live recheck. Customer-facing правило остаётся строгим. `write_reports` сериализует переданный результат и сам не является availability gate; callers обязаны передавать проверенные кандидаты.
- Sample и production-build — разные пути; исторический SAMPLE_RUN и production golden benchmark сохранены раздельно.
- Старое безусловное требование полного sample после любой правки заменено проверками по риску. Исторические отчёты и evidence не удалялись.
- Controlled benchmark уточняет ранний visual spike: есть полезные результаты на отдельных референсах, но автоматическая замена Codex review не доказана.

Политика моделей находится только в AGENTS. Возможности делегирования сверены с [официальной документацией Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents); конкретные модели/лимиты — выбор пользователя, не обещание цены или автоматическая настройка runtime.
