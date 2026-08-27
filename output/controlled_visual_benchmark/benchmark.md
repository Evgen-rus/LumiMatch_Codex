# Вывод: visual retrieval полезен, но не заменяет проверку конструкции

Контролируемый поиск **работает как способ получить кандидатов**: SigLIP2 поставил точные SKU F-01 и F-03 на первое место среди 300 товаров соответствующей семьи. Для F-04 он нашёл заданный в КП SKU на 33-м месте; DreamSim поднял его до 7-го, но визуально это не точное повторение конструкции на render. Поэтому вывод — подтверждённая возможность для двух примеров, частичный успех для третьего, не универсальное автоматическое распознавание светильника.

Лучший первый encoder в этом запуске — **SigLIP2 Base**. На трёх PRIMARY: R@1=2/3, R@20=2/3, R@50=3/3, MRR=0.6768. Это один дизайн-проект без независимого holdout. Исходный критерий 3/4 нельзя объявлять выполненным: четвёртая разметка оказалась ошибочной и исключена заранее.

## Компактное сравнение

Числа ниже — место заданного SKU, меньше лучше. Основной режим — image-only, MAX по трём render crops. Catalog self и perturbed дали rank 1 для каждого target у всех трёх baseline; это отдельный контроль, не результат по интерьеру.

| Target / SKU | Пул | Catalog self / perturbed | DINOv2 | OpenCLIP | SigLIP2 | SigLIP2 → DreamSim |
|---|---:|---:|---:|---:|---:|---:|
| F-01 / 50248 | 300 подвесов | 1 / 1 | 97 | 9 | 1 | 24 |
| F-03 / FR2066WL-L40B | 300 настенных | 1 / 1 | 3 | 12 | 1 | 1 |
| F-04 / LSP-7187 | 300 настенных | 1 / 1 | 110 | 60 | 33 | 7 |
| F-06 / 85078/01, diagnostic | 19 направленных/трековых | 1 / 1 | 1 | 1 | 1 | 1 |

**F-06 не доказывает успешный поиск:** в КП показан широкий диск, на render — узкий цилиндр. В таком маленьком пуле попадание в Top20 вообще неизбежно. Это диагностический тест ошибочной разметки, а не PRIMARY и не подтверждение совместимости/монтажа.

**F-04 — слабая разметка для exact-identity:** на render два смещённых округлых контура с тёмным центром, у LSP-7187 — светящаяся спиральная лента вокруг оси. Оставлен заданный пользователем SKU из КП; его rank измеряет возврат выбранного в КП аналога, а не доказанную идентичность изображённому предмету. После раскрытия рангов target не исключался. В masked review этот SKU не был признан близким по конструкции даже после подъёма в Top10; единственный plausible контурный аналог оказался другим товаром.

## Что дала визуальная проверка

Все 24 анонимных contact sheets открыты до раскрытия рангов; оценено по 20 карточек, для F-06 — 19. Strong означает близкую геометрию и цвет; plausible — узнаваемый конструктивный аналог с отличиями. Цена, наличие, размеры и монтаж здесь не подтверждаются.

| Target | SigLIP2 strong / plausible / poor | После DreamSim |
|---|---:|---:|
| F-01 | 2 / 10 / 8 | 2 / 8 / 10 |
| F-03 | 1 / 12 / 7 | 1 / 11 / 8 |
| F-04 | 0 / 1 / 19 | 0 / 1 / 19 |
| F-06, Top19 | 0 / 0 / 19 | 0 / 0 / 19 |

Это число визуально полезных карточек, включая сам positive, если он похож, а не число гарантированно подходящих замен. Полные strong/plausible/poor для каждой модели приведены ниже и сохранены в `manual_review.json`.

## Модели и дополнительные проверки

