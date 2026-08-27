# Visual retrieval spike benchmark

This report evaluates image-to-image retrieval only. Golden mappings are consulted after ranking; SYSTEM_BOM, unmapped rows and low-confidence rows are excluded from PRIMARY metrics.

## Model comparison

| model | variant | scope | primary R@10 | R@20 | R@50 | R@100 | MRR | build sec | benchmark sec |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| dinov2_vits14 | primary | natural | 0.0 | 0.0 | 0.0 | 0.0 | 0.0014 | 115.347 | 0.32 |
| openclip_vit_b32 | primary | natural | 0.0 | 0.0 | 0.0 | 0.0 | 0.0013 | 74.765 | 1.785 |
| dinov2_vits14 | primary | oracle | 0.0 | 0.0 | 0.0 | 0.0 | 0.002 | 11.157 | 0.248 |
| openclip_vit_b32 | primary | oracle | 0.0 | 0.0 | 0.0 | 0.0 | 0.0015 | 13.955 | 3.423 |
| mobileclip2_s0 | - | - | failed | failed | failed | failed | failed | - | - |
| mobileclip2_s2 | - | - | failed | failed | failed | failed | failed | - | - |

## Natural corpus recall

| model | scope | primary present/total | exploratory present/total | image rows | dimensions |
|---|---|---:|---:|---:|---:|
| dinov2_vits14 | natural | 1/4 | 2/6 | 2414 | 384 |
| openclip_vit_b32 | natural | 1/4 | 2/6 | 2414 | 512 |
| dinov2_vits14 | oracle | 1/4 | 2/6 | 2416 | 384 |
| openclip_vit_b32 | oracle | 1/4 | 2/6 | 2416 | 512 |

## Individual golden ranks

