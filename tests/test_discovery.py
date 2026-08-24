from lumimatch.discovery import product_url_score, xml_locations


def test_xml_locations_supports_namespace() -> None:
    xml = b"<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'><url><loc>https://example.test/store/a/</loc></url></urlset>"
    assert xml_locations(xml) == ["https://example.test/store/a/"]


def test_product_url_is_prioritized() -> None:
    assert product_url_score(
        "https://example.test/store/cl164321/"
    ) > product_url_score("https://example.test/about/")
