## Протокол и границы вывода

Этот benchmark изолирован от `lumimatch/*`, crawler, hydration, availability и клиентских отчётов. Все расчёты локальные, CPU-only, в `.venv-visual`, без платных/OpenAI API. Результат проверяет технологическую возможность при наличии товара, а не production coverage.

- PRIMARY: F-01 / 50248, F-03 / FR2066WL-L40B, F-04 / LSP-7187; по 300 товаров. F-06 / 85078/01 протестирован отдельно на 19 товарах. Его КП-фото — широкий диск, в render — узкий цилиндр. Низкий rank F-06 не является успехом визуального подбора; R@20 для 19 кандидатов тривиален.
- Пулы собраны только из существующих изображений двух локальных каталогов. Историческим taxonomy-меткам не доверяем без проверки названия/URL. До раскрытия рангов из пулов удалены явно посторонние семьи и компоненты. В F-01 семейство понимается как подвесные светильники, включая многоподвесные композиции, а не только одно-плафонные изделия. Это более широкий и трудный пул.
- Детеминированное заполнение по хешу URL; golden используется для включения positive и измерения. SKU/название товара не подаются в encoder или score. Матрицы моделей используют одинаковый фиксированный пул; его SHA-256 хранится в каждом результате.
- F-01/F-03/F-04 используют реальные supplier photos из кэша. Для F-06 bounded target-aware discovery (`data/visual_spike/oracle_eval/manifest.json`) не нашёл карточку, локального supplier photo нет, дополнительный поиск по официальному домену результата не дал. Использован документированный fallback: картинка строки 16 из `expected_kp.docx`. Это не доказательство отсутствия карточки вообще.
- Все 12 query получены только из `Dan_vis.pdf`, страницы 2, 11, 18, 29, 30. Каждый окончательный crop открыт глазами. Tight содержит один полный объект с минимальными полями; medium — тот же объект с умеренным контекстом. F-01 tight: 89×227 px; увеличение не создаёт новых деталей. F-03/F-04 alternate — второй экземпляр на той же визуализации, не полностью независимый ракурс. F-06 верх корпуса частично уходит за кадр.
- `object_area_ratio` — приблизительная ручная оценка площади bounding box объекта относительно crop, не маска непрозрачных пикселей. Прежние оценки площади исправлены до раскрытия rank, все модели пересчитаны на финальных crops. На трёх PRIMARY нельзя делать статистический вывод о корреляции площади и качества; сравниваем варианты внутри каждого target.
- Основной score: cosine similarity нормированных image embeddings. MAX и MEAN считаются отдельно. Используется штатный preprocessing каждого checkpoint; разные resize/crop стратегии являются частью сравниваемых pipelines, поэтому различия нельзя приписать только backbone.
- OpenCLIP OpenAI checkpoint запускается с QuickGELU; старые несовместимые GELU-векторы исключены отдельной версией кэша. SigLIP2 adapter поддерживает `pooler_output` текущего Transformers. Исправления не изменяют и не используют golden ranking.
- Catalog-self и слегка cropped/resized catalog-photo — отдельные sanity-тесты, не production metric. Rank 1 в self-match тривиален; perturbed test несколько содержательнее, но не заменяет render query.
- Для каждого доступного encoder открыт анонимный Top-20 MAX, записаны позиции strong/plausible до reveal. SKU/названия не показаны. Это процедурное маскирование, не независимое слепое исследование: автор видел названия целей в задании. `useful_top20` включает strong+plausible, цветовые альтернативы допустимы; это не техническое одобрение и не проверка наличия. Для других crop-режимов manual usefulness не измерена и не переносится с MAX.
- DreamSim: rerank Top-50 отдельно от каждого доступного DINO/multimodal baseline, без golden identity. Проверяем оба multimodal источника, чтобы не выбирать по известному rank. Кандидат вне исходного Top-50 не может быть восстановлен reranker; такой результат обозначается отсутствующим, а не rank 51.
- Gallery — отдельная label-assisted coverage диагностика окончательного Top-20 SigLIP2 плюс positive: 137 фото из уже известных URL, до 3 на товар, без новых карточек. Один и тот же расширенный набор изображений проверяется всеми тремя baseline. Это не честная оценка равномерно покрытой gallery всей базы. Визуально проверены gallery positive и лидеров SigLIP2: соответствуют товару; часть фото дублирует primary, часть показывает детали/интерьер. У LSP-7187 есть лишь дубликат primary, у F-06 дополнительных фото нет; их gallery-test не проверяет эффект нового ракурса. Ранее скачанные дополнительные фото остаются в кэше, но не включены в финальный manifest.
- Background test: грубые прямоугольные маски сохранённого объекта на нейтральном фоне, без ML segmentation. Все четыре результата открыты; геометрия корпуса сохранена. Это вторичная ablation, не скрытая оптимизация baseline.
- Текстовые mixtures и fine-tuning не проводились. MobileCLIP2 повторно не запускался: по заданию он необязателен и не блокирует сравнение.
- N=3 PRIMARY, один проект, без holdout: любые успехи — демонстрация возможности, не оценка качества на новых дизайн-проектах. Исходный критерий 3/4 нельзя механически применять после исключения ошибочной разметки; приводим реальные знаменатели.