| benchmark | F | golden SKU | supplier | confidence | variant | rank |
|---|---|---|---|---:|---|---:|
| primary | F-01 | 50248 | eurosvet.ru | 0.88 | image_only |  |
| primary | F-03 | FR2066WL-L40B | freya-light.com | 0.72 | image_only |  |
| primary | F-04 | lsp-7187 | shop.lussole.ru | 0.67 | image_only | 182 |
| primary | F-06 | 85078/01 | eurosvet.ru | 0.79 | image_only |  |
| exploratory | F-03 | 2207B,19 | kinklight.ru | 0.49 | image_only |  |
| exploratory | F-02 | LL-894-1 |  | 0.56 | image_only |  |
| exploratory | F-04 | 5610/37WL | odeon-light.com | 0.58 | image_only |  |
| exploratory | F-05 | 1108 | eurosvet.ru | 0.44 | image_only |  |
| exploratory | F-05 | lsp-4001 | shop.lussole.ru | 0.54 | image_only | 474 |
| exploratory | F-01 | LSP-4016 | shop.lussole.ru | 0.42 | image_only | 1645 |
| primary | F-01 | 50248 | eurosvet.ru | 0.88 | image_only |  |
| primary | F-03 | FR2066WL-L40B | freya-light.com | 0.72 | image_only |  |
| primary | F-04 | lsp-7187 | shop.lussole.ru | 0.67 | image_only | 191 |
| primary | F-06 | 85078/01 | eurosvet.ru | 0.79 | image_only |  |
| exploratory | F-03 | 2207B,19 | kinklight.ru | 0.49 | image_only |  |
| exploratory | F-02 | LL-894-1 |  | 0.56 | image_only |  |
| exploratory | F-04 | 5610/37WL | odeon-light.com | 0.58 | image_only |  |
| exploratory | F-05 | 1108 | eurosvet.ru | 0.44 | image_only |  |
| exploratory | F-05 | lsp-4001 | shop.lussole.ru | 0.54 | image_only | 673 |
| exploratory | F-01 | LSP-4016 | shop.lussole.ru | 0.42 | image_only | 122 |
| primary | F-01 | 50248 | eurosvet.ru | 0.88 | visual_first_0.85 |  |
| primary | F-03 | FR2066WL-L40B | freya-light.com | 0.72 | visual_first_0.85 |  |
| primary | F-04 | lsp-7187 | shop.lussole.ru | 0.67 | visual_first_0.85 | 195 |
| primary | F-06 | 85078/01 | eurosvet.ru | 0.79 | visual_first_0.85 |  |
| exploratory | F-03 | 2207B,19 | kinklight.ru | 0.49 | visual_first_0.85 |  |
| exploratory | F-02 | LL-894-1 |  | 0.56 | visual_first_0.85 |  |
| exploratory | F-04 | 5610/37WL | odeon-light.com | 0.58 | visual_first_0.85 |  |
| exploratory | F-05 | 1108 | eurosvet.ru | 0.44 | visual_first_0.85 |  |
| exploratory | F-05 | lsp-4001 | shop.lussole.ru | 0.54 | visual_first_0.85 | 785 |
| exploratory | F-01 | LSP-4016 | shop.lussole.ru | 0.42 | visual_first_0.85 | 142 |
| primary | F-01 | 50248 | eurosvet.ru | 0.88 | mixed_0.70 |  |
| primary | F-03 | FR2066WL-L40B | freya-light.com | 0.72 | mixed_0.70 |  |
| primary | F-04 | lsp-7187 | shop.lussole.ru | 0.67 | mixed_0.70 | 209 |
| primary | F-06 | 85078/01 | eurosvet.ru | 0.79 | mixed_0.70 |  |
| exploratory | F-03 | 2207B,19 | kinklight.ru | 0.49 | mixed_0.70 |  |
| exploratory | F-02 | LL-894-1 |  | 0.56 | mixed_0.70 |  |
| exploratory | F-04 | 5610/37WL | odeon-light.com | 0.58 | mixed_0.70 |  |
| exploratory | F-05 | 1108 | eurosvet.ru | 0.44 | mixed_0.70 |  |
| exploratory | F-05 | lsp-4001 | shop.lussole.ru | 0.54 | mixed_0.70 | 919 |
| exploratory | F-01 | LSP-4016 | shop.lussole.ru | 0.42 | mixed_0.70 | 172 |
| primary | F-01 | 50248 | eurosvet.ru | 0.88 | image_only |  |
| primary | F-03 | FR2066WL-L40B | freya-light.com | 0.72 | image_only | 403 |
| primary | F-04 | lsp-7187 | shop.lussole.ru | 0.67 | image_only | 183 |
| primary | F-06 | 85078/01 | eurosvet.ru | 0.79 | image_only |  |
| exploratory | F-03 | 2207B,19 | kinklight.ru | 0.49 | image_only |  |
| exploratory | F-02 | LL-894-1 |  | 0.56 | image_only |  |
| exploratory | F-04 | 5610/37WL | odeon-light.com | 0.58 | image_only |  |
| exploratory | F-05 | 1108 | eurosvet.ru | 0.44 | image_only |  |
| exploratory | F-05 | lsp-4001 | shop.lussole.ru | 0.54 | image_only | 475 |
| exploratory | F-01 | LSP-4016 | shop.lussole.ru | 0.42 | image_only | 1646 |
| primary | F-01 | 50248 | eurosvet.ru | 0.88 | image_only |  |
| primary | F-03 | FR2066WL-L40B | freya-light.com | 0.72 | image_only | 1287 |
| primary | F-04 | lsp-7187 | shop.lussole.ru | 0.67 | image_only | 191 |
| primary | F-06 | 85078/01 | eurosvet.ru | 0.79 | image_only |  |
| exploratory | F-03 | 2207B,19 | kinklight.ru | 0.49 | image_only |  |
| exploratory | F-02 | LL-894-1 |  | 0.56 | image_only |  |
| exploratory | F-04 | 5610/37WL | odeon-light.com | 0.58 | image_only |  |
| exploratory | F-05 | 1108 | eurosvet.ru | 0.44 | image_only |  |
| exploratory | F-05 | lsp-4001 | shop.lussole.ru | 0.54 | image_only | 674 |
| exploratory | F-01 | LSP-4016 | shop.lussole.ru | 0.42 | image_only | 122 |
| primary | F-01 | 50248 | eurosvet.ru | 0.88 | visual_first_0.85 |  |
| primary | F-03 | FR2066WL-L40B | freya-light.com | 0.72 | visual_first_0.85 | 1317 |
| primary | F-04 | lsp-7187 | shop.lussole.ru | 0.67 | visual_first_0.85 | 195 |
| primary | F-06 | 85078/01 | eurosvet.ru | 0.79 | visual_first_0.85 |  |
| exploratory | F-03 | 2207B,19 | kinklight.ru | 0.49 | visual_first_0.85 |  |
| exploratory | F-02 | LL-894-1 |  | 0.56 | visual_first_0.85 |  |
| exploratory | F-04 | 5610/37WL | odeon-light.com | 0.58 | visual_first_0.85 |  |
| exploratory | F-05 | 1108 | eurosvet.ru | 0.44 | visual_first_0.85 |  |
| exploratory | F-05 | lsp-4001 | shop.lussole.ru | 0.54 | visual_first_0.85 | 786 |
| exploratory | F-01 | LSP-4016 | shop.lussole.ru | 0.42 | visual_first_0.85 | 142 |
| primary | F-01 | 50248 | eurosvet.ru | 0.88 | mixed_0.70 |  |
| primary | F-03 | FR2066WL-L40B | freya-light.com | 0.72 | mixed_0.70 | 1359 |
| primary | F-04 | lsp-7187 | shop.lussole.ru | 0.67 | mixed_0.70 | 209 |
| primary | F-06 | 85078/01 | eurosvet.ru | 0.79 | mixed_0.70 |  |
| exploratory | F-03 | 2207B,19 | kinklight.ru | 0.49 | mixed_0.70 |  |
| exploratory | F-02 | LL-894-1 |  | 0.56 | mixed_0.70 |  |
| exploratory | F-04 | 5610/37WL | odeon-light.com | 0.58 | mixed_0.70 |  |
| exploratory | F-05 | 1108 | eurosvet.ru | 0.44 | mixed_0.70 |  |
| exploratory | F-05 | lsp-4001 | shop.lussole.ru | 0.54 | mixed_0.70 | 920 |
| exploratory | F-01 | LSP-4016 | shop.lussole.ru | 0.42 | mixed_0.70 | 172 |

## Qualitative review

Top-20 sheets are under output/visual_spike/review/<model>/<variant>/. Golden SKU rank is not treated as a visual positive.
Manual Codex review: no_strong_visual_finalists

## Integrity

- Natural corpus selection reads only the selected production inventory and never reads golden data.
- Query paths come from FixtureRequirement.reference_crop_paths; expected_kp.docx and golden assets are rejected.
- Oracle-enriched rows live in the separate oracle scope and are never added to natural.
- A model failure is recorded as a failed run and does not cancel other model runs.
