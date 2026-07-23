"""Tests for the combined Zhihu publishing workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.skill_router import SkillRouter
from src.skill_library.zhihu import zhihu_send_article, zhihu_total


LIBRARY_DIR = Path(__file__).resolve().parents[1] / "src" / "skill_library"


def test_total_skill_routes_and_builds_existing_adapters() -> None:
    router = SkillRouter(library_dir=LIBRARY_DIR)
    decision = router.route("知乎全流程")

    assert decision.skill is not None
    assert decision.skill.id == "domain/zhihu_total"
    assert "def __zhihu_send_run(" in decision.script
    assert "def __zhihu_approve_run(" not in decision.script
    assert "def __zhihu_comment_run(" in decision.script
    assert "def __zhihu_shoucang_run(" in decision.script
    compile(decision.script, "<zhihu_total>", "exec")


def test_total_prompts_for_article_then_comment_before_browser_actions() -> None:
    router = SkillRouter(library_dir=LIBRARY_DIR)
    router.load()
    script = router.build_script(router._skills["domain/zhihu_total"], "知乎全流程")
    prompts: list[str] = []
    answers = iter(
        [
            "手动输入/确认",
            "测试正文",
            "手动输入/确认",
            "测试标题",
            "no",
            "手动输入/确认",
            "测试评论",
        ]
    )
    auth_calls = 0

    def panel_prompt(question: str) -> str:
        prompts.append(question)
        return next(answers)

    def ensure_auth(*_args, **_kwargs) -> bool:
        nonlocal auth_calls
        auth_calls += 1
        if auth_calls == 1:
            return True
        raise RuntimeError("STOP_AFTER_PROMPTS")

    with pytest.raises(RuntimeError, match="STOP_AFTER_PROMPTS"):
        exec(
            script,
            {
                "panel_prompt": panel_prompt,
                "panel_show": lambda: None,
                "panel_set_fields": lambda _fields: None,
                "ensure_auth": ensure_auth,
                "llm_generate_text": lambda _prompt: "unused",
            },
        )

    assert len(prompts) == 7
    assert "文章内容请选择输入方式" in prompts[0]
    assert "文章标题请选择输入方式" in prompts[2]
    assert "添加 AI 配图" in prompts[4]
    assert "评论内容请选择输入方式" in prompts[5]
    assert "请输入要发布的知乎评论内容" in prompts[6]


def test_total_passes_published_url_to_comment_and_collection(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    article_url = "https://zhuanlan.zhihu.com/p/123456"

    monkeypatch.setitem(
        zhihu_total.run.__globals__,
        "__zhihu_send_run",
        lambda **kwargs: calls.append(("send", kwargs)) or article_url,
    )
    monkeypatch.setitem(
        zhihu_total.run.__globals__,
        "__zhihu_comment_run",
        lambda **kwargs: calls.append(("comment", kwargs)),
    )
    monkeypatch.setitem(
        zhihu_total.run.__globals__,
        "__zhihu_shoucang_run",
        lambda **kwargs: calls.append(("collect", kwargs)),
    )
    monkeypatch.setitem(zhihu_total.run.__globals__, "wait", lambda _seconds: None)
    monkeypatch.setitem(zhihu_total.run.__globals__, "log", lambda _message: None)

    result = zhihu_total.run(
        title="标题",
        keyword="正文",
        add_picture=False,
        comment_keyword="评论",
        comment_use_ai=False,
        comment_requirement="",
    )

    assert result == article_url
    assert [name for name, _payload in calls] == [
        "send",
        "comment",
        "collect",
    ]
    assert calls[1][1]["article_url"] == article_url
    assert calls[2][1]["article_url"] == article_url


def test_publish_returns_public_article_url(monkeypatch) -> None:
    monkeypatch.setitem(
        zhihu_send_article.run.__globals__, "ensure_auth", lambda *_args: True
    )
    monkeypatch.setitem(zhihu_send_article.run.__globals__, "goto", lambda _url: None)
    monkeypatch.setitem(
        zhihu_send_article.run.__globals__, "_require_write_editor", lambda **_kwargs: None
    )
    monkeypatch.setitem(zhihu_send_article.run.__globals__, "fill", lambda *_args: None)
    monkeypatch.setitem(zhihu_send_article.run.__globals__, "wait", lambda _seconds: None)
    monkeypatch.setitem(
        zhihu_send_article.run.__globals__, "wait_for_element", lambda *_args, **_kwargs: None
    )
    monkeypatch.setitem(
        zhihu_send_article.run.__globals__,
        "wait_for_navigation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setitem(zhihu_send_article.run.__globals__, "click", lambda *_args: None)
    monkeypatch.setitem(zhihu_send_article.run.__globals__, "log", lambda _message: None)
    monkeypatch.setitem(zhihu_send_article.run.__globals__, "run_js", lambda _script: "ok")
    monkeypatch.setitem(
        zhihu_send_article.run.__globals__,
        "get_url",
        lambda: "https://zhuanlan.zhihu.com/p/123456/edit?from=write",
    )
    monkeypatch.setitem(
        zhihu_send_article.run.__globals__,
        "_close_publish_success_modal",
        lambda **_kwargs: True,
    )

    result = zhihu_send_article.run("标题", "正文", add_picture=False)

    assert result == "https://zhuanlan.zhihu.com/p/123456"
