# Golden benchmark — Dan

Production recall is measured against the clean production catalog. Target-aware golden discovery is reported separately.

- Production catalog recall: `0/10`; targeted discovery recall: `5/10`.
- Retrieval: `retrieval@20=0`, `retrieval@50=0`, `retrieval@100=0`.
- Actual visual review only: `visual@1=0`, `visual@3=0`, `visual@5=0`, `visual@10=0`.

| F | target | supplier | production | independent rank | production rank | visual status | visual rank | diagnosis |
|---|---|---|---|---:|---:|---|---:|---|
| F-01 | 50248 | eurosvet.ru | False |  |  | not_reviewed |  | not_in_production_catalog |
|  |  |  |  |  |  |  |  |  |
| F-03 | 2207B,19 | kinklight.ru | False |  |  | not_reviewed |  | targeted_only_not_in_production_catalog |
| F-02 | LL-894-1 |  | False |  |  | not_reviewed |  | not_in_production_catalog |
| F-03 | FR2066WL-L40B | freya-light.com | False |  |  | not_reviewed |  | targeted_only_not_in_production_catalog |
| F-04 | 5610/37WL | odeon-light.com | False |  |  | not_reviewed |  | not_in_production_catalog |
| F-05 | 1108 | eurosvet.ru | False |  |  | not_reviewed |  | not_in_production_catalog |
| F-05 | lsp-4001 | shop.lussole.ru | False |  |  | not_reviewed |  | targeted_only_not_in_production_catalog |
| F-04 | lsp-7187 | shop.lussole.ru | False |  |  | not_reviewed |  | targeted_only_not_in_production_catalog |
| F-01 | LSP-4016 | shop.lussole.ru | False |  |  | not_reviewed |  | targeted_only_not_in_production_catalog |
| F-06 | 85078/01 | eurosvet.ru | False |  |  | not_reviewed |  | not_in_production_catalog |

## Production catalog recall

`{"visual_targets": 11, "matchable_sku_targets": 10, "present": 0, "recall": 0.0, "not_matchable_no_sku": 1, "items": [{"kp_position": 1, "sku": "50248", "matched_fixture_requirement": "F-01", "status": "absent", "supplier": "eurosvet.ru", "url": null, "availability_status": null}, {"kp_position": 2, "sku": null, "matched_fixture_requirement": null, "status": "not_matchable_no_sku", "supplier": "kinklight.ru", "url": null, "availability_status": null}, {"kp_position": 3, "sku": "2207B,19", "matched_fixture_requirement": "F-03", "status": "absent", "supplier": "kinklight.ru", "url": null, "availability_status": null}, {"kp_position": 4, "sku": "LL-894-1", "matched_fixture_requirement": "F-02", "status": "absent", "supplier": null, "url": null, "availability_status": null}, {"kp_position": 9, "sku": "FR2066WL-L40B", "matched_fixture_requirement": "F-03", "status": "absent", "supplier": "freya-light.com", "url": null, "availability_status": null}, {"kp_position": 10, "sku": "5610/37WL", "matched_fixture_requirement": "F-04", "status": "absent", "supplier": "odeon-light.com", "url": null, "availability_status": null}, {"kp_position": 11, "sku": "1108", "matched_fixture_requirement": "F-05", "status": "absent", "supplier": "eurosvet.ru", "url": null, "availability_status": null}, {"kp_position": 12, "sku": "lsp-4001", "matched_fixture_requirement": "F-05", "status": "absent", "supplier": "shop.lussole.ru", "url": null, "availability_status": null}, {"kp_position": 13, "sku": "lsp-7187", "matched_fixture_requirement": "F-04", "status": "absent", "supplier": "shop.lussole.ru", "url": null, "availability_status": null}, {"kp_position": 14, "sku": "LSP-4016", "matched_fixture_requirement": "F-01", "status": "absent", "supplier": "shop.lussole.ru", "url": null, "availability_status": null}, {"kp_position": 16, "sku": "85078/01", "matched_fixture_requirement": "F-06", "status": "absent", "supplier": "eurosvet.ru", "url": null, "availability_status": null}], "note": "Measured only against the clean production catalog; golden discovery never populates it."}`

System BOM is excluded from decorative visual metrics.

Actual visual metrics are zero until the current run's review manifest is completed; no golden visual annotation is substituted.
