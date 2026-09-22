"""Unit and integration tests for Jev element scanner and decision planner."""

import pytest
from unittest.mock import MagicMock, patch

from src.jev.element_scanner import ElementScanner, ScannedElement
from src.jev.jev_client import JevDecision, JevPlanner, _extract_fill_value_from_task


def test_extract_fill_value():
    assert _extract_fill_value_from_task("在百度搜索框输入 python 并点击搜索") == "python"
    assert _extract_fill_value_from_task('在搜索栏输入 "Playwright MCP"') == "Playwright MCP"
    assert _extract_fill_value_from_task("搜索 deepseek 并回车") == "deepseek"
    assert _extract_fill_value_from_task("type 'admin' into username") == "admin"


def test_scanned_element_description():
    el = ScannedElement(
        ref="e1",
        tag="input",
        role="searchbox",
        name="百度搜索",
        placeholder="请输入关键词",
        value="",
        selector="#kw",
        bbox={"x": 100, "y": 200, "width": 400, "height": 40},
    )
    desc = el.description
    assert "<input role='searchbox' (Editable Input Field)>" in desc
    assert "label='百度搜索'" in desc
    assert "placeholder='请输入关键词' (recommendation hint)" in desc
    assert "sel='#kw'" in desc

    # Non-input element
    btn = ScannedElement(
        ref="e2",
        tag="button",
        role="button",
        name="百度一下",
        selector="#su",
    )
    btn_desc = btn.description
    assert "<button role='button'>" in btn_desc
    assert "text='百度一下'" in btn_desc


def test_heuristic_planner_decision():
    elements = [
        ScannedElement(
            ref="e1",
            tag="a",
            role="link",
            name="新闻",
            selector="a#news",
        ),
        ScannedElement(
            ref="e2",
            tag="input",
            role="textbox",
            placeholder="请输入搜索词",
            selector="#kw",
        ),
        ScannedElement(
            ref="e3",
            tag="button",
            role="button",
            name="百度一下",
            selector="#su",
        ),
    ]

    planner = JevPlanner(api_key="")  # offline heuristic mode
    decision = planner.plan(
        task="在百度搜索框输入 python 并点击搜索",
        page_url="https://www.baidu.com",
        page_title="百度一下",
        elements=elements,
    )

    assert decision.target_ref == "e2"
    assert decision.action_type == "fill"
    assert decision.input_value == "python"
    assert decision.confidence >= 0.8
    assert decision.target_element is not None
    assert decision.target_element.selector == "#kw"


def test_heuristic_planner_click_decision():
    elements = [
        ScannedElement(
            ref="e1",
            tag="input",
            role="textbox",
            value="python",
            selector="#kw",
        ),
        ScannedElement(
            ref="e2",
            tag="button",
            role="button",
            name="百度一下",
            selector="#su",
        ),
    ]

    planner = JevPlanner(api_key="")
    decision = planner.plan(
        task="点击百度一下按钮",
        page_url="https://www.baidu.com",
        page_title="百度一下",
        elements=elements,
    )

    assert decision.target_ref == "e2"
    assert decision.action_type == "click"
    assert decision.confidence >= 0.8


@pytest.mark.asyncio
async def test_element_scanner_sync_and_async():
    from playwright.async_api import async_playwright

    sample_html = """
    <!DOCTYPE html>
    <html>
    <body>
      <header>
        <a href="/home" id="nav-home">Home</a>
      </header>
      <main>
        <input type="text" id="username" placeholder="Username" />
        <input type="password" id="pwd" placeholder="Password" />
        <button id="login-btn" type="submit">Log In</button>
      </main>
    </body>
    </html>
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(sample_html)

        scanner = ElementScanner(max_elements=10)
        elements = await scanner.scan_async(page)

        assert len(elements) == 4
        refs = [e.ref for e in elements]
        assert refs == ["e1", "e2", "e3", "e4"]

        tags = [e.tag for e in elements]
        assert "a" in tags
        assert "input" in tags
        assert "button" in tags

        await browser.close()


def test_cloud_jev_live_api():
    """Verify live TypeSafe Jev System 1 cloud model evaluation with configured API key."""
    import os
    api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    if not api_key:
        pytest.skip("No TYPESAFE_API_KEY configured")

    elements = [
        ScannedElement(
            ref="e1",
            tag="input",
            role="searchbox",
            placeholder="Search keywords",
            selector="#search-input",
        ),
        ScannedElement(
            ref="e2",
            tag="button",
            role="button",
            name="Search",
            selector="#submit-btn",
        ),
    ]

    planner = JevPlanner()  # Uses configured TYPESAFE_API_KEY
    assert planner.api_key == api_key

    decision = planner.plan(
        task="Type 'python' into searchbox",
        page_url="https://example.com",
        page_title="Example Search",
        elements=elements,
    )

    assert decision.mode == "cloud_api"
    assert decision.model_name in ("jev-latest", "jev-1.13.0")
    assert decision.target_ref == "e1"
    assert decision.action_type == "fill"
    assert decision.confidence > 0.5

