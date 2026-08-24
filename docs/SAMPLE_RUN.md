# SAMPLE_RUN V2

Повторный availability-gated, visual-first прогон на `samples/Dan_dia-2.pdf` и `samples/Dan_vis.pdf`.

- FixtureRequirement после coverage pass: `8`
- карточек в локальном SQLite: `206`
- удалено карточек, переставших быть product pages при refresh: `0`
- reference crops и contact sheets: `output/review/`
- machine source: `output/lumimatch_sample.json`
- reports: `output/lumimatch_sample.md` и `output/lumimatch_sample.html`
- rejected diagnostics: `output/debug/rejected_candidates.json`

## Supplier coverage

| supplier | discovered | parsed | in_stock | out_of_stock | discontinued | failed | status |
|---|---:|---:|---:|---:|---:|---:|---|
| ambrella.biz | 0 | 0 | 0 | 0 | 0 | 0 | partial |
| artelamp.ru | 3 | 3 | 3 | 0 | 0 | 0 | complete |
| citilux.ru | 0 | 0 | 0 | 0 | 0 | 0 | partial |
| crystallux.ru | 0 | 0 | 0 | 0 | 0 | 0 | partial |
| divinare.ru | 21 | 0 | 0 | 0 | 0 | 8 | complete |
| eurosvet.ru | 60 | 4 | 4 | 0 | 0 | 4 | complete |
| favourite-light.com | 1 | 0 | 0 | 0 | 0 | 1 | complete |
| kinklight.ru | 60 | 0 | 0 | 0 | 0 | 9 | complete |
| lightstar.ru | 60 | 8 | 7 | 1 | 0 | 0 | complete |
| shop.lussole.ru | 1 | 0 | 0 | 0 | 0 | 1 | complete |
| maytoni.ru | 0 | 0 | 0 | 0 | 0 | 0 | partial |
| mw-light.ru | 1 | 0 | 0 | 0 | 0 | 1 | complete |
| odeon-light.com | 0 | 0 | 0 | 0 | 0 | 0 | partial |
| freya-light.com | 1 | 0 | 0 | 0 | 0 | 1 | complete |
| stluce.ru | 0 | 0 | 0 | 0 | 0 | 0 | partial |

## FixtureRequirement coverage and final results

| id | wide pool | availability excluded | visual rejected | final | color fallback |
|---|---:|---:|---:|---:|---|
| F-01 | 22 | 85 | 0 | 1 | нет |
| F-02 | 19 | 85 | 0 | 0 | нет |
| F-03 | 19 | 85 | 0 | 0 | нет |
| F-04 | 19 | 85 | 0 | 0 | нет |
| F-05 | 0 | 85 | 0 | 0 | нет |
| F-06 | 21 | 85 | 1 | 0 | нет |
| F-07 | 80 | 85 | 0 | 0 | нет |
| F-08 | 19 | 85 | 0 | 0 | нет |

## Product decision

Товары без подтверждённого `in_stock`, снятые с производства, под заказ, ожидаемые, с неизвестным наличием, без совместимой family или без положительного визуального review не попадают в итог.

Если по позиции нет достойного кандидата, отчёт показывает: `Ничего не найдено. Попробуйте подобрать вручную.`