## Модели и ограничения доступа

- DINOv2 ViT-S/14: официальный Torch Hub checkpoint.
- OpenCLIP ViT-B/32: OpenAI pretrained weights через open_clip; `force_quick_gelu=True`.
- [DINOv3 Small](https://huggingface.co/facebook/dinov3-vits16-pretrain-lvd1689m): официальный endpoint вернул 401 gated repository. Нужен одобренный доступ; зеркала и обход не использовались.
- [SigLIP2 Base patch16/224](https://huggingface.co/google/siglip2-base-patch16-224): публичный официальный Google checkpoint.
- [DreamSim ensemble](https://github.com/ssundaram21/dreamsim): официальный пакет 0.2.1, perceptual embedding и cosine similarity. Загрузка включает ensemble archive и дополнительные DINO backbone weights.

## Воспроизведение и кэш

Пулы, manifest, masked review, sealed rankings, secondary, performance и positive provenance сохранены отдельно. NumPy-кэш зависит от модели/версии и SHA-256 изображения; результаты пишутся атомарно. Повторный запуск пересчитывает только отсутствующие/повреждённые векторы. Основные результаты привязаны SHA-256 к пулам, manifest и фактическим байтам всех query/product images; DreamSim дополнительно привязан к исходному ranking. Reveal отказывается принимать устаревшие входы или несовпадающие SHA-256 просмотренных sheets. После добавления этой проверки расчёты повторены из кэша, sheets и результаты не изменились. Не запускайте два writer-процесса одной модели одновременно.

Команды выполняются из корня проекта:

```powershell
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled prepare --limit 300
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled run --model dinov2_vits14
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled run --model openclip_vit_b32
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled run --model siglip2_base_patch16_224 --batch-size 4
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled_extensions dreamsim --sources dinov2_vits14 openclip_vit_b32 siglip2_base_patch16_224
# После визуального review и записи manual_review.json:
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled seal-review
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled reveal
# Secondary: те же crops и зафиксированный gallery manifest.
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled_diagnostics backgrounds
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled_diagnostics galleries --sources siglip2_base_patch16_224
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled_diagnostics score --model siglip2_base_patch16_224
# Повторить score для dinov2_vits14 и openclip_vit_b32.
.\.venv-visual\Scripts\python.exe -m experiments.visual_retrieval.controlled_extensions performance --model dreamsim_ensemble
# Повторить performance для baseline-моделей; reveal пересобирает итоговые отчёты.
```

Основные версии текущего запуска: Python 3.14.2, torch 2.13.0 CPU, torchvision 0.28.0, open_clip_torch 3.3.0, transformers 5.16.1, DreamSim 0.2.1. Новые зависимости только в `requirements-visual.txt` / `.venv-visual`; production `.venv` не изменена.

Время `runtime.total_seconds` может включать cache hits и загрузку модели; это не cold-indexing throughput. Для сравнения скорости есть отдельные warmed `performance` измерения без embedding-cache. `runtime.checkpoint_size_mb` — снимок общего model cache, не размер отдельной модели. Проверенные размеры файлов checkpoint: DINOv2 84.19 MiB, OpenCLIP 577.11 MiB, SigLIP2 1431.28 MiB. RSS — рабочий набор на момент замера, не гарантированный peak RAM.

## Итоговая проверка артефактов

- `.venv-visual`: 71 тест прошёл; `.venv`: 61 прошёл, 3 пропущены (экспериментальные зависимости не устанавливались в основное окружение).
- Проверены 752 уникальных исходных product/query изображения, 12 query crops, 108 списков ранжирования: изображения открываются, rank последовательны, IDs уникальны, scores конечны и отсортированы.
- Каждый positive присутствует в своём пуле ровно один раз. Все шесть результатов используют одни и те же контрольные суммы входов; 24 manual review соответствуют текущим sheets.
- Повторный запуск из кэша не изменил ранги и SHA-256 sheets. Два Markdown-отчёта совпадают побайтно.
- `git diff --check` проходит. Изменений в `lumimatch/*`, `data/supplier_availability.json`, `data/visual_review.json`, `ARCHITECTURE.md`, `README.md` и клиентских отчётах нет. Коммиты и push не выполнялись.
