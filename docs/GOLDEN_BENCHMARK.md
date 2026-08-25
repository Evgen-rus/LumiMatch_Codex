# Golden benchmark — clean production discovery

Дата прогона: `2026-08-25`.

Production catalog был собран отдельно в `data/catalog/production_clean.sqlite3` командой `production-build`. Во время этой сборки golden set, ожидаемые SKU и target-aware URL discovery не читались. После сборки golden был загружен только для evaluation.

## Recall и retrieval

| metric | result |
|---|---:|
| production catalog recall, SKU-matchable visual targets | `0/10` |
| visual targets без SKU | `1` |
| target-aware golden discovery, SKU-matchable visual targets | `5/10` |
| target-aware discovery, all golden items | `6/22` |
| production retrieval@20 / @50 / @100 | `0 / 0 / 0` |
| actual visual@1 / @3 / @5 / @10 for golden targets | `0 / 0 / 0 / 0` |

Target-aware discovery и production catalog recall намеренно разделены. Golden discovery нашёл 5 из 10 SKU-matchable visual targets, но scratch store остался пустым и не изменил production catalog.

## Фактический visual review

Открыты reference crops и свежие contact sheets из `output/golden/dan/review/`. В отдельном файле `output/golden/dan/actual_visual_review_completed.json` сохранены только judgments текущего запуска; старые annotation scores не использовались.

По текущим production pools визуально приняты два декоративных аналога:

- `F-02`: Ambrella `GV1451` — линейный чёрный корпус, но монтаж не доказан как recessed;
- `F-03`: Eurosvet `00000055442` — близкая роль и светлый абажур, но классическая латунная арматура вместо чёрного основания.

Для `F-01`, `F-04`, `F-06` и `F-08` достойных аналогов в текущих sheets не подтверждено. `F-05` остался пустым из-за технического hard gate по влажной зоне. `F-07` имеет визуально похожий шинопровод `GV1076`, но это system/ambiguous requirement и не входит в decorative visual metrics.

## Supplier coverage

Полная детализация сохранена в `output/production_catalog_build.json`. В ней отдельно записаны sitemap URLs total, product URLs discovered, cards attempted, parsed cards, parse rate, approximate catalog coverage, discovery quality и parse quality. Поэтому supplier может быть parse-healthy, но discovery-partial/broken.

Чистая сборка содержит `281` карточку. При bounded лимите `35` карточек на supplier большинство адаптеров имеют healthy parse rate, но discovery coverage остаётся partial, потому что URL inventory больше обрабатываемого лимита. Generic suppliers с нулевым product URL inventory требуют отдельного adapter/fallback pass; это bottleneck discovery, а не доказательство отсутствия товаров.

## Вывод

На этом clean run главная проблема — discovery/coverage production catalog, а не availability: production recall ожидаемых SKU равен нулю ещё до sellable gate. При этом фактический visual review нашёл только два умеренно пригодных текущих аналога, поэтому после расширения catalog нужно повторно проверить и retrieval, и visual quality; нельзя считать все потери только availability.
