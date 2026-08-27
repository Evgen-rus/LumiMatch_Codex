# ARCHITECTURE.md — текущая архитектура LumiMatch

## 1. Назначение

LumiMatch — локальный Codex-workflow для продавца светотехники. Он помогает разобрать дизайн-проект, выделить требуемые светильники и подобрать у разрешённых поставщиков конкретную модель либо максимально близкий аналог.

Основной вход:

- технические PDF-планы;
- интерьерные визуализации;
- подписи, размеры и спецификации, если они присутствуют;
- список разрешённых поставщиков из `suppliers.txt`.

Основной результат — короткая, проверяемая подборка с референсом из проекта, настоящими фотографиями товаров, SKU, прямыми ссылками, публичными характеристиками, статусом доступности и объяснением сходств и различий. Если достойного кандидата нет, система возвращает честный пустой результат.

## 2. Архитектурная граница

Codex является AI-оператором системы. Он читает PDF и изображения, связывает планы с визуализациями, проверяет contact sheets и принимает финальное визуальное решение.

Локальный Python-код автоматизирует воспроизводимую часть:

- discovery публичных карточек;
- построение локального URL inventory;
- ограниченный выбор страниц для извлечения;
- получение и нормализацию товарных данных;
- SQLite-каталог, кэш и дедупликацию;
- taxonomy, availability и технические фильтры;
- подготовку reference crops и contact sheets;
- применение сохранённых решений визуального review;
- live recheck и формирование отчётов;
- golden benchmark и диагностические эксперименты.

В проекте нет внешнего LLM/vision runtime, OpenAI SDK и требования `OPENAI_API_KEY`. LumiMatch не является SaaS, многопользовательской системой или полностью автономным сервисом без Codex.

## 3. Контуры системы

### 3.1. Основной production-контур

Канонический поток:

`design project -> FixtureRequirement -> supplier URL inventory -> requirement-driven hydration -> CatalogProduct -> hard gates -> wide candidate pool -> contact sheets -> Codex visual review -> live recheck -> customer report`

Сбор каталога отделён от обработки конкретного проекта. Сайты не нужно полностью обходить заново для каждой позиции: URL inventory, извлечённые карточки, изображения и промежуточные результаты кэшируются локально.

### 3.2. Golden benchmark

Golden-контур измеряет потери по стадиям, не влияя на production-отбор:

`expected selection -> target normalization -> inventory recall -> hydrated catalog recall -> hard-gated retrieval -> completed visual review -> metrics`

Golden SKU нельзя использовать для выбора URL при production build. Эталон открывается только после построения production-результата и служит для диагностики.

### 3.3. Экспериментальный visual retrieval

`experiments/visual_retrieval/` — изолированный CPU-контур для проверки image embeddings и retrieval-гипотез. Его зависимости находятся в `requirements-visual.txt`, а кэш и результаты — в отдельных `data/visual_spike/` и `output/visual_spike/`.

Эксперимент не меняет production scoring, availability policy, финальные отчёты или обязательность ручной визуальной проверки Codex. Перенос результата эксперимента в основной pipeline требует отдельного подтверждённого решения.

## 4. Production pipeline

### 4.1. Разбор дизайн-проекта

Codex и локальные PDF-инструменты:

1. читают все технические и визуальные материалы проекта;
2. связывают технические обозначения с интерьерными референсами;
3. сохраняют известные значения и оставляют неизвестное неизвестным;
4. создают `FixtureRequirement` с источниками и уверенностью;
5. готовят страницы и crops для последующего visual review.

Sample-проект хранится в `samples/` и остаётся основным регрессионным примером. Текущий набор содержит восемь требований, включая подвесы, линейный свет, бра, зеркало, spot/track, шинопровод и LED/profile позиции.

### 4.2. Supplier discovery и URL inventory

Источником разрешённых доменов является только `suppliers.txt`.

Порядок получения публичного контента:

1. sitemap или sitemap index;
2. обычный HTTP;
3. JSON-LD и другие структурированные данные;
4. спецификационные таблицы и устойчивые HTML-селекторы;
5. лёгкий site-specific adapter;
6. Playwright только для публично отрисованного контента, который нельзя получить проще.

Discovery классифицирует URL и сохраняет product URL inventory отдельно от извлечённого каталога. Обход ограничен лимитами, retry и rate control. Ошибка одного домена не останавливает остальные. CAPTCHA, авторизация и технические защиты не обходятся.

