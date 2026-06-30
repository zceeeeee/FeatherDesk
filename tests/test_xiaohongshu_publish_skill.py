"""Tests for the Xiaohongshu image-text publish skill adapter."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from src.core.script_engine import ScriptEngine
from src.skill_library.send.xiaohongshu_publish import (
    _click_final_publish,
    _click_generate_image,
    _click_next_step,
    _click_text_to_image,
    _detect_image_edit,
    _detect_preview_image,
    _fill_publish_content,
    run,
)


def _noop(*args):
    return "ok"


def _with_page(html, callback):
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1200, "height": 800})
                page.set_content(html)
                return callback(page)
            finally:
                browser.close()
    except PlaywrightError as exc:
        pytest.skip(f"Playwright browser unavailable: {exc}")


def _mock_publish_run_js(logged_in=True):
    def run_js(code):
        if "phone_login:" in code:
            return {
                "success": True,
                "logged_in": logged_in,
                "phone_login": not logged_in,
            }
        if "ME_BUTTON_TEXT" in code:
            return {
                "success": True,
                "me_button": True,
                "method": "bottom_me_button",
            }
        if "Phone input not found" in code:
            return {"success": True, "value": "13574133406"}
        if "Agreement checkbox not found" in code:
            return {"success": True, "checked": True}
        if "Get-code button not found" in code:
            return {"success": True, "text": "获取验证码"}
        if "ABOUT_US_TEXT" in code:
            return {"success": True, "about_us": True, "lower_left": True}
        if "TEXT_TO_IMAGE_TEXT" in code:
            return {
                "success": True,
                "text": "文字配图",
                "method": "click_text_to_image",
            }
        if "content_value" in code:
            return {"success": True, "content_value": "测试图文内容"}
        if "GENERATE_IMAGE_TEXT" in code:
            return {
                "success": True,
                "text": "生成图片",
                "method": "lower_generate_image_button",
            }
        if "PREVIEW_IMAGE_TEXT" in code:
            return {"success": True, "preview_image": True, "top_left": True}
        if "NEXT_STEP_TEXT" in code:
            return {
                "success": True,
                "text": "下一步",
                "method": "lower_left_next_step",
            }
        if "IMAGE_EDIT_TEXT" in code:
            return {"success": True, "image_edit": True, "top": True}
        if "FINAL_PUBLISH_TEXT" in code:
            return {
                "success": True,
                "text": "发布",
                "method": "lower_publish_button",
            }
        return {"success": True}

    return run_js


def test_xiaohongshu_publish_runs_when_already_logged_in():
    urls = []
    logs = []

    result = run(
        "测试图文内容",
        max_wait_seconds=0,
        goto_fn=lambda url: urls.append(url) or "ok",
        run_js_fn=_mock_publish_run_js(logged_in=True),
        wait_fn=_noop,
        get_url_fn=lambda: "https://creator.xiaohongshu.com/publish/publish",
        get_text_fn=lambda: "",
        log_fn=lambda message: logs.append(message),
    )

    assert result["success"] is True
    assert urls == [
        "https://www.xiaohongshu.com/login",
        "https://creator.xiaohongshu.com/publish/publish?source=official&from=tab_switch&target=image",
    ]
    assert result["content"] == "测试图文内容"
    assert logs == ["Xiaohongshu publish button clicked"]


def test_xiaohongshu_publish_requests_code_and_waits_for_about_us():
    urls = []
    waits = []
    logs = []

    result = run(
        "测试图文内容",
        phone_number="13574133406",
        max_wait_seconds=0,
        goto_fn=lambda url: urls.append(url) or "ok",
        run_js_fn=_mock_publish_run_js(logged_in=False),
        wait_fn=lambda seconds: waits.append(seconds) or "ok",
        get_url_fn=lambda: "https://www.xiaohongshu.com/explore",
        get_text_fn=lambda: "",
        log_fn=lambda message: logs.append(message),
    )

    assert result["success"] is True
    assert result["phone_number"] == "13574133406"
    assert urls[-1] == (
        "https://creator.xiaohongshu.com/publish/publish"
        "?source=official&from=tab_switch&target=image"
    )
    steps = [step["step"] for step in result["steps"]]
    assert "click_text_to_image" in steps
    assert "fill_publish_content" in steps
    assert steps.index("click_text_to_image") < steps.index("fill_publish_content")
    assert "wait_after_fill_publish_content" in steps
    assert "click_generate_image" in steps
    assert "detect_preview_image" in steps
    assert "click_next_step" in steps
    assert "detect_image_edit" in steps
    assert "click_final_publish" in steps
    assert steps.index("wait_after_fill_publish_content") > steps.index("fill_publish_content")
    assert steps.index("click_generate_image") > steps.index("wait_after_fill_publish_content")
    assert steps.index("detect_preview_image") > steps.index("click_generate_image")
    assert steps.index("click_next_step") > steps.index("detect_preview_image")
    assert steps.index("detect_image_edit") > steps.index("click_next_step")
    assert steps.index("click_final_publish") > steps.index("detect_image_edit")
    assert "fill_phone" in steps
    assert "accept_agreement" in steps
    assert "click_get_code" in steps
    assert any(step.startswith("wait_about_us_attempt_") for step in steps)
    assert logs[0] == "Please enter the Xiaohongshu SMS verification code in the browser."
    assert logs[-1] == "Xiaohongshu publish button clicked"


def test_xiaohongshu_publish_requires_phone_when_not_logged_in():
    result = run(
        "测试图文内容",
        max_wait_seconds=0,
        goto_fn=_noop,
        run_js_fn=_mock_publish_run_js(logged_in=False),
        wait_fn=_noop,
        get_url_fn=lambda: "https://www.xiaohongshu.com/login",
        get_text_fn=lambda: "",
        log_fn=lambda message: None,
    )

    assert result["success"] is False
    assert result["requires_phone_number"] is True


def test_xiaohongshu_publish_clicks_text_to_image_generates_and_publishes():
    html = """
    <body>
      <input id="search" placeholder="搜索" style="width:240px;height:32px" />
      <button id="mode" role="tab" style="width:120px;height:36px">文字配图</button>
      <textarea id="content" placeholder="请输入图文内容"
        style="display:none;width:600px;height:180px;border:1px solid #ddd"></textarea>
      <button id="generate" style="position:fixed;left:320px;bottom:24px;
        width:120px;height:36px;background:#ff2442;color:white">生成图片</button>
      <h2 id="preview" style="display:none;position:fixed;left:16px;top:20px">预览图片</h2>
      <button id="next" style="display:none;position:fixed;left:24px;bottom:24px;
        width:96px;height:36px;background:#ff2442;color:white">下一步</button>
      <h2 id="image-edit" style="display:none;position:fixed;left:260px;top:20px">图片编辑</h2>
      <button id="publish" style="display:none;position:fixed;left:520px;bottom:24px;
        width:96px;height:36px;background:#ff2442;color:white">发布</button>
      <div id="published">no</div>
      <script>
        document.getElementById('mode').addEventListener('click', () => {
          document.getElementById('content').style.display = 'block';
          document.body.setAttribute('data-mode', 'text-to-image');
        });
        document.getElementById('generate').addEventListener('click', () => {
          document.getElementById('preview').style.display = 'block';
          document.getElementById('next').style.display = 'block';
        });
        document.getElementById('next').addEventListener('click', () => {
          document.getElementById('preview').style.display = 'none';
          document.getElementById('next').style.display = 'none';
          document.getElementById('image-edit').style.display = 'block';
          document.getElementById('publish').style.display = 'block';
        });
        document.getElementById('publish').addEventListener('click', () => {
          document.getElementById('published').textContent =
            document.getElementById('content').value;
        });
      </script>
    </body>
    """

    def assert_page(page):
        mode_result = _click_text_to_image(lambda code: page.evaluate(code))
        fill_result = _fill_publish_content(
            lambda code: page.evaluate(code),
            "第一行图文内容\n第二行图文内容",
        )
        generate_result = _click_generate_image(lambda code: page.evaluate(code))
        preview_result = _detect_preview_image(lambda code: page.evaluate(code))
        next_result = _click_next_step(lambda code: page.evaluate(code))
        image_edit_result = _detect_image_edit(lambda code: page.evaluate(code))
        publish_result = _click_final_publish(lambda code: page.evaluate(code))

        assert mode_result["success"] is True
        assert fill_result["success"] is True
        assert generate_result["success"] is True
        assert preview_result["success"] is True
        assert next_result["success"] is True
        assert image_edit_result["success"] is True
        assert publish_result["success"] is True
        assert page.locator("body").get_attribute("data-mode") == "text-to-image"
        assert page.locator("#content").input_value() == "第一行图文内容\n第二行图文内容"
        assert page.locator("#search").input_value() == ""
        assert "第一行图文内容" in page.locator("#published").text_content()

    _with_page(html, assert_page)


def test_xiaohongshu_publish_source_runs_inside_script_engine():
    source = Path("src/skill_library/send/xiaohongshu_publish.py").read_text(
        encoding="utf-8"
    )
    urls = []
    engine = ScriptEngine()
    engine.register_functions(
        {
            "goto": lambda url: urls.append(url) or "ok",
            "run_js": _mock_publish_run_js(logged_in=True),
            "wait": _noop,
            "get_url": lambda: "https://creator.xiaohongshu.com/publish/publish",
            "get_text": lambda: "",
        }
    )

    result = engine.execute(
        source + "\nresult = run('测试图文内容', max_wait_seconds=0)\nprint(result)"
    )

    assert result.success is True
    assert urls == [
        "https://www.xiaohongshu.com/login",
        "https://creator.xiaohongshu.com/publish/publish?source=official&from=tab_switch&target=image",
    ]
    assert "'success': True" in result.output
