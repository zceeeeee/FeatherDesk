"""Tests for the Xiaohongshu SMS login skill adapter."""

from __future__ import annotations

from pathlib import Path

from src.core.script_engine import ScriptEngine
from src.skill_library.others.xiaohongshu_login import (
    _accept_agreement,
    _click_get_code,
    run,
)


def _noop(*args):
    return "ok"


def test_xiaohongshu_login_requests_code_and_stops_for_manual_entry():
    js_calls = []

    def run_js(code):
        js_calls.append(code)
        return {"success": True}

    result = run(
        "13800138000",
        wait_seconds=0,
        goto_fn=_noop,
        run_js_fn=run_js,
        wait_fn=_noop,
        get_url_fn=lambda: "https://www.xiaohongshu.com/login",
        get_text_fn=lambda: "手机号 获取验证码 用户协议 隐私政策",
        log_fn=_noop,
    )

    assert result["success"] is True
    assert result["requires_manual_code"] is True
    assert result["phone_number"] == "13800138000"
    assert len(js_calls) == 4


def test_xiaohongshu_login_normalizes_china_country_code():
    result = run(
        "+86 138-0013-8000",
        wait_seconds=0,
        goto_fn=_noop,
        run_js_fn=lambda code: {"success": True},
        wait_fn=_noop,
        get_url_fn=lambda: "https://www.xiaohongshu.com/login",
        get_text_fn=lambda: "",
        log_fn=_noop,
    )

    assert result["success"] is True
    assert result["phone_number"] == "13800138000"


def test_xiaohongshu_login_rejects_invalid_phone_number():
    result = run(
        "12345",
        wait_seconds=0,
        goto_fn=_noop,
        run_js_fn=lambda code: {"success": True},
        wait_fn=_noop,
        get_url_fn=lambda: "https://www.xiaohongshu.com/login",
        get_text_fn=lambda: "",
        log_fn=_noop,
    )

    assert result["success"] is False
    assert "valid 11-digit phone number" in result["error"]


def test_xiaohongshu_login_reports_security_restriction():
    result = run(
        "13800138000",
        wait_seconds=0,
        goto_fn=_noop,
        run_js_fn=lambda code: {"success": True},
        wait_fn=_noop,
        get_url_fn=lambda: "https://www.xiaohongshu.com/website-login/error",
        get_text_fn=lambda: "安全限制 IP存在风险",
        log_fn=_noop,
    )

    assert result["success"] is False
    assert result["requires_network_change"] is True


def test_xiaohongshu_agreement_script_handles_custom_checkbox():
    js_calls = []

    result = _accept_agreement(
        lambda code: js_calls.append(code) or {"success": True}
    )

    assert result["success"] is True
    assert "我已阅读并同意" in js_calls[0]
    assert "elementFromPoint" in js_calls[0]
    assert "role_checkbox" in js_calls[0]
    assert "agreement_left_point" in js_calls[0]


def test_xiaohongshu_get_code_script_prefers_code_input_row():
    js_calls = []

    result = _click_get_code(lambda code: js_calls.append(code) or {"success": True})

    assert result["success"] is True
    assert "codeInput" in js_calls[0]
    assert "sameRow" in js_calls[0]
    assert "rightOfCodeInput" in js_calls[0]
    assert "发送验证码" in js_calls[0]


def test_xiaohongshu_login_source_runs_inside_script_engine():
    source = Path("src/skill_library/others/xiaohongshu_login.py").read_text(
        encoding="utf-8"
    )
    engine = ScriptEngine()
    engine.register_functions(
        {
            "goto": _noop,
            "run_js": lambda code: {"success": True},
            "wait": _noop,
            "get_url": lambda: "https://www.xiaohongshu.com/login",
            "get_text": lambda: "手机号 获取验证码 用户协议 隐私政策",
        }
    )

    result = engine.execute(
        source + "\nresult = run('13800138000', wait_seconds=0)\nprint(result)"
    )

    assert result.success is True
    assert "'requires_manual_code': True" in result.output
