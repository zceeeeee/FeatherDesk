"""Tests for the Bilibili search skill adapter."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from src.core.script_engine import ScriptEngine
from src.skill_library.search.bilibili_search import run


def _noop(*args):
    return "ok"


def _make_engine(goto_fn=None, log_fn=None):
    """创建注入了 mock 函数的 ScriptEngine。"""
    engine = ScriptEngine()
    engine.register_functions(
        {
            "goto": goto_fn or _noop,
            "run_js": lambda code: {"success": True},
            "wait": _noop,
            "wait_for_navigation": _noop,
            "get_url": lambda: "",
            "log": log_fn or _noop,
        }
    )
    return engine


def test_bilibili_search_navigates_to_search_url():
    """run() 直接导航到 Bilibili 搜索结果页。"""
    urls = []
    logs = []
    engine = _make_engine(
        goto_fn=lambda url: urls.append(url) or "ok",
        log_fn=lambda msg: logs.append(msg),
    )
    source = Path("src/skill_library/search/bilibili_search.py").read_text(
        encoding="utf-8"
    )

    result = engine.execute(source + '\nresult = run("test")\n')

    assert result.success is True
    assert urls == ["https://search.bilibili.com/all?keyword=test"]


def test_bilibili_search_encodes_chinese_keyword():
    """中文关键词应出现在搜索 URL 中。"""
    urls = []
    engine = _make_engine(goto_fn=lambda url: urls.append(url) or "ok")
    source = Path("src/skill_library/search/bilibili_search.py").read_text(
        encoding="utf-8"
    )

    result = engine.execute(source + '\nresult = run("机器学习")\n')

    assert result.success is True
    assert len(urls) == 1
    assert "search.bilibili.com" in urls[0]
    assert "机器学习" in urls[0]


def test_bilibili_search_logs_completion():
    """搜索完成后应输出日志。"""
    logs = []
    engine = _make_engine(log_fn=lambda msg: logs.append(msg))
    source = Path("src/skill_library/search/bilibili_search.py").read_text(
        encoding="utf-8"
    )

    result = engine.execute(source + '\nresult = run("test")\n')

    assert result.success is True
    assert any("test" in msg for msg in logs)


def test_bilibili_search_source_runs_inside_script_engine():
    """技能源码可在 ScriptEngine 中完整执行。"""
    source = Path("src/skill_library/search/bilibili_search.py").read_text(
        encoding="utf-8"
    )
    urls = []
    engine = _make_engine(goto_fn=lambda url: urls.append(url) or "ok")

    result = engine.execute(source + '\nresult = run("test")\n')

    assert result.success is True
    assert urls == ["https://search.bilibili.com/all?keyword=test"]
