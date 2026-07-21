"""Tests for Taobao product result extraction and statistics."""

from __future__ import annotations

from src.layer_3.taobao_results import (
    build_taobao_search_result,
    extract_taobao_products,
)


class FakePage:
    url = "https://s.taobao.com/search?q=耳机"

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def evaluate(self, script, *args):
        self.calls += 1
        assert 'querySelector("img")' in script
        assert "item.taobao.com" in script
        return self.payload


def test_extract_taobao_products_keeps_visible_product_fields():
    page = FakePage(
        {
            "products": [
                {
                    "title": "无线降噪耳机",
                    "shop": "音频旗舰店",
            "price": 199.0,
            "price_text": "¥199.00",
                    "image_url": "https://img.example/earbuds.jpg",
                    "product_url": "https://item.taobao.com/item.htm?id=1",
                }
            ]
        }
    )

    products = extract_taobao_products(page, max_items=3)

    assert page.calls == 1
    assert products == [
        {
            "title": "无线降噪耳机",
            "shop": "音频旗舰店",
            "price": 199.0,
            "price_text": "¥199.00",
            "image_url": "https://img.example/earbuds.jpg",
            "product_url": "https://item.taobao.com/item.htm?id=1",
        }
    ]


def test_build_taobao_search_result_returns_top_three_and_price_statistics():
    result = build_taobao_search_result(
        "耳机",
        [
            {"title": "A", "shop": "店A", "price": "10", "image_url": "a"},
            {"title": "B", "shop": "店B", "price": "20", "image_url": "b"},
            {"title": "C", "shop": "店C", "price": "30", "image_url": "c"},
            {"title": "D", "shop": "店D", "price": "40", "image_url": "d"},
        ],
        max_products=3,
    )

    assert result["type"] == "taobao_product_search"
    assert result["keyword"] == "耳机"
    assert [item["title"] for item in result["products"]] == ["A", "B", "C"]
    assert result["statistics"] == {
        "count": 4,
        "min": 10.0,
        "max": 40.0,
        "average": 25.0,
        "median": 25.0,
    }
    assert result["histogram"]["mime_type"] == "image/png"
    assert result["histogram"]["data_url"].startswith("data:image/png;base64,")


def test_build_taobao_search_result_omits_histogram_when_no_price_is_available():
    result = build_taobao_search_result(
        "书签",
        [{"title": "无价商品", "shop": "店铺", "price": "券后面议"}],
    )

    assert result["products"][0]["price"] is None
    assert result["statistics"] is None
    assert result["histogram"] is None
