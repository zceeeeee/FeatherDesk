"""Tests for the Taobao product search skill adapter."""

from __future__ import annotations

from pathlib import Path

from src.core.script_engine import ScriptEngine


def test_taobao_skill_navigates_and_returns_structured_product_result():
    urls = []
    logs = []
    engine = ScriptEngine()
    engine.register_functions(
        {
            "goto": lambda url: urls.append(url) or "ok",
            "wait": lambda seconds: None,
            "url_quote": lambda value: value.replace(" ", "+"),
            "taobao_collect_products": lambda keyword, max_items=20: {
                "keyword": keyword,
                "products": [],
            },
            "log": lambda message: logs.append(message),
        }
    )
    source = Path("src/skill_library/search/taobao_search.py").read_text(
        encoding="utf-8"
    )

    result = engine.execute(source + '\nresult = run("蓝牙 耳机")\n')

    assert result.success is True
    assert urls == ["https://s.taobao.com/search?q=蓝牙+耳机"]
    assert result.return_value == {"keyword": "蓝牙 耳机", "products": []}
    assert any("蓝牙 耳机" in message for message in logs)
