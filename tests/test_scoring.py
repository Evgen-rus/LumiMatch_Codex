from lumimatch.models import CatalogProduct, FixtureRequirement
from lumimatch.scoring import shortlist


def test_black_pendant_beats_white_wall_lamp() -> None:
    requirement = FixtureRequirement(
        id="F-1",
        room="гостиная",
        fixture_type="подвесной светильник",
        visual_description="чёрный цилиндрический подвес",
        color="чёрный",
        shape="цилиндрический",
        mounting="подвесной",
        confidence=0.8,
    )
    pendant = CatalogProduct(
        supplier="a.test",
        source_url="https://a.test/p/1",
        canonical_url="https://a.test/p/1",
        sku="A-1",
        name="Подвесной светильник Cylinder",
        color="чёрный",
        mounting_type="подвесной",
        attributes={"форма": "цилиндр"},
    )
    wall = CatalogProduct(
        supplier="b.test",
        source_url="https://b.test/p/2",
        canonical_url="https://b.test/p/2",
        sku="B-2",
        name="Настенное бра Oval",
        color="белый",
        mounting_type="настенный",
    )
    result = shortlist(requirement, [wall, pendant], limit=2)
    assert result[0].product.supplier == "a.test"
    assert result[0].overall_score > result[1].overall_score