### 4.3. Requirement-driven hydration

Полный URL inventory может быть существенно больше допустимого бюджета загрузки. `select_hydration_urls` формирует широкий, но ограниченный набор URL для каждого требования с квотами по поставщикам.

Hydration получает карточки только из production inventory и не читает golden set. Эта стадия сейчас является отдельной измеряемой границей: товар может присутствовать в inventory, но не попасть в hydrated catalog из-за отбора или квоты.

### 4.4. Product extraction и хранение

`CatalogProduct` хранит идентичность карточки, поставщика, URL, SKU, название, категорию, коллекцию, цену, доступность, размеры, цвет, материал, монтаж, источник света, мощность, цветовую температуру, IP, атрибуты и изображения.

Правила доказательности:

- характеристики извлекаются из JSON-LD, specification table или site-specific selectors;
- полный body text не является надёжным источником отдельных характеристик;
- размеры светильника нормализуются в `width_mm`, `height_mm`, `length_mm`, `diameter_mm`, `depth_mm`;
- размеры упаковки не считаются размерами изделия;
- изображения должны относиться к текущему SKU, а не к рекомендациям, сертификатам, счётчикам или просмотренным товарам;
- несуществующие значения не угадываются.

Основные хранилища — SQLite и JSON. SQLite используется для каталога, URL inventory и текстового поиска; JSON — для требований, review, отчётов и диагностических контрактов.

### 4.5. Hard gates и широкий candidate pool

Lexical/FTS scoring является coarse retrieval, а не финальным решением. До visual review строится широкий пул, обычно 30–100 карточек.

До попадания в визуальный пул применяются:

- совместимость `FixtureRequirement.taxonomy_family` и `CatalogProduct.product_family`;
- монтажные и доказанные технические ограничения;
- критические размерные ограничения;
- supplier-level availability policy;
- базовая структурная и текстовая релевантность.

Несовместимые family не передаются на визуальную проверку. Другой цвет допускается только отдельным режимом `color_alternative`, если хороший кандидат нужного цвета не найден.

### 4.6. Availability policy

Capability каждого поставщика хранится в `data/supplier_availability.json`.

Для `stock_tracked` основной customer-facing pool принимает только `availability_status=in_stock`. `unknown`, `out_of_stock`, `preorder`, `expected`, `check_availability`, discontinued и архивные карточки исключаются.

Для вручную подтверждённого `stock_not_published` отсутствие опубликованного статуса может обрабатываться только его отдельной capability-политикой. Это не означает подтверждённое наличие и не разрешает глобально принимать `unknown`.

Диагностический unavailable pool независим от основного и может содержать только временные статусы:

- `out_of_stock`;
- `preorder`;
- `expected`;
- `check_availability`.

`unknown`, discontinued и архивные позиции не допускаются и в диагностический результат. Один товар не должен одновременно появляться в основном и unavailable-отчёте.

### 4.7. Codex visual review

Для каждого требования создаются reference crops, manifest и contact sheets в `output/review/<requirement>/`. Codex сравнивает геометрию, конструкцию, пропорции, способ монтажа, материал, цвет и контекст применения.

Решения сохраняются как явные `accept` или `reject`. `reject` является обязательным gate: отклонённый товар исчезает из финала и сохраняется в диагностике `output/debug/rejected_candidates.json`.

Оценки разделены на:

- `visual_similarity`;
- `type_match`;
- `dimension_match`;
- `technical_match`;
- `overall_score`.

Hard constraints важнее визуального сходства. Числовой score сам по себе не доказывает совпадение, а отсутствие сильных кандидатов не компенсируется заполнением отчёта слабыми вариантами.

### 4.8. Live recheck

Перед финальной выдачей карточка каждого кандидата открывается повторно без кэша.

Для `stock_tracked` требуется актуальный `in_stock`. Для допустимого `stock_not_published` нужны живая карточка, совпадающий SKU и отсутствие явных негативных маркеров. Такой товар нельзя описывать как товар с подтверждённым наличием.

Live recheck защищает отчёт от устаревшего URL, изменившегося SKU, снятия с продажи и изменения наличия между сбором каталога и выдачей.

### 4.9. Reports

Основной отчёт формируется в HTML, Markdown и JSON. Для каждого требования он показывает:

- референс и контекст из проекта;
- распознанное требование и источники;
- до пяти визуально подтверждённых кандидатов;
- фото, поставщика, название, SKU и прямую ссылку;
- публичные цену, наличие, размеры и характеристики;
- класс совпадения и объяснение различий.

