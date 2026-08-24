"""Project-local paths; no global configuration is used."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CATALOG = DATA / "catalog"
CACHE = DATA / "cache"
IMAGES = DATA / "images"
OUTPUT = ROOT / "output"
TMP = ROOT / "tmp"


def ensure_dirs() -> None:
    for path in (DATA, CATALOG, CACHE, IMAGES, OUTPUT, TMP):
        path.mkdir(parents=True, exist_ok=True)
    (CATALOG / "images").mkdir(parents=True, exist_ok=True)
