from lumimatch.discovery import get_supplier_adapter, product_url_score, xml_locations


def test_xml_locations_supports_namespace() -> None:
    xml = b"<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'><url><loc>https://example.test/store/a/</loc></url></urlset>"
    assert xml_locations(xml) == ["https://example.test/store/a/"]


def test_product_url_is_prioritized() -> None:
    assert product_url_score(
        "https://example.test/store/cl164321/"
    ) > product_url_score("https://example.test/about/")


def test_priority_supplier_adapters_are_generic_url_selectors() -> None:
    assert get_supplier_adapter("https://freya-light.com").adapter_name == "freya_products"
    assert get_supplier_adapter("https://shop.lussole.ru").product_filter(  # type: ignore[attr-defined]
        "https://shop.lussole.ru/podves-lussole-lsp-4001/", "https://shop.lussole.ru"
    )
    assert not get_supplier_adapter("https://shop.lussole.ru").product_filter(  # type: ignore[attr-defined]
        "https://shop.lussole.ru/news/lsp-4001/", "https://shop.lussole.ru"
    )
    assert get_supplier_adapter("https://kinklight.ru").product_filter(  # type: ignore[attr-defined]
        "https://kinklight.ru/bra/17352.html", "https://kinklight.ru"
    )
