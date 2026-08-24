# SAMPLE_RUN

Запущен `python -m lumimatch sample-run` на `samples/Dan_dia-2.pdf` и `samples/Dan_vis.pdf`.

- FixtureRequirement: `6`
- карточек в локальном SQLite после запуска: `171`
- PDF metadata/text cache: `data/pdf_extraction.json`
- reference renders: `output/sample_references/`
- machine source: `output/lumimatch_sample.json`
- reports: `output/lumimatch_sample.md` и `output/lumimatch_sample.html`
- Codex visual review input: `data/visual_review.json`

## Коллекторы

- `artelamp.ru`: pages=12, products=0, images=0, errors=0
- `citilux.ru`: pages=12, products=11, images=11, errors=0
- `divinare.ru`: pages=12, products=0, images=0, errors=0
- `lightstar.ru`: pages=12, products=12, images=12, errors=0
- `shop.lussole.ru`: pages=12, products=1, images=1, errors=0
- `maytoni.ru`: pages=12, products=0, images=0, errors=0

## Ограничения

Итоговый визуальный класс является предварительным: фотографии кандидатов нужно просмотреть в HTML и подтвердить вручную в Codex. Поля, которых нет на публичной карточке, помечены как неизвестные.
