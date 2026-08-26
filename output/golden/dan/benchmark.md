# Golden benchmark — Dan

Production stages are evaluated only after the clean inventory and hydration run. Golden discovery is diagnostic and never populates production storage.

- Inventory recall: `5/10`; hydrated recall: `0/10`; sellable hydrated recall: `0/10`.
- Target-aware discovery (diagnostic only): `5/10`.
- Retrieval: `retrieval@20=0`, `retrieval@50=0`, `retrieval@100=0`.
- Review completeness: `True`.
- Actual visual@K: `@1=0`, `@3=0`, `@5=0`, `@10=0`.

| F | target | inventory | hydrated | independent rank | production rank | visual status | diagnosis |
|---|---|---|---|---:|---:|---|---|
| F-01 | 50248 | True | False |  |  | not_reviewed | hydration_miss |
|  |  |  |  |  |  |  |  |
| F-03 | 2207B,19 | False | False |  |  | not_reviewed | inventory_miss |
| F-02 | LL-894-1 | False | False |  |  | not_reviewed | inventory_miss |
| F-03 | FR2066WL-L40B | True | False |  |  | not_reviewed | hydration_miss |
| F-04 | 5610/37WL | False | False |  |  | not_reviewed | inventory_miss |
| F-05 | 1108 | False | False |  |  | not_reviewed | inventory_miss |
| F-05 | lsp-4001 | True | False |  |  | not_reviewed | hydration_miss |
| F-04 | lsp-7187 | True | False |  |  | not_reviewed | hydration_miss |
| F-01 | LSP-4016 | True | False |  |  | not_reviewed | hydration_miss |
| F-06 | 85078/01 | False | False |  |  | not_reviewed | inventory_miss |

## Stage recall

- Inventory: `{"visual_targets": 11, "matchable_sku_targets": 10, "present": 5, "recall": 0.5, "items": [{"kp_position": 1, "sku": "50248", "supplier": "eurosvet.ru", "in_inventory": true, "evidence": "normalized_sku_in_product_url", "product_url": "https://eurosvet.ru/catalog/lustri/podvesnoy-svetilnik-50248-1-led-belyy-a061424"}, {"kp_position": 2, "sku": null, "supplier": "kinklight.ru", "in_inventory": false, "evidence": null, "product_url": null}, {"kp_position": 3, "sku": "2207B,19", "supplier": "kinklight.ru", "in_inventory": false, "evidence": null, "product_url": null}, {"kp_position": 4, "sku": "LL-894-1", "supplier": null, "in_inventory": false, "evidence": null, "product_url": null}, {"kp_position": 9, "sku": "FR2066WL-L40B", "supplier": "freya-light.com", "in_inventory": true, "evidence": "inventory_sku", "product_url": "https://freya-light.com/products/nastennye-svetilniki/fr2066wl_l40b/"}, {"kp_position": 10, "sku": "5610/37WL", "supplier": "odeon-light.com", "in_inventory": false, "evidence": null, "product_url": null}, {"kp_position": 11, "sku": "1108", "supplier": "eurosvet.ru", "in_inventory": false, "evidence": null, "product_url": null}, {"kp_position": 12, "sku": "lsp-4001", "supplier": "shop.lussole.ru", "in_inventory": true, "evidence": "inventory_sku", "product_url": "https://shop.lussole.ru/bra-lussole-lsp-4001/"}, {"kp_position": 13, "sku": "lsp-7187", "supplier": "shop.lussole.ru", "in_inventory": true, "evidence": "inventory_sku", "product_url": "https://shop.lussole.ru/bra-lussole-lsp-7187/"}, {"kp_position": 14, "sku": "LSP-4016", "supplier": "shop.lussole.ru", "in_inventory": true, "evidence": "inventory_sku", "product_url": "https://shop.lussole.ru/podvesnoy-svetilnik-lussole-lsp-4016/"}, {"kp_position": 16, "sku": "85078/01", "supplier": "eurosvet.ru", "in_inventory": false, "evidence": null, "product_url": null}], "note": "Measured after production URL inventory build; golden data is only used here for evaluation."}`
- Hydrated: `{"visual_targets": 11, "matchable_sku_targets": 10, "present": 0, "recall": 0.0, "items": [{"kp_position": 1, "sku": "50248", "supplier": "eurosvet.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 2, "sku": null, "supplier": "kinklight.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 3, "sku": "2207B,19", "supplier": "kinklight.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 4, "sku": "LL-894-1", "supplier": null, "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 9, "sku": "FR2066WL-L40B", "supplier": "freya-light.com", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 10, "sku": "5610/37WL", "supplier": "odeon-light.com", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 11, "sku": "1108", "supplier": "eurosvet.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 12, "sku": "lsp-4001", "supplier": "shop.lussole.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 13, "sku": "lsp-7187", "supplier": "shop.lussole.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 14, "sku": "LSP-4016", "supplier": "shop.lussole.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 16, "sku": "85078/01", "supplier": "eurosvet.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}], "note": "Measured only after requirement-driven hydration; golden data never selects hydration URLs."}`
- Sellable hydrated: `{"visual_targets": 11, "matchable_sku_targets": 10, "present": 0, "recall": 0.0, "items": [{"kp_position": 1, "sku": "50248", "supplier": "eurosvet.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 2, "sku": null, "supplier": "kinklight.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 3, "sku": "2207B,19", "supplier": "kinklight.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 4, "sku": "LL-894-1", "supplier": null, "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 9, "sku": "FR2066WL-L40B", "supplier": "freya-light.com", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 10, "sku": "5610/37WL", "supplier": "odeon-light.com", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 11, "sku": "1108", "supplier": "eurosvet.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 12, "sku": "lsp-4001", "supplier": "shop.lussole.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 13, "sku": "lsp-7187", "supplier": "shop.lussole.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 14, "sku": "LSP-4016", "supplier": "shop.lussole.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}, {"kp_position": 16, "sku": "85078/01", "supplier": "eurosvet.ru", "in_hydrated_catalog": false, "sellable": false, "availability_status": null, "url": null}], "note": "Measured only after requirement-driven hydration; golden data never selects hydration URLs."}`

System BOM is excluded from decorative visual metrics.

Visual@K is intentionally null until every candidate in every current review fingerprint has an explicit accept, reject, or skipped_with_reason decision.

## Priority supplier diagnostics

| supplier | approximate total | inventory | coverage | relevant selected | hydrated | parse success | inventory golden hits | hydrated golden hits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| freya-light.com |  | 1623 |  | 80 | 40 | 1.0 | 1 | 0 |
| shop.lussole.ru |  | 1634 |  | 61 | 51 | 1.0 | 3 | 0 |
| kinklight.ru |  | 1347 |  | 142 | 40 | 0.4819277108433735 | 0 | 0 |
| eurosvet.ru |  | 1843 |  | 138 | 69 | 1.0 | 1 | 0 |
| odeon-light.com |  | 62 |  | 40 | 24 | 1.0 | 0 | 0 |
| ambrella.biz |  | 208 |  | 134 | 82 | 1.0 | 0 | 0 |
| artelamp.ru |  | 489 |  | 90 | 53 | 1.0 | 0 | 0 |
| divinare.ru |  | 348 |  | 128 | 69 | 0.971830985915493 | 0 | 0 |
| favourite-light.com |  | 1 |  | 0 | 0 |  | 0 | 0 |
| lightstar.ru |  | 2731 |  | 147 | 90 | 1.0 | 0 | 0 |
| mw-light.ru |  | 5 |  | 0 | 0 |  | 0 | 0 |
