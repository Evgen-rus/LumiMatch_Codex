"""Controlled same-family visual retrieval benchmark.

This module is evaluation-only.  It reads existing production/spike artifacts,
but never imports a golden identity into scoring and never writes production
catalogs, availability state, or customer reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import statistics
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from lxml import etree
from PIL import Image, ImageDraw, ImageFont

from lumimatch.paths import ROOT

from .common import sha256_file
from .encoders import load_encoder, model_metadata, write_model_failure

OUTPUT = ROOT / "output" / "controlled_visual_benchmark"
DATA = ROOT / "data" / "visual_spike" / "controlled"
CORPUS_DB = ROOT / "data" / "visual_spike" / "visual_corpus.sqlite3"
PRODUCTION_DB = ROOT / "data" / "catalog" / "production_v4.sqlite3"
GOLDEN_DOCX = ROOT / "samples" / "golden" / "dan" / "expected_kp.docx"
VISUAL_PDF = ROOT / "samples" / "Dan_vis.pdf"
MODEL_CACHE = ROOT / "data" / "visual_spike" / "model_cache"


@dataclass(frozen=True)
class TargetSpec:
    requirement_id: str
    family: str
    pool_families: tuple[str, ...]
    golden_sku: str
    positive_url_contains: str | None
    docx_row: int | None
    primary: bool
    mapping_note: str


TARGETS: dict[str, TargetSpec] = {
    "F-01": TargetSpec(
        "F-01",
        "pendant_single",
        ("pendant_single",),
        "50248",
        "50248-1-led-chernyy-a061423",
        None,
        True,
        "The black 50248/1 LED supplier variant matches the compact cylindrical pendant render.",
    ),
    "F-03": TargetSpec(
        "F-03",
        "wall_sconce",
        ("wall_sconce", "decorative_wall"),
        "FR2066WL-L40B",
        "fr2066wl_l40b",
        None,
        True,
        "Bedside sconce with a dark rectangular base and a light fabric shade.",
    ),
    "F-04": TargetSpec(
        "F-04",
        "decorative_wall",
        ("wall_sconce", "decorative_wall"),
        "LSP-7187",
        "bra-lussole-lsp-7187",
        None,
        True,
        "Vertical illuminated ribbon/loop around a dark central axis.",
    ),
    "F-06": TargetSpec(
        "F-06",
        "track_spot",
        ("track_spot", "spot"),
        "85078/01",
        None,
        16,
        False,
        "Mapping ambiguity: the KP photo is a wide disk track light, while the render shows narrow vertical cylinders.",
    ),
}


# Coordinates are normalized against the full PDF page.  They were selected
# from Dan_vis.pdf only; no catalog/golden product image is used as a query.
CROP_SPECS: dict[str, list[dict[str, Any]]] = {
    "F-01": [
        {"name": "tight", "page": 2, "box": (0.730, 0.125, 0.755, 0.215), "object_area_ratio": 0.40, "note": "one complete cylinder, little room context; source-resolution limited"},
        {"name": "medium", "page": 2, "box": (0.715, 0.112, 0.770, 0.225), "object_area_ratio": 0.15, "note": "same cylinder with modest ceiling/wall context"},
        {"name": "alternate", "page": 11, "box": (0.147, 0.076, 0.177, 0.198), "object_area_ratio": 0.41, "note": "one full cylinder from a second room angle"},
    ],
    "F-03": [
        {"name": "tight", "page": 11, "box": (0.343, 0.545, 0.382, 0.645), "object_area_ratio": 0.74, "note": "complete shade, base and reading arm; close bounding box"},
        {"name": "medium", "page": 11, "box": (0.318, 0.500, 0.405, 0.675), "object_area_ratio": 0.19, "note": "sconce with modest marble-wall context"},
        {"name": "alternate", "page": 11, "box": (0.665, 0.540, 0.704, 0.650), "object_area_ratio": 0.61, "note": "right-side second instance, tightly framed"},
    ],
    "F-04": [
        {"name": "tight", "page": 18, "box": (0.253, 0.383, 0.285, 0.530), "object_area_ratio": 0.72, "note": "complete pair of offset oval contours and dark center; close bounding box"},
        {"name": "medium", "page": 18, "box": (0.235, 0.345, 0.305, 0.560), "object_area_ratio": 0.23, "note": "left light with a small surrounding dark-wall area"},
        {"name": "alternate", "page": 18, "box": (0.615, 0.383, 0.647, 0.530), "object_area_ratio": 0.68, "note": "right-side second instance tightly framed"},
    ],
    "F-06": [
        {"name": "tight", "page": 29, "box": (0.301, 0.052, 0.327, 0.142), "object_area_ratio": 0.55, "note": "one narrow black ceiling cylinder; top limited by original page"},
        {"name": "medium", "page": 29, "box": (0.285, 0.035, 0.390, 0.170), "object_area_ratio": 0.10, "note": "one cylinder with local ceiling context"},
        {"name": "alternate", "page": 30, "box": (0.474, 0.059, 0.505, 0.132), "object_area_ratio": 0.38, "note": "single cylinder in adjacent room angle"},
    ],
}


@dataclass
class Candidate:
    candidate_id: str
    sku: str | None
    supplier: str
    url: str
    family: str
    image: str
    title: str | None = None
    image_source: str | None = None
    image_hash: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "sku": self.sku,
            "supplier": self.supplier,
            "url": self.url,
            "family": self.family,
            "image": self.image,
            "title": self.title,
            "image_source": self.image_source,
        }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def input_fingerprints() -> dict[str, str]:
    """Bind runs to manifests AND image bytes, without reading golden labels."""
    paths = [OUTPUT / "queries/manifest.json"]
    queries = json.loads(paths[0].read_text(encoding="utf-8"))
    paths.extend(Path(query["path"]) for query in queries)
    for key in TARGETS:
        path = OUTPUT / "pools" / f"{key}.json"
        paths.append(path)
        paths.extend(Path(item["image"]) for item in json.loads(path.read_text(encoding="utf-8")))
    return {str(path): sha256_file(path) for path in sorted(set(paths))}


def _normalized(value: object | None) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", " ", str(value or "").casefold()).strip()


def _candidate_id(url: str, image_hash: str) -> str:
    return hashlib.sha256(f"{url}|{image_hash}".encode()).hexdigest()[:16]


ACCESSORY_MARKERS = (
    "accessor",
    "komplekt",
    "коннектор",
    "connector",
    "шинопровод",
    "track rail",
    "zaglus",
    "заглуш",
    "крепеж",
    "adapter",
    "адаптер",
)


def classify_family(
    *, title: object | None, category: object | None, url: object | None, explicit: object | None = None
) -> str:
    """Conservative family classifier for the fixed evaluation corpus."""
    text = _normalized(" ".join(str(part or "") for part in (title, category, url)))
    # Cached production taxonomy is not authoritative: some old entries label
    # chandeliers as wall lights. Product name/URL conflicts take precedence.
    identity = _normalized(" ".join(str(part or "") for part in (title, url)))
    if any(marker in text for marker in ACCESSORY_MARKERS):
        return "accessory"
    if any(marker in identity for marker in ("lyustra", "lyustry", "люстра", "люстры", "chandelier", "profil", "профиль", "led strip")):
        return "unknown"
    if any(marker in identity for marker in ("podvesnoy svetilnik", "podvesnye svetilniki", "svetilniki podvesnyie", "подвесной светильник", "pendant light", "spoty podvesnye")):
        return "pendant_single"
    if any(marker in text for marker in ("bra ", " bra", "настенн", "wall sconce", "wall lamp", "svetilniki nastenn", "bra-")):
        return "decorative_wall" if any(marker in text for marker in ("dekor", "decor", "bradford")) else "wall_sconce"
    pendant_markers = (
        "podvesnoy svetilnik",
        "podvesnye svetilniki",
        "svetilniki podvesnyie",
        "подвесной светильник",
        "pendant light",
    )
    if any(marker in text for marker in pendant_markers) and "lyustr" not in text and "люстр" not in text:
        return "pendant_single"
    if any(marker in text for marker in ("trekovyy svetilnik", "trekovye svetilniki", "трековый светильник", "track spot", "track light")):
        # The broad track category also contains diffuse disks, globes, bars,
        # suspensions and room/system shots. Require directional evidence.
        if "spot" in identity or re.search(r"\b(?:15|24|36)\s*[°г]", str(title or "")):
            return "track_spot"
        return "unknown"
    if re.search(r"\b(?:spot|spotovyy|спот|споты|спотовый)\b", identity) or "directional ceiling" in identity:
        return "spot"
    return "unknown"


def _visual_corpus_candidates() -> list[Candidate]:
    if not CORPUS_DB.exists():
        return []
    results: list[Candidate] = []
    with sqlite3.connect(CORPUS_DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM products WHERE status = 'ready'").fetchall()
    for row in rows:
        path = Path(str(row["local_image_path"] or ""))
        if not path.is_file():
            continue
        image_hash = str(row["image_hash"] or sha256_file(path))
        family = classify_family(
            title=row["title"], category=row["category"], url=row["canonical_url"]
        )
        if family == "unknown":
            continue
        url = str(row["canonical_url"])
        results.append(
            Candidate(
                _candidate_id(url, image_hash),
                row["sku"],
                str(row["supplier"]),
                url,
                family,
                str(path.resolve()),
                row["title"],
                row["image_source"],
                image_hash,
            )
        )
    return results


def _production_candidates() -> list[Candidate]:
    if not PRODUCTION_DB.exists():
        return []
    results: list[Candidate] = []
    with sqlite3.connect(PRODUCTION_DB) as con:
        rows = con.execute("SELECT payload_json FROM products").fetchall()
    for (payload_json,) in rows:
        payload = json.loads(payload_json)
        raw_path = str(payload.get("local_image_path") or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_file():
            continue
        family = classify_family(
            title=payload.get("name"),
            category=payload.get("category"),
            url=payload.get("canonical_url") or payload.get("source_url"),
            explicit=payload.get("product_family"),
        )
        if family == "unknown":
            continue
        url = str(payload.get("canonical_url") or payload.get("source_url"))
        image_hash = sha256_file(path)
        results.append(
            Candidate(
                _candidate_id(url, image_hash),
                payload.get("sku"),
                str(payload.get("supplier") or "unknown"),
                url,
                family,
                str(path.resolve()),
                payload.get("name"),
                "existing_production_cache",
                image_hash,
            )
        )
    return results


def _extract_docx_row_image(row_index: int, target: Path) -> Path:
    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with zipfile.ZipFile(GOLDEN_DOCX) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
        relationships = etree.fromstring(
            archive.read("word/_rels/document.xml.rels")
        )
        rows = document.xpath(".//w:tbl[1]/w:tr", namespaces=namespaces)
        blips = rows[row_index].xpath(".//a:blip", namespaces=namespaces)
        if not blips:
            raise RuntimeError(f"DOCX row {row_index} has no embedded image")
        relationship_id = blips[0].get(f"{{{namespaces['r']}}}embed")
        targets = relationships.xpath(
            f".//pr:Relationship[@Id='{relationship_id}']/@Target",
            namespaces=namespaces,
        )
        if not targets:
            raise RuntimeError(f"DOCX relationship not found: {relationship_id}")
        member = "word/" + str(targets[0]).lstrip("/")
        suffix = Path(member).suffix or ".bin"
        output = target.with_suffix(suffix)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(archive.read(member))
        return output


def _render_queries() -> list[dict[str, Any]]:
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("pymupdf is required in .venv-visual") from exc
    output_dir = OUTPUT / "queries"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    document = pymupdf.open(VISUAL_PDF)
    scale = 3.0
    page_cache: dict[int, Image.Image] = {}
    for requirement_id, specs in CROP_SPECS.items():
        for spec in specs:
            page_number = int(spec["page"])
            if page_number not in page_cache:
                pixmap = document[page_number - 1].get_pixmap(
                    matrix=pymupdf.Matrix(scale, scale), alpha=False
                )
                page_cache[page_number] = Image.frombytes(
                    "RGB", (pixmap.width, pixmap.height), pixmap.samples
                )
            page = page_cache[page_number]
            left, top, right, bottom = spec["box"]
            box = (
                round(left * page.width),
                round(top * page.height),
                round(right * page.width),
                round(bottom * page.height),
            )
            crop = page.crop(box)
            path = output_dir / f"{requirement_id}_{spec['name']}.png"
            crop.save(path)
            manifest.append(
                {
                    "requirement_id": requirement_id,
                    "variant": spec["name"],
                    "source_file": "samples/Dan_vis.pdf",
                    "page": page_number,
                    "normalized_box": list(spec["box"]),
                    "pixel_size": [crop.width, crop.height],
                    "object_area_ratio": spec["object_area_ratio"],
                    "visual_note": spec["note"],
                    "path": str(path.resolve()),
                }
            )
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def _select_pool(
    target: TargetSpec, candidates: list[Candidate], *, limit: int = 300
) -> tuple[list[Candidate], Candidate]:
    family_candidates = [
        item for item in candidates if item.family in target.pool_families
    ]
    positives = [
        item
        for item in candidates
        if target.positive_url_contains
        and target.positive_url_contains.casefold() in item.url.casefold()
    ]
    if not positives and target.docx_row is not None:
        path = _extract_docx_row_image(
            target.docx_row, OUTPUT / "positives" / target.requirement_id
        )
        image_hash = sha256_file(path)
        positive = Candidate(
            _candidate_id(f"docx:{target.golden_sku}", image_hash),
            target.golden_sku,
            "eurosvet.ru",
            "samples/golden/dan/expected_kp.docx",
            target.family,
            str(path.resolve()),
            f"Golden product {target.golden_sku}",
            "expected_kp_docx_fallback",
            image_hash,
        )
        family_candidates.append(positive)
        positives = [positive]
    if not positives:
        raise RuntimeError(f"missing controlled positive for {target.requirement_id}")
    positive = sorted(positives, key=lambda item: item.url)[0]
    by_url: dict[str, Candidate] = {}
    for item in family_candidates:
        by_url.setdefault(item.url.casefold().rstrip("/"), item)
    by_url[positive.url.casefold().rstrip("/")] = positive
    distractors = [
        item for item in by_url.values() if item.candidate_id != positive.candidate_id
    ]
    distractors.sort(
        key=lambda item: hashlib.sha256(
            f"controlled-v1|{target.requirement_id}|{item.url}".encode()
        ).hexdigest()
    )
    selected = distractors[: max(0, limit - 1)] + [positive]
    selected.sort(
        key=lambda item: hashlib.sha256(
            f"fixed-pool-v1|{target.requirement_id}|{item.url}".encode()
        ).hexdigest()
    )
    return selected, positive


def prepare(limit: int = 300) -> dict[str, Any]:
    query_manifest = _render_queries()
    candidates = _visual_corpus_candidates() + _production_candidates()
    # Image-level deduplication avoids making the pool artificially easy/hard
    # through repeated cards with the same product photo.
    unique: dict[tuple[str, str], Candidate] = {}
    for item in candidates:
        unique.setdefault((item.family, str(item.image_hash)), item)
    candidates = list(unique.values())
    pool_summary: dict[str, Any] = {}
    private_targets: dict[str, Any] = {}
    for requirement_id, target in TARGETS.items():
        pool, positive = _select_pool(target, candidates, limit=limit)
        path = OUTPUT / "pools" / f"{requirement_id}.json"
        _write_json(path, [item.public_dict() for item in pool])
        pool_summary[requirement_id] = {
            "family": target.family,
            "allowed_families": list(target.pool_families),
            "size": len(pool),
            "suppliers": sorted({item.supplier for item in pool}),
            "pool_path": str(path.resolve()),
        }
        private_targets[requirement_id] = {
            "candidate_id": positive.candidate_id,
            "golden_sku": target.golden_sku,
            "source_url": positive.url,
            "image_source": positive.image_source,
            "local_path": positive.image,
            "primary": target.primary,
            "mapping_note": target.mapping_note,
        }
    _write_json(DATA / "target_provenance.json", private_targets)
    payload = {
        "version": 1,
        "pool_revision": 2,
        "mode": "controlled_same_family_evaluation_only",
        "golden_not_used_for_scoring": True,
        "candidate_source_count": len(candidates),
        "queries": query_manifest,
        "pools": pool_summary,
    }
    _write_json(OUTPUT / "prepare.json", payload)
    return payload


def _embedding_cache_path(model: str, image_hash: str) -> Path:
    # QuickGELU is required by the OpenAI CLIP checkpoint. Never reuse the
    # earlier standard-GELU baseline vectors after correcting that mismatch.
    version = "quickgelu-v2" if model == "openclip_vit_b32" else "v1"
    path = DATA / "embeddings" / model / version / f"{image_hash}.npy"
    old = DATA / "embeddings" / model / f"{image_hash}.npy"
    if model != "openclip_vit_b32" and old.exists():
        return old
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _encode_paths(encoder: Any, paths: list[Path], *, batch_size: int) -> np.ndarray:
    vectors: list[np.ndarray | None] = [None] * len(paths)
    pending_paths: list[Path] = []
    pending_indices: list[int] = []
    for index, path in enumerate(paths):
        image_hash = sha256_file(path)
        cache = _embedding_cache_path(encoder.name, image_hash)
        if cache.exists():
            try:
                vector = np.load(cache, allow_pickle=False)
                if vector.ndim != 1 or not np.isfinite(vector).all():
                    raise ValueError("Invalid cached vector")
                vectors[index] = vector
                continue
            except (ValueError, OSError, EOFError):
                pass  # Recover an interrupted/invalid cache entry locally.
        pending_paths.append(path)
        pending_indices.append(index)
    for start in range(0, len(pending_paths), max(1, batch_size)):
        batch_paths = pending_paths[start : start + max(1, batch_size)]
        encoded = encoder.encode_images(batch_paths, batch_size=len(batch_paths))
        for path, index, vector in zip(
            batch_paths,
            pending_indices[start : start + len(batch_paths)],
            encoded,
            strict=True,
        ):
            vector = np.asarray(vector, dtype="float32")
            vector /= max(float(np.linalg.norm(vector)), 1e-12)
            cache = _embedding_cache_path(encoder.name, sha256_file(path))
            temporary = cache.with_suffix(".tmp.npy")
            np.save(temporary, vector, allow_pickle=False)
            temporary.replace(cache)
            vectors[index] = vector
    return np.vstack([vector for vector in vectors if vector is not None])


def _rank(
    pool: list[dict[str, Any]], matrix: np.ndarray, query_matrix: np.ndarray, mode: str
) -> list[dict[str, Any]]:
    scores = query_matrix @ matrix.T
    if mode == "max":
        final = scores.max(axis=0)
    elif mode == "mean":
        final = scores.mean(axis=0)
    else:
        final = scores[0]
    order = np.argsort(-final, kind="stable")
    return [
        {
            "rank": rank,
            "candidate_id": pool[int(index)]["candidate_id"],
            "score": round(float(final[int(index)]), 7),
            "image": pool[int(index)]["image"],
            "supplier": pool[int(index)]["supplier"],
            "sku": pool[int(index)].get("sku"),
            "url": pool[int(index)]["url"],
        }
        for rank, index in enumerate(order, start=1)
    ]


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _write_blind_sheet(
    target: str, model: str, ranking: list[dict[str, Any]], output: Path
) -> None:
    width, height = 260, 260
    header = 60
    canvas = Image.new("RGB", (width * 5, header + height * 4), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 12), f"{target} | {model} | anonymous Top-20", fill="black", font=_font(24))
    for index, item in enumerate(ranking[:20]):
        x = (index % 5) * width
        y = header + (index // 5) * height
        try:
            with Image.open(item["image"]) as source:
                image = source.convert("RGB")
                image.thumbnail((width - 16, height - 48), Image.Resampling.LANCZOS)
                canvas.paste(image, (x + (width - image.width) // 2, y + 8))
        except OSError:
            pass
        code = str(item["candidate_id"])[:8]
        draw.text((x + 8, y + height - 34), f"#{index + 1}  {code}", fill="black", font=_font(18))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92)


def _perturb(path: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as source:
        image = source.convert("RGB")
        dx, dy = max(1, image.width // 16), max(1, image.height // 18)
        image = image.crop((dx, dy, image.width - dx // 2, image.height - dy))
        image = image.resize((max(64, image.width * 9 // 10), max(64, image.height * 9 // 10)), Image.Resampling.LANCZOS)
        image.save(target, quality=93)
    return target


def run_model(model_name: str, *, batch_size: int = 8, threads: int = 4) -> dict[str, Any]:
    if not (OUTPUT / "prepare.json").exists():
        prepare()
    started = time.monotonic()
    try:
        fingerprints = input_fingerprints()
        pool_fingerprints = {key: sha256_file(OUTPUT / "pools" / f"{key}.json") for key in TARGETS}
        encoder = load_encoder(model_name, model_cache=MODEL_CACHE, threads=threads)
        query_manifest = json.loads((OUTPUT / "queries" / "manifest.json").read_text(encoding="utf-8"))
        provenance = json.loads((DATA / "target_provenance.json").read_text(encoding="utf-8"))
        targets_payload: dict[str, Any] = {}
        for requirement_id in TARGETS:
            pool = json.loads((OUTPUT / "pools" / f"{requirement_id}.json").read_text(encoding="utf-8"))
            pool_paths = [Path(item["image"]) for item in pool]
            matrix = _encode_paths(encoder, pool_paths, batch_size=batch_size)
            queries = [
                item for item in query_manifest if item["requirement_id"] == requirement_id
            ]
            query_paths = [Path(item["path"]) for item in queries]
            query_matrix = _encode_paths(encoder, query_paths, batch_size=1)
            variants: dict[str, list[dict[str, Any]]] = {}
            for index, query in enumerate(queries):
                variants[str(query["variant"])] = _rank(
                    pool, matrix, query_matrix[index : index + 1], "single"
                )
            variants["max"] = _rank(pool, matrix, query_matrix, "max")
            variants["mean"] = _rank(pool, matrix, query_matrix, "mean")
            positive_id = provenance[requirement_id]["candidate_id"]
            positive = next(item for item in pool if item["candidate_id"] == positive_id)
            positive_path = Path(positive["image"])
            catalog_query = _encode_paths(encoder, [positive_path], batch_size=1)
            perturbed_path = _perturb(
                positive_path,
                OUTPUT / "sanity_queries" / f"{requirement_id}_perturbed.jpg",
            )
            perturbed_query = _encode_paths(encoder, [perturbed_path], batch_size=1)
            variants["catalog_self"] = _rank(pool, matrix, catalog_query, "single")
            variants["catalog_perturbed"] = _rank(pool, matrix, perturbed_query, "single")
            _write_blind_sheet(
                requirement_id,
                model_name,
                variants["max"],
                OUTPUT / "review" / model_name / f"{requirement_id}_top20.jpg",
            )
            targets_payload[requirement_id] = {
                "pool_size": len(pool),
                "query_variants": queries,
                "rankings": variants,
            }
        runtime = model_metadata(encoder, model_cache=MODEL_CACHE)
        first_ranking = next(iter(targets_payload.values()))["rankings"]["max"]
        runtime["embedding_dimension"] = int(
            np.load(
                _embedding_cache_path(
                    model_name, sha256_file(Path(first_ranking[0]["image"]))
                ),
                allow_pickle=False,
            ).shape[0]
        )
        runtime["total_seconds"] = round(time.monotonic() - started, 3)
        try:
            import psutil

            runtime["rss_mb_at_end"] = round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1)
        except (ImportError, OSError):
            runtime["rss_mb_at_end"] = None
        payload = {"status": "ready", "model": model_name, "runtime": runtime, "targets": targets_payload,
                   "pool_fingerprints": pool_fingerprints, "input_fingerprints": fingerprints}
        _write_json(OUTPUT / "sealed" / f"{model_name}.json", payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        path = OUTPUT / "failures" / f"{model_name}.json"
        write_model_failure(path, model_name, exc)
        return {"status": "failed", "model": model_name, "error": f"{type(exc).__name__}: {exc}"}


def _target_rank(ranking: list[dict[str, Any]], candidate_id: str) -> int | None:
    for item in ranking:
        if item["candidate_id"] == candidate_id:
            return int(item["rank"])
    return None


def _recall(ranks: list[int | None], k: int) -> float:
    return round(sum(rank is not None and rank <= k for rank in ranks) / len(ranks), 4) if ranks else 0.0


def seal_review() -> None:
    """Bind already human-written ratings to the exact viewed sheet files."""
    path = OUTPUT / "manual_review.json"
    manual = json.loads(path.read_text(encoding="utf-8"))
    hashes = {}
    for model, targets in manual.items():
        if model.startswith("_"):
            continue
        hashes[model] = {}
        for target, ratings in targets.items():
            count = min(20, len(json.loads((OUTPUT / "pools" / f"{target}.json").read_text(encoding="utf-8"))))
            strong, plausible = ratings['strong_ranks'], ratings['plausible_ranks']
            if len(strong) != ratings['strong'] or len(plausible) != ratings['plausible']:
                raise ValueError(f"Review count/list mismatch: {model} {target}")
            if len(set(strong + plausible)) != len(strong + plausible) or any(r < 1 or r > count for r in strong + plausible):
                raise ValueError(f"Invalid or overlapping review ranks: {model} {target}")
            if sum(ratings[k] for k in ('strong', 'plausible', 'poor')) != count:
                raise ValueError(f"Review total mismatch: {model} {target}")
            hashes[model][target] = sha256_file(OUTPUT / "review" / model / f"{target}_top20.jpg")
    manual['_sheet_hashes'] = hashes
    _write_json(path, manual)


def reveal() -> dict[str, Any]:
    provenance = json.loads((DATA / "target_provenance.json").read_text(encoding="utf-8"))
    manual_path = OUTPUT / "manual_review.json"
    manual = json.loads(manual_path.read_text(encoding="utf-8")) if manual_path.exists() else {}
    models: dict[str, Any] = {}
    table: list[dict[str, Any]] = []
    fingerprints = input_fingerprints()
    for path in sorted((OUTPUT / "sealed").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "ready":
            continue
        expected = {key: sha256_file(OUTPUT / "pools" / f"{key}.json") for key in TARGETS}
        if payload.get("pool_fingerprints") != expected:
            raise RuntimeError(f"Stale model result with different pools: {path.name}")
        if payload.get("input_fingerprints") != fingerprints:
            raise RuntimeError(f"Stale input images or manifests: {path.name}")
        if payload.get("source_model"):
            source_path = OUTPUT / "sealed" / f"{payload['source_model']}.json"
            if payload.get("source_fingerprint") != sha256_file(source_path):
                raise RuntimeError(f"Stale reranker source: {path.name}")
        if not payload.get("source_model"):
            current_queries = json.loads((OUTPUT / "queries/manifest.json").read_text(encoding="utf-8"))
            for key, value in payload["targets"].items():
                if value.get("query_variants") != [q for q in current_queries if q['requirement_id'] == key]:
                    raise RuntimeError(f"Stale query manifest in {path.name}: {key}")
        model_name = str(payload["model"])
        if any(key not in manual.get(model_name, {}) for key in payload["targets"]):
            raise RuntimeError(f"Complete anonymous manual review before reveal: {model_name}")
        for key in payload['targets']:
            if manual.get('_sheet_hashes', {}).get(model_name, {}).get(key) != sha256_file(OUTPUT / 'review' / model_name / f'{key}_top20.jpg'):
                raise RuntimeError(f"Review does not match current sheet: {model_name} {key}")
        ranks: list[int | None] = []
        target_rows: dict[str, Any] = {}
        for requirement_id, target_payload in payload["targets"].items():
            positive_id = provenance[requirement_id]["candidate_id"]
            variant_ranks = {
                name: _target_rank(ranking, positive_id)
                for name, ranking in target_payload["rankings"].items()
            }
            if provenance[requirement_id]["primary"]:
                ranks.append(variant_ranks["max"])
            qualitative = manual.get(model_name, {}).get(requirement_id, {})
            target_rows[requirement_id] = {
                "pool_size": target_payload["pool_size"],
                "golden_sku": provenance[requirement_id]["golden_sku"],
                "primary": provenance[requirement_id]["primary"],
                "mapping_note": provenance[requirement_id]["mapping_note"],
                "ranks": variant_ranks,
                "manual_top20": qualitative,
            }
            for variant in (name for name in ("tight", "medium", "alternate", "max", "mean") if name in variant_ranks):
                rank = variant_ranks.get(variant)
                table.append(
                    {
                        "target": requirement_id,
                        "model": model_name,
                        "crop_variant": variant,
                        "golden_rank": rank,
                        "r_at_10": int(rank is not None and rank <= 10),
                        "r_at_20": int(rank is not None and rank <= 20),
                        "r_at_50": int(rank is not None and rank <= 50),
                        "useful_top20": int(qualitative.get("strong", 0)) + int(qualitative.get("plausible", 0)) if variant == "max" else None,
                        "recall_at_1": int(rank is not None and rank <= 1),
                        "recall_at_5": int(rank is not None and rank <= 5),
                        "recall_at_100": int(rank is not None and rank <= 100),
                        "reciprocal_rank": 1 / rank if rank else 0,
                    }
                )
        models[model_name] = {
            "runtime": payload["runtime"],
            "primary_metrics_max": {
                "targets": len(ranks),
                "recall_at_1": _recall(ranks, 1),
                "recall_at_5": _recall(ranks, 5),
                "recall_at_10": _recall(ranks, 10),
                "recall_at_20": _recall(ranks, 20),
                "recall_at_50": _recall(ranks, 50),
                "recall_at_100": _recall(ranks, 100),
                "mrr": round(sum(1 / rank if rank else 0 for rank in ranks) / len(ranks), 4) if ranks else 0.0,
                "median_rank_of_retrieved": statistics.median([rank for rank in ranks if rank]) if any(ranks) else None,
                "ranks": ranks,
            },
            "targets": target_rows,
        }
        models[model_name]["primary_metrics_by_variant"] = {}
        for variant in ("tight", "medium", "alternate", "max", "mean"):
            variant_values = [row["ranks"][variant] for row in target_rows.values() if row["primary"] and variant in row["ranks"]]
            if variant_values:
                models[model_name]["primary_metrics_by_variant"][variant] = {
                    **{f"recall_at_{k}": _recall(variant_values, k) for k in (1, 5, 10, 20, 50, 100)},
                    "mrr": sum(1 / rank if rank else 0 for rank in variant_values) / len(variant_values),
                    "ranks": variant_values,
                }
        if payload.get("source_model"):
            models[model_name]["source_model"] = payload["source_model"]
    failures = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((OUTPUT / "failures").glob("*.json"))]
    failures = [item for item in failures if item.get("model") not in models]
    secondary = {}
    for path in sorted((OUTPUT / "secondary").glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        secondary[item["model"]] = {
            target: {
                "neutral_background_rank": _target_rank(value["neutral_background"], provenance[target]["candidate_id"]),
                "gallery_max_rank": _target_rank(value["gallery_max"], provenance[target]["candidate_id"]),
                "gallery_images": value["gallery_images"],
            } for target, value in item["targets"].items()
        }
    rerank_comparison = []
    for model, item in models.items():
        source = item.get("source_model")
        if source:
            for target, value in item["targets"].items():
                before = models[source]["targets"][target]["ranks"]["max"]
                rerank_comparison.append({"target": target, "source_model": source, "before": before,
                                          "after": value["ranks"]["max"], "positive_in_top50": before is not None and before <= 50})
    payload = {
        "benchmark": "controlled_same_family_visual_retrieval",
        "primary_targets": [key for key, value in provenance.items() if value["primary"]],
        "diagnostic_targets": [key for key, value in provenance.items() if not value["primary"]],
        "models": models,
        "failures": failures,
        "table": table,
        "performance": {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in (OUTPUT / "performance").glob("*.json")},
        "positive_provenance": provenance,
        "manual_protocol": manual.get("_protocol", {}),
        "secondary": secondary,
        "dreamsim_comparison": rerank_comparison,
    }
    _write_json(OUTPUT / "benchmark.json", payload)
    write_report(payload)
    return payload


def write_report(payload: dict[str, Any]) -> None:
    prepare_payload = json.loads((OUTPUT / "prepare.json").read_text(encoding="utf-8"))
    lines = [
        "# Controlled visual benchmark",
        "",
        "Evaluation-only benchmark: every golden positive is present in a fixed same-family pool; golden identity is not used in embeddings, distractor selection, scoring, or reranking.",
        "",
        "## Pools",
        "",
        "| target | family | products | primary |",
        "|---|---|---:|---|",
    ]
    provenance = json.loads((DATA / "target_provenance.json").read_text(encoding="utf-8"))
    for target, pool in prepare_payload["pools"].items():
        lines.append(f"| {target} | {pool['family']} | {pool['size']} | {'yes' if provenance[target]['primary'] else 'no'} |")
    lines.extend([
        "",
        "F-06 is diagnostic rather than PRIMARY: its KP image is a wide disk track light, while the project render shows narrow cylinders.",
        "",
        "## Main results",
        "",
        "| target | model | crop variant | golden rank | R@10 | R@20 | R@50 | useful Top20 |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ])
    for row in payload["table"]:
        lines.append(
            f"| {row['target']} | {row['model']} | {row['crop_variant']} | {row['golden_rank'] or '—'} | {row['r_at_10']} | {row['r_at_20']} | {row['r_at_50']} | {row['useful_top20'] if row['useful_top20'] is not None else 'not reviewed'} |"
        )
    lines.extend(["", "## Catalog-to-catalog vs render-to-catalog", "", "| target | model | catalog self | perturbed catalog | render MAX |", "|---|---|---:|---:|---:|"])
    for model, result in payload["models"].items():
        for target, target_result in result["targets"].items():
            ranks = target_result["ranks"]
            lines.append(f"| {target} | {model} | {ranks.get('catalog_self') or '—'} | {ranks.get('catalog_perturbed') or '—'} | {ranks.get('max') or '—'} |")
    lines.extend(["", "## Manual visual usefulness (MAX, before identity reveal)", "", "| model | target | strong | plausible | poor | useful |", "|---|---|---:|---:|---:|---:|"])
    for model, result in payload["models"].items():
        for target, value in result["targets"].items():
            review = value['manual_top20']
            lines.append(f"| {model} | {target} | {review['strong']} | {review['plausible']} | {review['poor']} | {review['strong'] + review['plausible']} |")
    lines.extend(["", "## Model summary", "", "Quality uses MAX across render crops. Comparable inference cost is in the warmed CPU table; run elapsed time includes cache effects and, for DreamSim, cumulative downloads/earlier sources.", ""])
    for model, result in payload["models"].items():
        metric = result["primary_metrics_max"]
        runtime = result["runtime"]
        lines.append(f"- **{model}**: PRIMARY R@20={metric['recall_at_20']}, R@50={metric['recall_at_50']}, MRR={metric['mrr']}; embedding dim {runtime.get('embedding_dimension')}.")
    for failure in payload.get("failures", []):
        lines.append(f"- **{failure.get('model')} failed**: {failure.get('error')}")
    lines.extend(["", "## PRIMARY aggregation (3 targets)", "", "| model | variant | R@1 | R@5 | R@10 | R@20 | R@50 | R@100 | MRR |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"])
    for model, result in payload['models'].items():
        for variant, metric in result['primary_metrics_by_variant'].items():
            values = ' | '.join(str(metric[f'recall_at_{k}']) for k in (1,5,10,20,50,100))
            lines.append(f"| {model} | {variant} | {values} | {metric['mrr']:.4f} |")
    lines.extend(["", "## DreamSim rerank (MAX)", "", "| target | source | before | after | positive in Top50 |", "|---|---|---:|---:|---|"])
    for row in payload['dreamsim_comparison']:
        lines.append(f"| {row['target']} | {row['source_model']} | {row['before']} | {row['after'] or 'outside source Top50'} | {row['positive_in_top50']} |")
    lines.extend(["", "## Secondary diagnostics (not PRIMARY)", "", "| target | model | original tight | neutral background | baseline MAX | gallery MAX | gallery images |", "|---|---|---:|---:|---:|---:|---:|"])
    for model, rows in payload['secondary'].items():
        for target, row in rows.items():
            ranks = payload['models'][model]['targets'][target]['ranks']
            lines.append(f"| {target} | {model} | {ranks['tight']} | {row['neutral_background_rank']} | {ranks['max']} | {row['gallery_max_rank']} | {row['gallery_images']} |")
    lines.extend(["", "## Warmed CPU performance", "", "| model | load s | sec/image | median query s | RSS MiB | dimension | embedding cache MiB |", "|---|---:|---:|---:|---:|---:|---:|"])
    for model, row in payload['performance'].items():
        lines.append(f"| {model} | {row['load_seconds']:.2f} | {row['sec_per_image']:.3f} | {row['query_latency_seconds_median']:.3f} | {row['rss_mb']:.1f} | {row['embedding_dimension']} | {row['embedding_cache_mb']:.2f} |")
    lines.extend([
        "",
        "## Query crops",
        "",
    ])
    for query in prepare_payload["queries"]:
        lines.append(f"- {query['requirement_id']} {query['variant']}: page {query['page']}, object_area_ratio≈{query['object_area_ratio']}; {query['visual_note']}.")
    text = "\n".join(lines) + "\n"
    protocol = OUTPUT / "protocol.md"
    if protocol.exists():
        text += "\n" + protocol.read_text(encoding="utf-8")
    interpretation = OUTPUT / "interpretation.md"
    if interpretation.exists():
        text = interpretation.read_text(encoding="utf-8") + "\n\n" + text
    (OUTPUT / "benchmark.md").write_text(text, encoding="utf-8")
    (ROOT / "docs" / "CONTROLLED_VISUAL_BENCHMARK.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--limit", type=int, default=300)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--model", required=True)
    run_parser.add_argument("--batch-size", type=int, default=8)
    run_parser.add_argument("--threads", type=int, default=4)
    sub.add_parser("reveal")
    sub.add_parser("seal-review")
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(args.limit), ensure_ascii=False))
    elif args.command == "run":
        result = run_model(args.model, batch_size=args.batch_size, threads=args.threads)
        print(json.dumps({key: value for key, value in result.items() if key not in {"targets", "input_fingerprints"}}, ensure_ascii=False))
        return 0 if result.get("status") == "ready" else 2
    elif args.command == 'seal-review':
        seal_review()
        print('Review counts checked and sheet hashes saved')
    else:
        result = reveal()
        print(json.dumps({"models": list(result["models"]), "failures": len(result["failures"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
