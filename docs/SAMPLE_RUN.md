# SAMPLE_RUN V2

## V4 production-stage validation

The clean production-stage run is documented separately in [`docs/GOLDEN_BENCHMARK.md`](GOLDEN_BENCHMARK.md). It uses URL inventory `10,291`, requirement-driven hydration `563` unique URLs / `518` cards, and a complete Codex review for all eight current FixtureRequirement pools. The historical V2 sample figures below are intentionally retained as the availability-gated sample report baseline.

Повторный availability-gated, visual-first прогон на `samples/Dan_dia-2.pdf` и `samples/Dan_vis.pdf`.

- FixtureRequirement после coverage pass: `8`
- карточек в локальном SQLite: `301`
- удалено карточек, переставших быть product pages при refresh: `0`
- reference crops и contact sheets: `output/review/`
- machine source: `output/lumimatch_sample.json`
- reports: `output/lumimatch_sample.md` и `output/lumimatch_sample.html`
- unavailable visual diagnostics: `output/lumimatch_sample_unavailable.md`, `output/lumimatch_sample_unavailable.html` и `output/lumimatch_sample_unavailable.json`
- golden benchmark: `output/golden/dan/benchmark.md`, `output/golden/dan/benchmark.json` и свежий review manifest `output/golden/dan/visual_review_manifest.json`
- golden discovery: `output/golden/dan/discovery_report.md` и `output/golden/dan/discovery_report.json`; исходный набор: `data/golden/dan/golden_set.json`
- rejected diagnostics: `output/debug/rejected_candidates.json`

## Supplier coverage

| supplier | mode | discovered | parsed | in_stock | unknown | out_of_stock | discontinued | failed | status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| ambrella.biz | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | broken |
| artelamp.ru | stock_tracked | 3 | 3 | 3 | 0 | 0 | 0 | 0 | healthy |
| citilux.ru | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | broken |
| crystallux.ru | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | broken |
| divinare.ru | stock_tracked | 112 | 28 | 19 | 0 | 9 | 0 | 2 | partial |
| eurosvet.ru | stock_tracked | 20 | 20 | 20 | 0 | 0 | 0 | 0 | healthy |
| favourite-light.com | stock_tracked | 1 | 0 | 0 | 0 | 0 | 0 | 1 | broken |
| kinklight.ru | stock_tracked | 112 | 28 | 0 | 28 | 0 | 0 | 3 | partial |
| lightstar.ru | stock_tracked | 112 | 28 | 23 | 0 | 5 | 0 | 0 | partial |
| shop.lussole.ru | stock_tracked | 1 | 0 | 0 | 0 | 0 | 0 | 1 | broken |
| maytoni.ru | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | broken |
| mw-light.ru | stock_tracked | 2 | 0 | 0 | 0 | 0 | 0 | 2 | broken |
| odeon-light.com | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | broken |
| freya-light.com | stock_tracked | 1 | 1 | 0 | 1 | 0 | 0 | 0 | healthy |
| stluce.ru | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | broken |

## FixtureRequirement coverage and final results

| id | wide pool | availability excluded | visual rejected | in_stock final | unavailable visual final | color fallback |
|---|---:|---:|---:|---:|---:|---|
| F-01 | 42 | 129 | 0 | 1 | 0 | нет |
| F-02 | 28 | 129 | 0 | 0 | 0 | нет |
| F-03 | 29 | 129 | 0 | 0 | 0 | нет |
| F-04 | 31 | 129 | 0 | 0 | 0 | нет |
| F-05 | 0 | 129 | 0 | 0 | 0 | нет |
| F-06 | 30 | 129 | 1 | 0 | 0 | нет |
| F-07 | 80 | 129 | 0 | 0 | 0 | нет |
| F-08 | 28 | 129 | 0 | 0 | 0 | нет |

### Availability diagnostic

| id | in_stock visual | out_of_stock visual | preorder visual | expected visual | check_availability visual | discontinued rejected | visual rejected |
|---|---:|---:|---:|---:|---:|---:|---:|
| F-01 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| F-02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F-04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F-05 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F-06 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| F-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F-08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Comparison with previous V2

- Каталог: `206 -> 301`; FixtureRequirement: `8 -> 8`; основные финальные кандидаты: `1 -> 1`; недоступные визуальные финалисты: `0`.
- Проверенные supplier modes в текущем списке: `stock_tracked`.
- Новые пулы по `stock_not_published`: `0` supplier(s) (нет).
- Новых визуально сильных аналогов в sample не появилось; недоступные/архивные товары в финал не вернулись.

## Golden benchmark

- Источник `expected_kp.docx`: `22` позиции — `11` `VISUAL_SELECTION` и `11` `SYSTEM_BOM`; системные позиции исключены из декоративных visual-метрик и считаются отдельно в `system_bom_coverage`.
- Discovery: найдено `6/22`, из них `5` с exact/page-label evidence, распарсено `8`, с фото `6`. Для visual selection fresh review дал `visual@1=1`, `visual@3=1`, `visual@5=2`, `visual@10=2`.
- Визуально подтверждённые targets: `FR2066WL-L40B` (Freya, F-03) и `LSP-7187` (Lussole, F-04). `2207B,19` был найден, но fresh visual review отклонил его как неподходящую ветвящуюся архитектурную форму; `LSP-4016` также отклонён, хрустальные и классические false positives не прошли review.
- `F-03` имеет сильный визуальный контроль, но `2207B,19` остаётся вне sellable pool из-за `unknown` на `stock_tracked`; `F-04` имеет найденный визуальный аналог `LSP-7187`. Для F-01, F-02, F-05 и F-06 остаются retrieval/discovery или hard-gate ограничения, а не скрытые unavailable finalists.
- Supplier coverage в benchmark использует состояния `healthy` / `partial` / `broken`; `discovered > 0` при `parsed = 0` не считается здоровым покрытием. `SYSTEM_BOM` покрыт отдельно: `11` позиций, `3` discovered, `0` parsed/found/photo.

## Product decision

Для stock_tracked в подбор попадает только `in_stock`. Для stock_not_published отсутствие статуса допускается, но явные отрицательные маркеры (нет в наличии, архив, под заказ, ожидается, уточнение наличия и аналоги) по-прежнему исключаются. Оба режима проходят live recheck.

Если по позиции нет достойного кандидата, отчёт показывает: `Ничего не найдено. Попробуйте подобрать вручную.`
