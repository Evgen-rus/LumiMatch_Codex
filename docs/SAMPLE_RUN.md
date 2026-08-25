# SAMPLE_RUN V2

Повторный availability-gated, visual-first прогон на `samples/Dan_dia-2.pdf` и `samples/Dan_vis.pdf`.

- FixtureRequirement после coverage pass: `8`
- карточек в локальном SQLite: `206`
- удалено карточек, переставших быть product pages при refresh: `0`
- reference crops и contact sheets: `output/review/`
- machine source: `output/lumimatch_sample.json`
- reports: `output/lumimatch_sample.md` и `output/lumimatch_sample.html`
- unavailable visual diagnostics: `output/lumimatch_sample_unavailable.md`, `output/lumimatch_sample_unavailable.html` и `output/lumimatch_sample_unavailable.json`
- rejected diagnostics: `output/debug/rejected_candidates.json`

## Supplier coverage

| supplier | mode | discovered | parsed | in_stock | unknown | out_of_stock | discontinued | failed | status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| ambrella.biz | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | partial |
| artelamp.ru | stock_tracked | 3 | 3 | 3 | 0 | 0 | 0 | 0 | complete |
| citilux.ru | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | partial |
| crystallux.ru | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | partial |
| divinare.ru | stock_tracked | 21 | 0 | 0 | 0 | 0 | 0 | 8 | complete |
| eurosvet.ru | stock_tracked | 60 | 4 | 4 | 0 | 0 | 0 | 4 | complete |
| favourite-light.com | stock_tracked | 1 | 0 | 0 | 0 | 0 | 0 | 1 | complete |
| kinklight.ru | stock_tracked | 60 | 0 | 0 | 0 | 0 | 0 | 9 | complete |
| lightstar.ru | stock_tracked | 60 | 8 | 7 | 0 | 1 | 0 | 0 | complete |
| shop.lussole.ru | stock_tracked | 1 | 0 | 0 | 0 | 0 | 0 | 1 | complete |
| maytoni.ru | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | partial |
| mw-light.ru | stock_tracked | 1 | 0 | 0 | 0 | 0 | 0 | 1 | complete |
| odeon-light.com | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | partial |
| freya-light.com | stock_tracked | 1 | 0 | 0 | 0 | 0 | 0 | 1 | complete |
| stluce.ru | stock_tracked | 0 | 0 | 0 | 0 | 0 | 0 | 0 | partial |

## FixtureRequirement coverage and final results

| id | wide pool | availability excluded | visual rejected | in_stock final | unavailable visual final | color fallback |
|---|---:|---:|---:|---:|---:|---|
| F-01 | 22 | 85 | 0 | 1 | 0 | нет |
| F-02 | 19 | 85 | 0 | 0 | 0 | нет |
| F-03 | 19 | 85 | 0 | 0 | 0 | нет |
| F-04 | 19 | 85 | 0 | 0 | 0 | нет |
| F-05 | 0 | 85 | 0 | 0 | 0 | нет |
| F-06 | 21 | 85 | 1 | 0 | 0 | нет |
| F-07 | 80 | 85 | 0 | 0 | 0 | нет |
| F-08 | 19 | 85 | 0 | 0 | 0 | нет |

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

- Каталог: `206 -> 206`; FixtureRequirement: `8 -> 8`; основные финальные кандидаты: `1 -> 1`; недоступные визуальные финалисты: `0`.
- Проверенные supplier modes в текущем списке: `stock_tracked`.
- Новые пулы по `stock_not_published`: `0` supplier(s) (нет).
- Новых визуально сильных аналогов в sample не появилось; недоступные/архивные товары в финал не вернулись.

## Product decision

Для stock_tracked в подбор попадает только `in_stock`. Для stock_not_published отсутствие статуса допускается, но явные отрицательные маркеры (нет в наличии, архив, под заказ, ожидается, уточнение наличия и аналоги) по-прежнему исключаются. Оба режима проходят live recheck.

Если по позиции нет достойного кандидата, отчёт показывает: `Ничего не найдено. Попробуйте подобрать вручную.`
