# Visual retrieval spike corpus

Natural corpus is selected from the production URL inventory for the five configured suppliers. Golden data is not read during selection.

- Inventory URLs: 6509
- Ready product images in cumulative corpus: 2414
- Cumulative product statuses: {"ready": 2414, "image_failed": 154, "no_image": 157}
- Last run pages attempted/successful: 0/0
- Product images found: 0
- Images downloaded/reused: 0/109
- Failed: 0
- Elapsed: 6.984 sec

| supplier | cumulative ready | last run inventory URLs | last run failed |
|---|---:|---:|---:|
| eurosvet.ru | 1217 | 0 | 0 |
| freya-light.com | 421 | 0 | 0 |
| kinklight.ru | 314 | 0 | 0 |
| odeon-light.com | 0 | 0 | 0 |
| shop.lussole.ru | 462 | 0 | 0 |

Each image is stored under data/visual_spike/images/ by content hash. The isolated image_products table preserves image-to-product associations.
