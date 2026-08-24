from lumimatch.extract import parse_product_page


def test_extracts_jsonld_product_and_photo() -> None:
    html = """
    <html><head>
      <link rel='canonical' href='/product/abc-123'>
      <script type='application/ld+json'>
      {"@context":"https://schema.org","@type":"Product","name":"Black Cylinder","sku":"ABC-123","image":["/img/black.jpg"],"offers":{"price":"12500","priceCurrency":"RUB","availability":"https://schema.org/InStock"}}
      </script>
    </head><body><h1>Black Cylinder</h1><div>Цвет: чёрный</div></body></html>
    """
    product = parse_product_page(
        html, "https://example.test/product/abc-123", "example.test"
    )
    assert product is not None
    assert product.sku == "ABC-123"
    assert product.price == 12500
    assert product.currency == "RUB"
    assert product.availability == "InStock"
    assert product.primary_image_url == "https://example.test/img/black.jpg"


def test_category_without_product_signal_is_ignored() -> None:
    html = "<html><head><title>Каталог</title></head><body><h1>Каталог светильников</h1></body></html>"
    assert (
        parse_product_page(html, "https://example.test/catalog/", "example.test")
        is None
    )
