"""Secondary background/gallery diagnostics, separate from fixed baseline."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sqlite3
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageDraw

from .controlled import OUTPUT, DATA, CORPUS_DB, MODEL_CACHE, TARGETS, _encode_paths, _rank, _write_json, _write_blind_sheet
from .encoders import load_encoder


# Manually bounded foreground from render crops, not from catalog labels.
RECTANGLES = {
    "F-01": [(0.20, 0.02, 0.76, 1.0)],
    "F-03": [(0.04, 0.01, 0.90, 0.34), (0.35, 0.30, 0.72, 0.68), (0.27, 0.62, 0.60, 0.94)],
    "F-04": [(0.07, 0.03, 0.92, 0.99)],
    "F-06": [(0.12, 0.01, 0.90, 0.99)],
}


def backgrounds() -> None:
    for target, boxes in RECTANGLES.items():
        source = Image.open(OUTPUT / "queries" / f"{target}_tight.png").convert("RGB")
        mask = Image.new("L", source.size, 0)
        draw = ImageDraw.Draw(mask)
        for x1, y1, x2, y2 in boxes:
            draw.rectangle((int(x1 * source.width), int(y1 * source.height), int(x2 * source.width), int(y2 * source.height)), fill=255)
        image = Image.composite(source, Image.new("RGB", source.size, (235, 235, 235)), mask)
        path = OUTPUT / "background" / f"{target}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)


def galleries(sources: list[str]) -> dict:
    """Exploratory gallery coverage for Top20 plus annotated positive.

    This label-assisted coverage diagnostic is explicitly NOT a fair baseline:
    all gallery selection/provenance is saved and never changes fixed pools.
    """
    positive = json.loads((DATA / "target_provenance.json").read_text(encoding="utf-8"))
    with sqlite3.connect(CORPUS_DB) as db:
        lookup = {url.rstrip('/'): json.loads(gallery) for url, gallery in db.execute('SELECT canonical_url, gallery_urls_json FROM products')}
    output = {}
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        for target in TARGETS:
            pool = json.loads((OUTPUT / "pools" / f"{target}.json").read_text(encoding="utf-8"))
            selected = {positive[target]["candidate_id"]}
            for model in sources:
                result = json.loads((OUTPUT / "sealed" / f"{model}.json").read_text(encoding="utf-8"))
                selected.update(row["candidate_id"] for row in result["targets"][target]["rankings"]["max"][:20])
            entries = {}
            for item in pool:
                if item["candidate_id"] not in selected:
                    continue
                images = []
                errors = []
                for url in lookup.get(item["url"].rstrip('/'), [])[:3]:
                    path = OUTPUT / "gallery" / "images" / (hashlib.sha256(url.encode()).hexdigest() + '.jpg')
                    try:
                        if not path.exists():
                            response = client.get(url)
                            response.raise_for_status()
                            with Image.open(io.BytesIO(response.content)) as image:
                                image = image.convert("RGB")
                                image.thumbnail((1200, 1200))
                                path.parent.mkdir(parents=True, exist_ok=True)
                                image.save(path, quality=93)
                            time.sleep(0.1)
                        images.append({"url": url, "path": str(path)})
                    except Exception as exc:
                        errors.append({"url": url, "error": str(exc)})
                entries[item["candidate_id"]] = {"images": images, "errors": errors}
            output[target] = entries
            _write_json(OUTPUT / "gallery" / "manifest.json", output)
            print(f"Gallery {target}: {sum(len(x['images']) for x in entries.values())} photos", flush=True)
    return {target: len(entries) for target, entries in output.items()}


def score(model: str) -> dict:
    encoder = load_encoder(model, model_cache=MODEL_CACHE, threads=4)
    baseline = json.loads((OUTPUT / "sealed" / f"{model}.json").read_text(encoding="utf-8"))
    gallery_path = OUTPUT / "gallery/manifest.json"
    gallery = json.loads(gallery_path.read_text(encoding="utf-8")) if gallery_path.exists() else {}
    targets = {}
    for target in TARGETS:
        pool = json.loads((OUTPUT / "pools" / f"{target}.json").read_text(encoding="utf-8"))
        matrix = _encode_paths(encoder, [Path(x['image']) for x in pool], batch_size=4)
        neutral = _encode_paths(encoder, [OUTPUT / "background" / f"{target}.png"], batch_size=1)
        neutral_ranking = _rank(pool, matrix, neutral, "single")
        queries = _encode_paths(encoder, [OUTPUT / "queries" / f"{target}_{variant}.png" for variant in ("tight", "medium", "alternate")], batch_size=1)
        scores = (queries @ matrix.T).max(axis=0)
        gallery_images = 0
        for index, item in enumerate(pool):
            paths = [Path(x['path']) for x in gallery.get(target, {}).get(item['candidate_id'], {}).get('images', [])]
            if paths:
                gallery_matrix = _encode_paths(encoder, paths, batch_size=3)
                scores[index] = max(scores[index], (queries @ gallery_matrix.T).max())
                gallery_images += len(paths)
        order = np.argsort(-scores, kind='stable')
        gallery_ranking = [{"candidate_id": pool[int(i)]["candidate_id"], "rank": rank, "score": float(scores[i])} for rank, i in enumerate(order, 1)]
        targets[target] = {"neutral_background": neutral_ranking, "gallery_max": gallery_ranking, "gallery_images": gallery_images}
    payload = {"model": model, "targets": targets, "caution": "Gallery is label-assisted coverage diagnostic; not PRIMARY. Background is coarse hand-bounded masking, not segmentation."}
    _write_json(OUTPUT / "secondary" / f"{model}.json", payload)
    return {"model": model, "status": "ready"}


def gallery_qa() -> None:
    provenance = json.loads((DATA / "target_provenance.json").read_text(encoding="utf-8"))
    gallery = json.loads((OUTPUT / "gallery/manifest.json").read_text(encoding="utf-8"))
    baseline = json.loads((OUTPUT / "sealed/siglip2_base_patch16_224.json").read_text(encoding="utf-8"))
    for target in TARGETS:
        selected = [x['candidate_id'] for x in baseline['targets'][target]['rankings']['max'][:3]]
        if provenance[target]['candidate_id'] not in selected:
            selected.append(provenance[target]['candidate_id'])
        pool = json.loads((OUTPUT / 'pools' / f'{target}.json').read_text(encoding='utf-8'))
        rows = []
        for candidate_id in selected:
            item = next(x for x in pool if x['candidate_id'] == candidate_id)
            rows.append({'candidate_id': candidate_id + '-primary', 'image': item['image']})
            rows.extend({'candidate_id': candidate_id, 'image': x['path']} for x in gallery[target].get(candidate_id, {}).get('images', []))
        _write_blind_sheet(target, 'gallery QA: primary then up to 3 gallery', rows, OUTPUT / 'gallery' / f'{target}_qa.jpg')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["backgrounds", "galleries", "score", "qa"])
    parser.add_argument("--model", default="siglip2_base_patch16_224")
    parser.add_argument("--sources", nargs='+', default=["dinov2_vits14", "siglip2_base_patch16_224"])
    args = parser.parse_args()
    result = backgrounds() if args.command == "backgrounds" else galleries(args.sources) if args.command == "galleries" else gallery_qa() if args.command == 'qa' else score(args.model)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
