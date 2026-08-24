# LumiMatch V2 root-cause analysis

Проверка первой версии выполнена по исходному коду, SQLite-каталогу, сохранённым shortlist/visual review и sample PDF.

## Подтверждённые причины плохой выдачи

1. Availability не была hard gate: `Нет в наличии`, `OutOfStock` и отсутствие статуса могли попасть в top-5. Schema.org marker сохранялся как URL и не имел конечного нормализованного статуса.
2. `sample-run` фактически индексировал только шесть доменов из `suppliers.txt`, а discovery расходовал лимит страниц на главную, категории и статьи. В сохранённом прогоне были карточки только от `citilux.ru`, `eurosvet.ru`, `lightstar.ru` и `shop.lussole.ru`.
3. Lexical scoring выдавал top-5 до visual review. Поэтому Codex не видел визуально подходящую карточку, если название не совпало с текстом требования.
4. Taxonomy отсутствовала: `люстра`, одиночный цилиндрический подвес и трековый spot могли считаться одним текстовым типом через слишком широкие synonym rules.
5. Visual review не имел reject-семантики: низкий visual score оставался кандидатом и попадал в отчёт.
6. Характеристики извлекались из flattened body text. `color`/`mounting_type`/`IP` содержали соседние характеристики и related-блоки.
7. Image extraction обходил все `img` на странице и добавлял related, recommendations, certificates, viewed и counters. Vision получал не только фото текущего SKU.
8. Размеры не имели нормализованного `*_mm` контракта; упаковочные размеры могли конкурировать с размерами товара.
9. В отчёте отсутствовали reference crops, search stats, supplier coverage и честный нулевой результат.

## Архитектурное решение V2

`availability -> family/mounting/technical hard filters -> wide pool 30-100 -> contact sheets -> visual review Codex -> reject -> live availability recheck -> 0-5 finalists`.

Для цвета сначала используется пул нужного цвета. Другая окраска разрешается только как отдельный `color_alternative`, когда основной пул не дал финалистов.
