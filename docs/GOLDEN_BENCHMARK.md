# Golden benchmark — V4 production stages

Дата прогона: `2026-08-25`.

Production pipeline разделён на независимые стадии: URL inventory → requirement-driven hydration → hard gates/retrieval → Codex visual review. Golden set использовался только после production build для оценки и не выбирал production URL.

## Stage recall и retrieval

| metric | result |
|---|---:|
| product URL inventory | `10,291` |
| hydrated unique URLs | `563` |
| hydrated catalog cards | `518` |
| inventory recall, SKU-matchable visual targets | `5/10` |
| hydrated catalog recall, SKU-matchable visual targets | `0/10` |
| sellable hydrated recall, SKU-matchable visual targets | `0/10` |
| target-aware golden discovery, all golden items | `6/22` |
| retrieval@20 / @50 / @100 | `0 / 0 / 0` |
| actual visual@1 / @3 / @5 / @10 | `0 / 0 / 0 / 0` |

`visual@K` считается только после полного review всех текущих candidate pools. В этом run review complete для всех 8 требований; нулевые visual@K означают, что golden SKU не попал в hydrated production pool, а не что review был неполным.

## Current visual-review pools

Все текущие кандидаты были просмотрены по свежим contact sheets из `output/golden/dan/review/`. Для каждого кандидата записано явное `accept` или `reject` в `actual_visual_review_completed.json`.

| F | current pool | accepted visual candidates |
|---|---:|---:|
| F-01 | 90 | 0 |
| F-02 | 100 | 0 |
| F-03 | 99 | 2 |
| F-04 | 96 | 2 |
| F-05 | 98 | 0 |
| F-06 | 100 | 3 |
| F-07 | 100 | 2 |
| F-08 | 88 | 0 |

Принятые visual analogs:

- `F-03`: Freya `FR1007WL-01BS`, `FR1007WL-01N` — компактный настенный светильник с абажуром; цвет и арматура отличаются от чёрной референсной модели.
- `F-04`: Freya `FR1011WL-01B`, `FR1011WL-02B` — близкий вертикальный овальный контур; стекло темнее, у второй модели два корпуса.
- `F-06`: Ambrella `XP8111050`, Lussole `LSP-9509`, `LSP-9821` — чёрные цилиндрические/трековые spot-светильники; отличаются способом крепления, поэтому требуют проверки монтажа.
- `F-07`: Lightstar `506217`, `506227` — чёрный линейный шинопровод соответствующей системной семьи; длина и конфигурация проекта не доказаны.

Аксессуары DIY (крепёж, заглушки, основания, соединители) не считались светильниками. Для F-01, F-02, F-05 и F-08 в текущем hydrated pool действительно хороших аналогов не подтверждено; F-08 дополнительно требует не смешивать голую LED-ленту с готовым профилем.

## Stage diagnoses

Из 10 SKU-matchable visual targets:

- `5` найдены в URL inventory;
- `5` отсутствуют уже на inventory stage;
- из найденных `5` ни один не был выбран текущим hydration budget;
- `0` достигли hard-gated hydrated catalog, поэтому retrieval и availability нельзя оценивать как главную причину потери этих SKU.

Наиболее заметная следующая точка улучшения — requirement-driven quota/selection: inventory уже содержит `50248`, `lsp-4001`, `lsp-7187` и `LSP-4016`, но текущий bounded hydration отбирает другие URL. Это диагностическая проблема coverage/hydration, а не доказательство плохого visual matching и не availability-only loss.

## Supplier diagnostics

| supplier | inventory URLs | relevant selected | hydrated cards | parse success |
|---|---:|---:|---:|---:|
| freya-light.com | 1623 | 80 | 40 | 1.000 |
| shop.lussole.ru | 1634 | 61 | 51 | 1.000 |
| kinklight.ru | 1347 | 142 | 40 | 0.482 |
| eurosvet.ru | 1843 | 138 | 69 | 1.000 |
| odeon-light.com | 62 | 40 | 24 | 1.000 |
| ambrella.biz | 208 | 134 | 82 | 1.000 |
| artelamp.ru | 489 | 90 | 53 | 1.000 |
| divinare.ru | 348 | 128 | 69 | 0.972 |
| lightstar.ru | 2731 | 147 | 90 | 1.000 |

Для cached inventory в этом отчёте не проставляется процент покрытия относительно sitemap approximation, если такой denominator не был сохранён в inventory payload. Это предотвращает ложные значения coverage >100%.

## Вывод

В текущем clean V4 run главная проблема — hydration/coverage до retrieval, а не availability и не финальный visual threshold. При этом Codex visual review независимо подтвердил хорошие аналоги для F-03, F-04, F-06 и F-07 и оставил F-01, F-02, F-05, F-08 пустыми без искусственного заполнения.
