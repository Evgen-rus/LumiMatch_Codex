# Golden benchmark — Dan

Generated: `2026-08-25T06:34:29.865772+00:00`. Golden source is evaluation-only; it does not alter production scores.

## Summary

- VISUAL_SELECTION: `11`; SYSTEM_BOM: `11`.
- Discovery found: `6`; exact/page-label SKU evidence: `5`; parsed: `8`; with photo: `6`.
- Retrieval: `retrieval@20=4`, `retrieval@50=4`, `retrieval@100=4`; fresh visual: `visual@1=1`, `visual@3=1`, `visual@5=2`, `visual@10=2`.

## Visual retrieval

| F | target | supplier | independent rank | production rank | visual@1 | visual@3 | visual@5 | visual@10 | diagnosis |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| F-01 | 50248 | eurosvet.ru |  |  | False | False | False | False | not_discovered |
|  |  |  |  |  |  |  |  |  |  |
| F-03 | 2207B,19 | kinklight.ru | 17 |  | False | False | False | False | availability_gate_only |
| F-02 | LL-894-1 |  |  |  | False | False | False | False | not_discovered |
| F-03 | FR2066WL-L40B | freya-light.com | 1 | 1 | True | True | True | True | retrieved |
| F-04 | 5610/37WL | odeon-light.com |  |  | False | False | False | False | not_discovered |
| F-05 | 1108 | eurosvet.ru |  |  | False | False | False | False | not_discovered |
| F-05 | lsp-4001 | shop.lussole.ru |  |  | False | False | False | False | retrieval_or_hard_gate_failure |
| F-04 | lsp-7187 | shop.lussole.ru | 4 | 2 | False | False | True | True | retrieved |
| F-01 | LSP-4016 | shop.lussole.ru | 18 | 9 | False | False | False | False | retrieved |
| F-06 | 85078/01 | eurosvet.ru |  |  | False | False | False | False | not_discovered |

## System BOM coverage

`{"items": 11, "discovered": 3, "parsed": 0, "found": 0, "photo": 0, "decorative_visual_metrics_excluded": true, "items_by_category": {"led_strip": 2, "power_supply": 4, "profile_connector": 2, "track_rail": 1, "track_suspension": 2}}`

SYSTEM_BOM items are excluded from decorative visual metrics.

## Supplier golden coverage

| supplier | targets | discovered | parsed | found | state |
|---|---:|---:|---:|---:|---|
| ambrella.biz | 4 | 3 | 0 | 0 | broken |
| eurosvet.ru | 5 | 2 | 2 | 0 | partial |
| freya-light.com | 1 | 1 | 1 | 1 | healthy |
| kinklight.ru | 2 | 2 | 2 | 2 | healthy |
| odeon-light.com | 1 | 0 | 0 | 0 | broken |
| shop.lussole.ru | 3 | 3 | 3 | 3 | healthy |

## Review integrity

Fresh contact sheets and fingerprints are under `output/golden/dan/review/`. A review from a previous candidate pool is not treated as current; a new SKU without a fresh review is not automatically rejected.