Основной отчёт содержит только допустимые customer-facing позиции. Независимый `*_unavailable` отчёт предназначен для диагностики visual matching и не является предложением клиенту.

## 5. Основные компоненты

| Компонент | Ответственность |
|---|---|
| `lumimatch/models.py` | Pydantic-контракты требований, товаров и кандидатов |
| `lumimatch/pdf_project.py` | инспекция PDF, рендер страниц и reference crops |
| `lumimatch/audit.py` | ограниченный аудит возможностей сайтов поставщиков |
| `lumimatch/discovery.py` | sitemap/HTTP discovery и классификация product URL |
| `lumimatch/inventory.py` | URL inventory и requirement-driven hydration plan |
| `lumimatch/fetch.py` | публичные HTTP-запросы, кэш и retry |
| `lumimatch/collector.py` | координация discovery, hydration и извлечения карточек |
| `lumimatch/extract.py` | доказательное извлечение данных текущего SKU |
| `lumimatch/availability.py` | нормализация статусов и supplier capability policy |
| `lumimatch/taxonomy.py` | практическая taxonomy светотехники |
| `lumimatch/storage.py` | SQLite-каталог и FTS |
| `lumimatch/scoring.py` | hard gates, coarse retrieval и финализация кандидатов |
| `lumimatch/visual_review.py` | contact sheets и manifest для Codex review |
| `lumimatch/report.py` | основной и unavailable отчёты |
| `lumimatch/golden.py`, `benchmark.py` | golden dataset и stage-by-stage диагностика |
| `lumimatch/cli.py` | локальные команды и композиция стадий |
| `experiments/visual_retrieval/` | изолированные image-retrieval эксперименты |

## 6. Данные и артефакты

Основные устойчивые контракты:

- `data/fixture_requirements.json` — требования текущего проекта;
- `data/supplier_availability.json` — capability наличия по поставщикам;
- `data/visual_review.json` — явные решения Codex;
- `data/catalog/*.sqlite3` — URL inventory, каталог и индексы;
- `output/production_inventory.*` — состояние discovery/inventory;
- `output/production_hydration.*` — выбранные URL и результат hydration;
- `output/review/` — reference crops, manifests и contact sheets;
- `output/debug/` — причины исключений и rejected candidates;
- `output/golden/` — benchmark и visual-review evidence;
- `output/visual_spike/` — только экспериментальные результаты.

Runtime-кэши и generated artifacts не являются архитектурными источниками истины. Источниками правил служат этот документ, `AGENTS.md`, кодовые контракты и проверяемые данные.

## 7. Текущие ограничения

Подтверждённые ограничения текущего решения:

- supplier discovery и parsing имеют разное качество на разных доменах;
- наличие нужного SKU в URL inventory не гарантирует его выбор для hydration;
- visual retrieval по общему корпусу без family/mounting context даёт слабые результаты;
- exact match нельзя объявлять без подтверждения SKU и карточки;
- некоторые системные позиции требуют инженерной спецификации, а не подбора только по внешнему виду;
- обработка нового проекта остаётся human-in-the-loop Codex workflow, а не одной полностью автономной командой.

По последнему сохранённому golden benchmark основная измеренная потеря находится между URL inventory и hydrated catalog. Изолированный CPU visual spike также не подтвердил, что простое embedding-ранжирование способно заменить family-aware retrieval и Codex review.

## 8. Правила развития

1. Сначала локализовать, на какой стадии теряется нужный товар: discovery, inventory, hydration, extraction, hard gate, retrieval, visual review или live recheck.
2. Не ослаблять availability и технические gates для маскировки проблем предыдущих стадий.
3. Любой новый retrieval-подход сначала проверять в изолированном эксперименте и на golden benchmark.
4. Не смешивать golden targets с production selection.
5. Сохранять raw evidence, причины reject и воспроизводимые метрики.
6. Не добавлять тяжёлую инфраструктуру, если проблему можно решить локальным индексом, адаптером или более точным отбором.
7. При изменении pipeline одновременно обновлять `ARCHITECTURE.md`, тесты и соответствующие пользовательские инструкции.

Исторические метки V2/V4 могут оставаться в старых отчётах и именах команд. В актуальной документации они не обозначают отдельные работающие системы: канонической считается архитектура, описанная здесь.
