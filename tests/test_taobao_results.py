"""Tests for Taobao product result extraction and statistics."""

from __future__ import annotations

from src.layer_3.taobao_results import (
    build_taobao_search_result,
    enrich_taobao_products,
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
                    "manufacturer": "Sony",
                    "model": "WH-1000XM6",
                    "specifications": "蓝牙 5.3；黑色",
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
            "manufacturer": "Sony",
            "model": "WH-1000XM6",
            "specifications": "蓝牙 5.3；黑色",
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


def test_build_taobao_search_result_defaults_to_five_products():
    result = build_taobao_search_result(
        "显示器",
        [
            {"title": title, "shop": f"店{title}", "price": price}
            for title, price in zip("ABCDEF", range(10, 70, 10), strict=True)
        ],
    )

    assert [item["title"] for item in result["products"]] == list("ABCDE")
    assert result["statistics"]["count"] == 6


def test_enrich_taobao_products_only_opens_incomplete_product_details():
    class DetailPage:
        def __init__(self):
            self.url = "https://s.taobao.com/search?q=电脑"
            self.goto_urls = []

        def goto(self, url, **_kwargs):
            self.goto_urls.append(url)
            self.url = url

        def wait_for_timeout(self, _milliseconds):
            return None

        def evaluate(self, script):
            assert "TAOBAO_DETAIL_EXTRACTOR" in script
            return {
                "title": "ThinkPad X200 笔记本电脑",
                "manufacturer": "联想",
                "model": "X200",
                "specifications": "16GB 内存；512GB SSD",
            }

    page = DetailPage()
    products = [
        {
            "title": "完整商品",
            "model": "M1",
            "specifications": "16GB",
            "product_url": "https://item.taobao.com/item.htm?id=1",
        },
        {
            "title": "待补充商品",
            "model": "",
            "specifications": "",
            "product_url": "https://item.taobao.com/item.htm?id=2",
        },
    ]

    result = enrich_taobao_products(page, products, max_products=5)

    assert page.goto_urls == [
        "https://item.taobao.com/item.htm?id=2",
        "https://s.taobao.com/search?q=电脑",
    ]
    assert result[0]["model"] == "M1"
    assert result[1]["manufacturer"] == "联想"
    assert result[1]["model"] == "X200"
    assert result[1]["specifications"] == "16GB 内存；512GB SSD"


def test_enrich_taobao_products_preserves_card_data_when_detail_fails():
    class FailingPage:
        def __init__(self):
            self.url = "https://s.taobao.com/search?q=电脑"
            self.goto_urls = []

        def goto(self, url, **_kwargs):
            self.goto_urls.append(url)
            self.url = url
            if "item.htm" in url:
                raise RuntimeError("detail blocked")

        def evaluate(self, _script):
            raise AssertionError("detail extraction should not run after navigation fails")

    page = FailingPage()
    products = [
        {
            "title": "搜索页标题",
            "shop": "电脑店",
            "model": "",
            "specifications": "",
            "product_url": "https://item.taobao.com/item.htm?id=3",
        }
    ]

    result = enrich_taobao_products(page, products, max_products=5)

    assert result == products
    assert page.goto_urls == [
        "https://item.taobao.com/item.htm?id=3",
        "https://s.taobao.com/search?q=电脑",
    ]


def test_build_taobao_search_result_omits_histogram_when_no_price_is_available():
    result = build_taobao_search_result(
        "书签",
        [{"title": "无价商品", "shop": "店铺", "price": "券后面议"}],
    )

    assert result["products"][0]["price"] is None
    assert result["statistics"] is None
    assert result["histogram"] is None
