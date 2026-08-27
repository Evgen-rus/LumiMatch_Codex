# CPU visual retrieval spike

Дата прогона: 2026-08-26.

Это изолированный экспериментальный контур в `experiments/visual_retrieval`. Он не изменяет V4 production pipeline, availability gates, production scoring или пользовательский отчёт. В production по-прежнему действует текущая строгая политика подтверждённого `in_stock`.

## Цель и границы

Spike измеряет качество visual retrieval независимо от текущей доступности товара:

- natural corpus строится только из production URL inventory пяти разрешённых поставщиков: `eurosvet.ru`, `shop.lussole.ru`, `freya-light.com`, `kinklight.ru`, `odeon-light.com`;
- natural selection не читает golden set, не добавляет golden SKU и не использует `expected_kp.docx`;
- запросы — только project reference crops из `FixtureRequirement.reference_crop_paths`;
- golden set читается только после ranking для evaluation и для отдельного `oracle` scope;
- `SYSTEM_BOM`, unmapped rows и evaluation targets с confidence ниже 0.40 исключены из метрик;
- основной baseline — чистый image-to-image; image+text проверен вторично только для OpenCLIP;
- hard gates production не ослаблялись. Contact sheets проверены вручную Codex.

## Corpus

Natural corpus получен из 6 509 inventory URLs. Для bounded passes использовалась детерминированная evenly-spaced выборка внутри supplier, чтобы не измерять только первую категорию URL. Итоговый natural scope:

| supplier | ready images |
|---|---:|
| eurosvet.ru | 1 217 |
| freya-light.com | 421 |
| kinklight.ru | 314 |
| shop.lussole.ru | 462 |
| odeon-light.com | 0 |
| **total** | **2 414** |

В corpus database также сохранены 154 `image_failed` и 157 `no_image` records. Для odeon-light.com 62 страницы были доступны по HTML, но изображения не удалось получить; товарные изображения не подставлялись искусственно.

Natural primary index содержит 2 414 image rows и 2 263 уникальных content-hash. Gallery-3 не запускался: ручной review primary Top-20 не показал сильных visual finalists, поэтому дополнительные ракурсы не были бы содержательным исправлением category mismatch.

## Models and CPU performance

| model | checkpoint | dim | smoke | RSS peak sampled | result |
|---|---|---:|---:|---:|---|
| DINOv2 ViT-S/14 | `facebookresearch/dinov2:dinov2_vits14` | 384 | 4.81 img/s / 250 | ~487 MB | ready |
| OpenCLIP ViT-B/32 | public OpenAI `openai` tag | 512 | 6.93 img/s / 250 | ~1 075 MB | ready |
| Apple MobileCLIP2-S0 | `dfndr2b` | — | — | — | checkpoint download did not complete |
| Apple MobileCLIP2-S2 | `dfndr2b` | — | — | — | checkpoint download did not complete |

The requested OpenCLIP family was tested with the public `openai` ViT-B/32 checkpoint because a LAION blob did not complete in the current environment. Official model references: [OpenCLIP](https://github.com/mlfoundations/open_clip), [Apple MobileCLIP](https://github.com/apple/ml-mobileclip), [Meta DINOv2](https://github.com/facebookresearch/dinov2).

Model failures are recorded in `output/visual_spike/model_failure_mobileclip2_s0.json` and `model_failure_mobileclip2_s2.json`; they are not represented as zero-quality retrieval metrics.

## Golden coverage and retrieval metrics

There are 4 primary visual targets (confidence >= 0.60). Only 1/4 target SKU is present in the natural corpus. The separate oracle enrichment found 2 target pages/images that were absent from natural: `FR2066WL-L40B` and `LSP-4016` (the latter is exploratory). Thus oracle scope has 2/4 primary target SKU coverage; it is evaluation-only and is never merged into natural.

### Primary targets, image-only

`R@K` counts a golden SKU within the first K product results after image ranking. A missing SKU is not assigned a rank.

| scope | model | corpus SKU coverage | R@1 | R@5 | R@10 | R@20 | R@50 | R@100 | MRR | median rank | ranks for F-01/F-03/F-04/F-06 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| natural | DINOv2 | 1/4 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0014 | 182 | — / — / 182 / — |
| natural | OpenCLIP | 1/4 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0013 | 191 | — / — / 191 / — |
| oracle | DINOv2 | 2/4 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0020 | 293 | — / 403 / 183 / — |
| oracle | OpenCLIP | 2/4 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0015 | 739 | — / 1287 / 191 / — |

For exploratory targets, natural DINOv2 had MRR 0.0005 and natural OpenCLIP MRR 0.0016. Neither model placed a primary target within Top-100. OpenCLIP image+text variants were secondary diagnostics: adding text decreased primary MRR from 0.0013 to 0.0012 on natural and from 0.0015 to 0.0014 on oracle (`mixed_0.70`), so text was not promoted to the primary path.

## Manual visual review

Top-20 sheets are under `output/visual_spike/review/` and the manual result is in `output/visual_spike/review/qualitative_review.json`.

- Strong visual finalists: **0** across F-01…F-08.
- Near-but-rejected observations: 4, for F-02, F-03, F-07 and F-08.
- F-01 top DINO results are linear pendants with spherical diffusers, not compact black cylinders.
- F-03 has a related wall-sconce family, but the best candidates differ materially in shade/base geometry.
- F-04, F-05 and F-06 retain mounting/family conflicts.
- No old-style crystal/chandelier result was accepted as a visual match; crystal products visible lower in sheets remain rejected by manual review.

The review therefore does not produce a candidate list for customer delivery. It deliberately returns zero rather than filling the output with weak matches.

## Reproduction

Use the isolated visual environment:

```powershell
.\\.venv-visual\\Scripts\\python.exe -m experiments.visual_retrieval build-corpus --workers 4 --timeout 5 --delay 0.05
.\\.venv-visual\\Scripts\\python.exe -m experiments.visual_retrieval smoke --models dinov2_vits14,openclip_vit_b32 --limit 250 --batch-size 16 --threads 4
.\\.venv-visual\\Scripts\\python.exe -m experiments.visual_retrieval embed --model dinov2_vits14 --variant primary --scope natural
.\\.venv-visual\\Scripts\\python.exe -m experiments.visual_retrieval benchmark --model dinov2_vits14 --variant primary --scope natural
```

`data/visual_spike/visual_corpus.sqlite3`, image cache, model cache, embedding cache and indices are resumable and isolated. Machine-readable and Markdown outputs are under `output/visual_spike/`.

## Conclusion

This sample does not support the hypothesis that availability alone is the main reason for the weak visual result. Natural corpus coverage is incomplete (1/4 primary target SKUs), but oracle-enriched evaluation also leaves both working models at R@100 = 0 and manual visual review finds no strong Top-20 finalist. The current limiting factors are corpus/retrieval quality and family-aware visual candidate selection; availability should remain a separate production concern and was not weakened by this spike.

Recommended next experiment: improve natural corpus category coverage and add an explicit family/mounting-aware post-retrieval review/evaluation set, then rerun this isolated benchmark. Do not use this result as authorization to relax production availability gates.