- DINOv2: хороший F-03 (#3), слабые F-01 (#97) и F-04 (#110). DreamSim улучшил F-03 до #1, но не мог вернуть F-01/F-04, отсутствующие в исходном Top50.
- OpenCLIP: #9 / #12 / #60. DreamSim: #14 / #1 / отсутствует. MEAN даёт #13 / #8 / #33, поэтому MAX не является универсально лучшей агрегацией.
- SigLIP2: лучший баланс индивидуальных ranks и визуальной полезности. Для F-01/F-03 rank 1 сохраняется на каждом из трёх crops. F-04: tight #37, medium #33, alternate #31; MAX #33, MEAN #32.
- DreamSim поверх SigLIP2: F-04 #33→#7, но F-01 #1→#24; F-03 остаётся #1. Общий R@20 не вырос, MRR снизился с 0.6768 до 0.3948. Это полезная дополнительная оценка, не обязательная замена исходного порядка. Нельзя задним числом выбрать лучшую модель отдельно для каждого golden и назвать это проверенным pipeline.
- DINOv3 Small не запущен: официальный checkpoint вернул HTTP 401 / gated repository. Зеркала и обход доступа не использовались. MobileCLIP2 повторно не запускался, как разрешено заданием. Текстовые mixtures и fine-tuning не выполнялись.
- Gallery: до 3 известных фото для Top20 SigLIP2 плюс positive, всего 137 файлов. DINOv2 F-01 улучшился #97→#13. SigLIP2 F-01/F-03 остались #1, F-04 #33→#30. Это label-assisted secondary: дополнительные фото есть не у всех товаров; нельзя переносить улучшение на весь каталог. У F-04 не было нового ракурса positive, только дубликат primary.
- Нейтрализация фона не даёт стабильного выигрыша. DINOv2 F-01 tight #115→#65, OpenCLIP F-03 #32→#15; SigLIP2 F-04 ухудшился #37→#54. Сложная segmentation не нужна для объяснения полученного результата.
- Tight crop не автоматически лучше medium: малая исходная детализация, пропорции, штатное обрезание encoder и контекст влияют совместно. Все 12 финальных crops проверены глазами. Bounding-box object_area_ratio составляет примерно 0.10–0.74; по трём PRIMARY статистическая корреляция не заявляется.

## Где остаётся domain gap

Все catalog sanity-тесты успешны, но при переходе к render качество зависит от предмета и модели. На F-01 DINOv2 теряет маленький цилиндр в изменённом масштабе и контексте; SigLIP2 решает этот пример. F-03 распознаётся уверенно. На F-04 смешиваются два фактора: render→catalog domain gap и неточная конструктивная разметка аналога из КП. Приписывать всю ошибку encoder было бы неверно. F-06 — в первую очередь ошибка сопоставления, а не ошибка retrieval.

Следовательно, сильное утверждение «generic local embeddings не подходят» опровергается F-01/F-03. Обратное утверждение «можно без проверки автоматически найти нужный светильник» результатами не подтверждено.

## Практический следующий шаг — рекомендация, не внедрение

Сохранить существующую архитектуру и отдельно проверить на новых проектах: доказательные требования и несколько crops → same-family/технические ограничения → локальный image index SigLIP2 → широкий Top50 → Codex сравнивает конструкцию → действующие availability gates и live recheck → итоговые кандидаты. DreamSim можно показывать как дополнительный порядок/сигнал внутри Top50, не скрывая исходный SigLIP2 rank и не отбрасывая его лидеров автоматически.

Перед расширением production coverage нужен небольшой независимый набор новых проектов с проверенной связью render↔SKU и оценкой полезности для менеджера. Никакие production-файлы, crawler/hydration, availability policy, frontend или клиентские отчёты в этом проходе не изменены.

CPU позволяет такой workflow: warmed SigLIP2 ~0.273 с/изображение, DreamSim ~1.043 с/изображение; рабочий набор процессов ~1.0 и ~1.6 GiB соответственно. Это измерения batch=1 на 12 queries, не обещание скорости полного каталога. Кэширование делает повторную оценку дешёвой; первичная загрузка весов DreamSim заняла существенно больше времени, чем дальнейший inference.


# Controlled visual benchmark

Evaluation-only benchmark: every golden positive is present in a fixed same-family pool; golden identity is not used in embeddings, distractor selection, scoring, or reranking.

## Pools

| target | family | products | primary |
|---|---|---:|---|
| F-01 | pendant_single | 300 | yes |
| F-03 | wall_sconce | 300 | yes |
| F-04 | decorative_wall | 300 | yes |
| F-06 | track_spot | 19 | no |

F-06 is diagnostic rather than PRIMARY: its KP image is a wide disk track light, while the project render shows narrow cylinders.

## Main results

| target | model | crop variant | golden rank | R@10 | R@20 | R@50 | useful Top20 |
|---|---|---|---:|---:|---:|---:|---:|
| F-01 | dinov2_vits14 | tight | 115 | 0 | 0 | 0 | not reviewed |
| F-01 | dinov2_vits14 | medium | 97 | 0 | 0 | 0 | not reviewed |
| F-01 | dinov2_vits14 | alternate | 86 | 0 | 0 | 0 | not reviewed |
| F-01 | dinov2_vits14 | max | 97 | 0 | 0 | 0 | 9 |
| F-01 | dinov2_vits14 | mean | 92 | 0 | 0 | 0 | not reviewed |
| F-03 | dinov2_vits14 | tight | 7 | 1 | 1 | 1 | not reviewed |
| F-03 | dinov2_vits14 | medium | 5 | 1 | 1 | 1 | not reviewed |
| F-03 | dinov2_vits14 | alternate | 3 | 1 | 1 | 1 | not reviewed |
| F-03 | dinov2_vits14 | max | 3 | 1 | 1 | 1 | 13 |
| F-03 | dinov2_vits14 | mean | 3 | 1 | 1 | 1 | not reviewed |
| F-04 | dinov2_vits14 | tight | 105 | 0 | 0 | 0 | not reviewed |
| F-04 | dinov2_vits14 | medium | 101 | 0 | 0 | 0 | not reviewed |
| F-04 | dinov2_vits14 | alternate | 140 | 0 | 0 | 0 | not reviewed |
| F-04 | dinov2_vits14 | max | 110 | 0 | 0 | 0 | 1 |
| F-04 | dinov2_vits14 | mean | 106 | 0 | 0 | 0 | not reviewed |
| F-06 | dinov2_vits14 | tight | 2 | 1 | 1 | 1 | not reviewed |
| F-06 | dinov2_vits14 | medium | 1 | 1 | 1 | 1 | not reviewed |
| F-06 | dinov2_vits14 | alternate | 1 | 1 | 1 | 1 | not reviewed |
| F-06 | dinov2_vits14 | max | 1 | 1 | 1 | 1 | 0 |
| F-06 | dinov2_vits14 | mean | 1 | 1 | 1 | 1 | not reviewed |
| F-01 | dinov2_vits14__dreamsim | max | — | 0 | 0 | 0 | 12 |
| F-01 | dinov2_vits14__dreamsim | mean | — | 0 | 0 | 0 | not reviewed |
| F-03 | dinov2_vits14__dreamsim | max | 1 | 1 | 1 | 1 | 13 |
| F-03 | dinov2_vits14__dreamsim | mean | 1 | 1 | 1 | 1 | not reviewed |
| F-04 | dinov2_vits14__dreamsim | max | — | 0 | 0 | 0 | 1 |
| F-04 | dinov2_vits14__dreamsim | mean | — | 0 | 0 | 0 | not reviewed |
| F-06 | dinov2_vits14__dreamsim | max | 1 | 1 | 1 | 1 | 0 |
| F-06 | dinov2_vits14__dreamsim | mean | 1 | 1 | 1 | 1 | not reviewed |
| F-01 | openclip_vit_b32 | tight | 19 | 0 | 1 | 1 | not reviewed |
| F-01 | openclip_vit_b32 | medium | 9 | 1 | 1 | 1 | not reviewed |
| F-01 | openclip_vit_b32 | alternate | 13 | 0 | 1 | 1 | not reviewed |
| F-01 | openclip_vit_b32 | max | 9 | 1 | 1 | 1 | 5 |
| F-01 | openclip_vit_b32 | mean | 13 | 0 | 1 | 1 | not reviewed |
| F-03 | openclip_vit_b32 | tight | 32 | 0 | 0 | 1 | not reviewed |
| F-03 | openclip_vit_b32 | medium | 12 | 0 | 1 | 1 | not reviewed |
| F-03 | openclip_vit_b32 | alternate | 26 | 0 | 0 | 1 | not reviewed |
| F-03 | openclip_vit_b32 | max | 12 | 0 | 1 | 1 | 13 |
| F-03 | openclip_vit_b32 | mean | 8 | 1 | 1 | 1 | not reviewed |
| F-04 | openclip_vit_b32 | tight | 32 | 0 | 0 | 1 | not reviewed |
| F-04 | openclip_vit_b32 | medium | 58 | 0 | 0 | 0 | not reviewed |
| F-04 | openclip_vit_b32 | alternate | 36 | 0 | 0 | 1 | not reviewed |
| F-04 | openclip_vit_b32 | max | 60 | 0 | 0 | 0 | 0 |
| F-04 | openclip_vit_b32 | mean | 33 | 0 | 0 | 1 | not reviewed |
| F-06 | openclip_vit_b32 | tight | 6 | 1 | 1 | 1 | not reviewed |
| F-06 | openclip_vit_b32 | medium | 1 | 1 | 1 | 1 | not reviewed |
| F-06 | openclip_vit_b32 | alternate | 2 | 1 | 1 | 1 | not reviewed |
| F-06 | openclip_vit_b32 | max | 1 | 1 | 1 | 1 | 0 |
| F-06 | openclip_vit_b32 | mean | 2 | 1 | 1 | 1 | not reviewed |
| F-01 | openclip_vit_b32__dreamsim | max | 14 | 0 | 1 | 1 | 8 |
| F-01 | openclip_vit_b32__dreamsim | mean | 13 | 0 | 1 | 1 | not reviewed |
| F-03 | openclip_vit_b32__dreamsim | max | 1 | 1 | 1 | 1 | 11 |
| F-03 | openclip_vit_b32__dreamsim | mean | 1 | 1 | 1 | 1 | not reviewed |
| F-04 | openclip_vit_b32__dreamsim | max | — | 0 | 0 | 0 | 0 |
| F-04 | openclip_vit_b32__dreamsim | mean | — | 0 | 0 | 0 | not reviewed |
| F-06 | openclip_vit_b32__dreamsim | max | 1 | 1 | 1 | 1 | 0 |
| F-06 | openclip_vit_b32__dreamsim | mean | 1 | 1 | 1 | 1 | not reviewed |
| F-01 | siglip2_base_patch16_224 | tight | 1 | 1 | 1 | 1 | not reviewed |
| F-01 | siglip2_base_patch16_224 | medium | 1 | 1 | 1 | 1 | not reviewed |
| F-01 | siglip2_base_patch16_224 | alternate | 1 | 1 | 1 | 1 | not reviewed |
| F-01 | siglip2_base_patch16_224 | max | 1 | 1 | 1 | 1 | 12 |
| F-01 | siglip2_base_patch16_224 | mean | 1 | 1 | 1 | 1 | not reviewed |
| F-03 | siglip2_base_patch16_224 | tight | 1 | 1 | 1 | 1 | not reviewed |
| F-03 | siglip2_base_patch16_224 | medium | 1 | 1 | 1 | 1 | not reviewed |
| F-03 | siglip2_base_patch16_224 | alternate | 1 | 1 | 1 | 1 | not reviewed |
| F-03 | siglip2_base_patch16_224 | max | 1 | 1 | 1 | 1 | 13 |
| F-03 | siglip2_base_patch16_224 | mean | 1 | 1 | 1 | 1 | not reviewed |
| F-04 | siglip2_base_patch16_224 | tight | 37 | 0 | 0 | 1 | not reviewed |
| F-04 | siglip2_base_patch16_224 | medium | 33 | 0 | 0 | 1 | not reviewed |
| F-04 | siglip2_base_patch16_224 | alternate | 31 | 0 | 0 | 1 | not reviewed |
| F-04 | siglip2_base_patch16_224 | max | 33 | 0 | 0 | 1 | 1 |
| F-04 | siglip2_base_patch16_224 | mean | 32 | 0 | 0 | 1 | not reviewed |
| F-06 | siglip2_base_patch16_224 | tight | 1 | 1 | 1 | 1 | not reviewed |
| F-06 | siglip2_base_patch16_224 | medium | 1 | 1 | 1 | 1 | not reviewed |
| F-06 | siglip2_base_patch16_224 | alternate | 1 | 1 | 1 | 1 | not reviewed |
| F-06 | siglip2_base_patch16_224 | max | 1 | 1 | 1 | 1 | 0 |
| F-06 | siglip2_base_patch16_224 | mean | 1 | 1 | 1 | 1 | not reviewed |
| F-01 | siglip2_base_patch16_224__dreamsim | max | 24 | 0 | 0 | 1 | 10 |
| F-01 | siglip2_base_patch16_224__dreamsim | mean | 22 | 0 | 0 | 1 | not reviewed |
| F-03 | siglip2_base_patch16_224__dreamsim | max | 1 | 1 | 1 | 1 | 12 |
| F-03 | siglip2_base_patch16_224__dreamsim | mean | 1 | 1 | 1 | 1 | not reviewed |
| F-04 | siglip2_base_patch16_224__dreamsim | max | 7 | 1 | 1 | 1 | 1 |
| F-04 | siglip2_base_patch16_224__dreamsim | mean | 6 | 1 | 1 | 1 | not reviewed |
| F-06 | siglip2_base_patch16_224__dreamsim | max | 1 | 1 | 1 | 1 | 0 |
| F-06 | siglip2_base_patch16_224__dreamsim | mean | 1 | 1 | 1 | 1 | not reviewed |

## Catalog-to-catalog vs render-to-catalog

| target | model | catalog self | perturbed catalog | render MAX |
|---|---|---:|---:|---:|
| F-01 | dinov2_vits14 | 1 | 1 | 97 |
| F-03 | dinov2_vits14 | 1 | 1 | 3 |
| F-04 | dinov2_vits14 | 1 | 1 | 110 |
| F-06 | dinov2_vits14 | 1 | 1 | 1 |
| F-01 | dinov2_vits14__dreamsim | — | — | — |
| F-03 | dinov2_vits14__dreamsim | — | — | 1 |
| F-04 | dinov2_vits14__dreamsim | — | — | — |
| F-06 | dinov2_vits14__dreamsim | — | — | 1 |
| F-01 | openclip_vit_b32 | 1 | 1 | 9 |
| F-03 | openclip_vit_b32 | 1 | 1 | 12 |
| F-04 | openclip_vit_b32 | 1 | 1 | 60 |
| F-06 | openclip_vit_b32 | 1 | 1 | 1 |
| F-01 | openclip_vit_b32__dreamsim | — | — | 14 |
| F-03 | openclip_vit_b32__dreamsim | — | — | 1 |
| F-04 | openclip_vit_b32__dreamsim | — | — | — |
| F-06 | openclip_vit_b32__dreamsim | — | — | 1 |
| F-01 | siglip2_base_patch16_224 | 1 | 1 | 1 |
| F-03 | siglip2_base_patch16_224 | 1 | 1 | 1 |
| F-04 | siglip2_base_patch16_224 | 1 | 1 | 33 |
| F-06 | siglip2_base_patch16_224 | 1 | 1 | 1 |
| F-01 | siglip2_base_patch16_224__dreamsim | — | — | 24 |
| F-03 | siglip2_base_patch16_224__dreamsim | — | — | 1 |
| F-04 | siglip2_base_patch16_224__dreamsim | — | — | 7 |
| F-06 | siglip2_base_patch16_224__dreamsim | — | — | 1 |

## Manual visual usefulness (MAX, before identity reveal)

| model | target | strong | plausible | poor | useful |
|---|---|---:|---:|---:|---:|
| dinov2_vits14 | F-01 | 1 | 8 | 11 | 9 |
| dinov2_vits14 | F-03 | 1 | 12 | 7 | 13 |
| dinov2_vits14 | F-04 | 0 | 1 | 19 | 1 |
| dinov2_vits14 | F-06 | 0 | 0 | 19 | 0 |
| dinov2_vits14__dreamsim | F-01 | 1 | 11 | 8 | 12 |
| dinov2_vits14__dreamsim | F-03 | 1 | 12 | 7 | 13 |
| dinov2_vits14__dreamsim | F-04 | 0 | 1 | 19 | 1 |
| dinov2_vits14__dreamsim | F-06 | 0 | 0 | 19 | 0 |
| openclip_vit_b32 | F-01 | 2 | 3 | 15 | 5 |
| openclip_vit_b32 | F-03 | 1 | 12 | 7 | 13 |
| openclip_vit_b32 | F-04 | 0 | 0 | 20 | 0 |
| openclip_vit_b32 | F-06 | 0 | 0 | 19 | 0 |
| openclip_vit_b32__dreamsim | F-01 | 2 | 6 | 12 | 8 |
| openclip_vit_b32__dreamsim | F-03 | 1 | 10 | 9 | 11 |
| openclip_vit_b32__dreamsim | F-04 | 0 | 0 | 20 | 0 |
| openclip_vit_b32__dreamsim | F-06 | 0 | 0 | 19 | 0 |
| siglip2_base_patch16_224 | F-01 | 2 | 10 | 8 | 12 |
| siglip2_base_patch16_224 | F-03 | 1 | 12 | 7 | 13 |
| siglip2_base_patch16_224 | F-04 | 0 | 1 | 19 | 1 |
| siglip2_base_patch16_224 | F-06 | 0 | 0 | 19 | 0 |
| siglip2_base_patch16_224__dreamsim | F-01 | 2 | 8 | 10 | 10 |
| siglip2_base_patch16_224__dreamsim | F-03 | 1 | 11 | 8 | 12 |
| siglip2_base_patch16_224__dreamsim | F-04 | 0 | 1 | 19 | 1 |
| siglip2_base_patch16_224__dreamsim | F-06 | 0 | 0 | 19 | 0 |

## Model summary

Quality uses MAX across render crops. Comparable inference cost is in the warmed CPU table; run elapsed time includes cache effects and, for DreamSim, cumulative downloads/earlier sources.

- **dinov2_vits14**: PRIMARY R@20=0.3333, R@50=0.3333, MRR=0.1176; embedding dim 384.
- **dinov2_vits14__dreamsim**: PRIMARY R@20=0.3333, R@50=0.3333, MRR=0.3333; embedding dim 1792.
- **openclip_vit_b32**: PRIMARY R@20=0.6667, R@50=0.6667, MRR=0.0704; embedding dim 512.
- **openclip_vit_b32__dreamsim**: PRIMARY R@20=0.6667, R@50=0.6667, MRR=0.3571; embedding dim 1792.
- **siglip2_base_patch16_224**: PRIMARY R@20=0.6667, R@50=1.0, MRR=0.6768; embedding dim 768.
- **siglip2_base_patch16_224__dreamsim**: PRIMARY R@20=0.6667, R@50=1.0, MRR=0.3948; embedding dim 1792.
- **dinov3_vits16 failed**: OSError: You are trying to access a gated repo.
Make sure to have access to it at https://huggingface.co/facebook/dinov3-vits16-pretrain-lvd1689m.
401 Client Error. (Request ID: Root=1-6a8fcbb1-6a0264911b3180dc1699d10b;e1691d77-ec7f-41a1-a248-0af58657f3e1)

Cannot access gated repo for url https://huggingface.co/facebook/dinov3-vits16-pretrain-lvd1689m/resolve/main/processor_config.json.
Access to model facebook/dinov3-vits16-pretrain-lvd1689m is restricted. You must have access to it and be authenticated to access it. Please log in.

## PRIMARY aggregation (3 targets)

| model | variant | R@1 | R@5 | R@10 | R@20 | R@50 | R@100 | MRR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| dinov2_vits14 | tight | 0.0 | 0.0 | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.0537 |
| dinov2_vits14 | medium | 0.0 | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.6667 | 0.0734 |
| dinov2_vits14 | alternate | 0.0 | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.6667 | 0.1174 |
| dinov2_vits14 | max | 0.0 | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.6667 | 0.1176 |
| dinov2_vits14 | mean | 0.0 | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.6667 | 0.1179 |
| dinov2_vits14__dreamsim | max | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.3333 |
| dinov2_vits14__dreamsim | mean | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 0.3333 |
| openclip_vit_b32 | tight | 0.0 | 0.0 | 0.0 | 0.3333 | 1.0 | 1.0 | 0.0384 |
| openclip_vit_b32 | medium | 0.0 | 0.0 | 0.3333 | 0.6667 | 0.6667 | 1.0 | 0.0706 |
| openclip_vit_b32 | alternate | 0.0 | 0.0 | 0.0 | 0.3333 | 1.0 | 1.0 | 0.0477 |
| openclip_vit_b32 | max | 0.0 | 0.0 | 0.3333 | 0.6667 | 0.6667 | 1.0 | 0.0704 |
| openclip_vit_b32 | mean | 0.0 | 0.0 | 0.3333 | 0.6667 | 1.0 | 1.0 | 0.0774 |
| openclip_vit_b32__dreamsim | max | 0.3333 | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 0.6667 | 0.3571 |
| openclip_vit_b32__dreamsim | mean | 0.3333 | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 0.6667 | 0.3590 |
| siglip2_base_patch16_224 | tight | 0.6667 | 0.6667 | 0.6667 | 0.6667 | 1.0 | 1.0 | 0.6757 |
| siglip2_base_patch16_224 | medium | 0.6667 | 0.6667 | 0.6667 | 0.6667 | 1.0 | 1.0 | 0.6768 |
| siglip2_base_patch16_224 | alternate | 0.6667 | 0.6667 | 0.6667 | 0.6667 | 1.0 | 1.0 | 0.6774 |
| siglip2_base_patch16_224 | max | 0.6667 | 0.6667 | 0.6667 | 0.6667 | 1.0 | 1.0 | 0.6768 |
| siglip2_base_patch16_224 | mean | 0.6667 | 0.6667 | 0.6667 | 0.6667 | 1.0 | 1.0 | 0.6771 |
| siglip2_base_patch16_224__dreamsim | max | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 1.0 | 1.0 | 0.3948 |
| siglip2_base_patch16_224__dreamsim | mean | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 1.0 | 1.0 | 0.4040 |

## DreamSim rerank (MAX)

| target | source | before | after | positive in Top50 |
|---|---|---:|---:|---|
| F-01 | dinov2_vits14 | 97 | outside source Top50 | False |
| F-03 | dinov2_vits14 | 3 | 1 | True |
| F-04 | dinov2_vits14 | 110 | outside source Top50 | False |
| F-06 | dinov2_vits14 | 1 | 1 | True |
| F-01 | openclip_vit_b32 | 9 | 14 | True |
| F-03 | openclip_vit_b32 | 12 | 1 | True |
| F-04 | openclip_vit_b32 | 60 | outside source Top50 | False |
| F-06 | openclip_vit_b32 | 1 | 1 | True |
| F-01 | siglip2_base_patch16_224 | 1 | 24 | True |
| F-03 | siglip2_base_patch16_224 | 1 | 1 | True |
| F-04 | siglip2_base_patch16_224 | 33 | 7 | True |
| F-06 | siglip2_base_patch16_224 | 1 | 1 | True |

## Secondary diagnostics (not PRIMARY)

| target | model | original tight | neutral background | baseline MAX | gallery MAX | gallery images |
|---|---|---:|---:|---:|---:|---:|
| F-01 | dinov2_vits14 | 115 | 65 | 97 | 13 | 53 |
| F-03 | dinov2_vits14 | 7 | 5 | 3 | 4 | 41 |
| F-04 | dinov2_vits14 | 105 | 86 | 110 | 110 | 36 |
| F-06 | dinov2_vits14 | 2 | 6 | 1 | 1 | 7 |
| F-01 | openclip_vit_b32 | 19 | 21 | 9 | 16 | 53 |
| F-03 | openclip_vit_b32 | 32 | 15 | 12 | 14 | 41 |
| F-04 | openclip_vit_b32 | 32 | 37 | 60 | 59 | 36 |
| F-06 | openclip_vit_b32 | 6 | 6 | 1 | 1 | 7 |
| F-01 | siglip2_base_patch16_224 | 1 | 1 | 1 | 1 | 53 |
| F-03 | siglip2_base_patch16_224 | 1 | 1 | 1 | 1 | 41 |
| F-04 | siglip2_base_patch16_224 | 37 | 54 | 33 | 30 | 36 |
| F-06 | siglip2_base_patch16_224 | 1 | 1 | 1 | 1 | 7 |

## Warmed CPU performance

| model | load s | sec/image | median query s | RSS MiB | dimension | embedding cache MiB |
|---|---:|---:|---:|---:|---:|---:|
| dinov2_vits14 | 1.58 | 0.097 | 0.100 | 486.5 | 384 | 1.81 |
| dreamsim_ensemble | 7.82 | 1.043 | 0.969 | 1571.8 | 1792 | 2.02 |
| openclip_vit_b32 | 5.37 | 0.107 | 0.107 | 1025.7 | 512 | 3.94 |
| siglip2_base_patch16_224 | 4.83 | 0.273 | 0.277 | 1011.9 | 768 | 3.23 |

## Query crops

- F-01 tight: page 2, object_area_ratio≈0.4; one complete cylinder, little room context; source-resolution limited.
- F-01 medium: page 2, object_area_ratio≈0.15; same cylinder with modest ceiling/wall context.
- F-01 alternate: page 11, object_area_ratio≈0.41; one full cylinder from a second room angle.
- F-03 tight: page 11, object_area_ratio≈0.74; complete shade, base and reading arm; close bounding box.
- F-03 medium: page 11, object_area_ratio≈0.19; sconce with modest marble-wall context.
- F-03 alternate: page 11, object_area_ratio≈0.61; right-side second instance, tightly framed.
- F-04 tight: page 18, object_area_ratio≈0.72; complete pair of offset oval contours and dark center; close bounding box.
- F-04 medium: page 18, object_area_ratio≈0.23; left light with a small surrounding dark-wall area.
- F-04 alternate: page 18, object_area_ratio≈0.68; right-side second instance tightly framed.
- F-06 tight: page 29, object_area_ratio≈0.55; one narrow black ceiling cylinder; top limited by original page.
- F-06 medium: page 29, object_area_ratio≈0.1; one cylinder with local ceiling context.
- F-06 alternate: page 30, object_area_ratio≈0.38; single cylinder in adjacent room angle.

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
