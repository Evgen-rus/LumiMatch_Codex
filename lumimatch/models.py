"""Typed records shared by the collector, scorer and report writer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    page: int
    source_type: str
    note: str
    confidence: float = Field(ge=0, le=1)


class FixtureRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    room: str
    fixture_type: str
    quantity: int | None = Field(default=None, ge=1)
    visual_description: str
    color: str | None = None
    shape: str | None = None
    mounting: str | None = None
    approximate_dimensions: dict[str, Any] | None = None
    exact_dimensions: dict[str, Any] | None = None
    technical_constraints: list[str] = Field(default_factory=list)
    source_pages: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    reference_pages: list[str] = Field(default_factory=list)
    reference_image_paths: list[str] = Field(default_factory=list)


class CatalogProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier: str
    source_url: str
    canonical_url: str
    sku: str | None = None
    name: str
    category: str | None = None
    collection: str | None = None
    description: str | None = None
    price: float | None = None
    currency: str | None = None
    availability: str | None = None
    dimensions: str | None = None
    width: float | None = None
    height: float | None = None
    diameter: float | None = None
    depth: float | None = None
    color: str | None = None
    material: str | None = None
    mounting_type: str | None = None
    light_source: str | None = None
    wattage: float | None = None
    color_temperature: float | None = None
    ip_rating: str | None = None
    style: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    image_urls: list[str] = Field(default_factory=list)
    primary_image_url: str | None = None
    local_image_path: str | None = None
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ScoredCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    product: CatalogProduct
    visual_similarity: float | None = Field(default=None, ge=0, le=1)
    type_match: float = Field(ge=0, le=1)
    dimension_match: float = Field(ge=0, le=1)
    technical_match: float = Field(ge=0, le=1)
    overall_score: float = Field(ge=0, le=1)
    result_class: str
    fit_explanation: str
    differences: list[str] = Field(default_factory=list)
    visual_review_status: str = "не проверено Codex"
