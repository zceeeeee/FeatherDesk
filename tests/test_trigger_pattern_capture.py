"""Tests for trigger_patterns captured-parameter passthrough.

验证：trigger_patterns 命中且捕获到 group(1) 时，
1. 命中技能走高置信直接命中路径（source="keyword"）
2. captured 透传到 build_script，作为 keyword 候选初值
3. keyword 候选经 LLM 校验确认/纠正（全量校验策略）
"""

from __future__ import annotations

import pytest

from src.core.skill_router import SkillRouter, SkillRouterInfo


def _router_with_real_library(llm_caller=None):
    """构造一个加载真实 skills.yaml 的 SkillRouter。"""
    from pathlib import Path

    library_dir = Path(__file__).resolve().parent.parent / "src" / "skill_library"
    router = SkillRouter(library_dir=library_dir, llm_caller=llm_caller)
    router.load()
    return router


def test_match_pattern_captures_keyword_group():
    """trigger_patterns 命中时，_match_pattern 返回捕获的 group(1)。"""
    router = _router_with_real_library()
    baidu = router.get_skill("domain/baidu_search")
    assert baidu is not None

    score, captured = router._match_pattern(baidu, "在百度搜索 python教程")
    assert score == 0.95
    assert captured == "python教程"


def test_match_pattern_returns_none_for_no_capture_group():
    """无捕获组的 pattern（如 wps/wechat 的断言式）→ captured=None。"""
    router = _router_with_real_library()
    wps = router.get_skill("domain/wps_writer_export")
    assert wps is not None

    score, captured = router._match_pattern(
        wps, "用wps写文章标题是hello"
    )
    assert score == 0.95
    # wps 的 pattern 无捕获组
    assert captured is None


def test_resolve_captured_param_targets_keyword_field():
    """captured 映射到 params 中第一个 type=keyword 的字段。"""
    router = _router_with_real_library()
    baidu = router.get_skill("domain/baidu_search")
    assert baidu is not None

    target = router._resolve_captured_param(baidu, "python教程")
    assert target == "keyword"

    # 无 captured 或空 → 不采用
    assert router._resolve_captured_param(baidu, None) is None
    assert router._resolve_captured_param(baidu, "") is None


class StubJsonCaller:
    """可控的 LLM caller：按调用序返回预设响应，并记录每次调用。"""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def call_json(self, prompt, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        if self.responses:
            return self.responses.pop(0)
        return {"keyword": "-1"}

    def call(self, *args, **kwargs):
        raise AssertionError("free-text call 不应被调用")


def _is_keyword_verify(call):
    """判断一次 call_json 是否为 keyword 校验调用（而非参数抽取）。"""
    prompt = call.get("prompt", "")
    return "关键词清洗器" in prompt


def _is_param_extraction(call):
    prompt = call.get("prompt", "")
    return "parameter extractor" in prompt or "参数提取" in prompt


def test_route_search_skill_llm_verifies_captured_keyword():
    """端到端：'在百度搜索 python教程' 命中后 LLM 校验关键词。

    关键词由 trigger_patterns 捕获（rule 亦能抽取），由于采用全量 LLM 校验
    策略，会调用一次 keyword 校验（确认或纠正），但不再触发参数兜底抽取。
    """
    # 第 1 次响应 = keyword 校验（返回干净原值）
    # 若发生第 2 次（参数兜底抽取）会取默认 {"keyword":"-1"}，不影响断言
    caller = StubJsonCaller({"keyword": "python教程", "clean": True})
    router = _router_with_real_library(llm_caller=caller)

    decision = router.route("在百度搜索 python教程")

    assert decision.skill is not None
    assert decision.skill.id == "domain/baidu_search"
    assert decision.source == "keyword"
    assert decision.confidence >= 0.8
    assert "python教程" in decision.script
    # 校验调用发生了
    verify_calls = [c for c in caller.calls if _is_keyword_verify(c)]
    assert len(verify_calls) >= 1


def test_route_search_skill_llm_cleans_noisy_keyword():
    """带噪音的捕获值会被 LLM 校验纠正。

    '百度搜python教程然后截图' 的 rule/captured 值为 'python教程然后截图'，
    LLM 校验应纠正为干净关键词。
    """
    caller = StubJsonCaller({"keyword": "python教程", "clean": False})
    router = _router_with_real_library(llm_caller=caller)

    decision = router.route("百度搜python教程然后截图")

    assert decision.skill is not None
    assert decision.skill.id == "domain/baidu_search"
    # 纠正后的干净关键词进入脚本，原噪音值不在
    assert "python教程" in decision.script
    assert "然后截图" not in decision.script
    verify_calls = [c for c in caller.calls if _is_keyword_verify(c)]
    assert len(verify_calls) >= 1


def test_route_search_skill_postfix_form_captures_keyword():
    """后置形式 '搜索 python教程 用百度' 也能被第二条 pattern 捕获并校验。"""
    caller = StubJsonCaller({"keyword": "python教程", "clean": True})
    router = _router_with_real_library(llm_caller=caller)

    decision = router.route("搜索 python教程 用百度")

    assert decision.skill is not None
    assert decision.skill.id == "domain/baidu_search"
    assert "python教程" in decision.script
    verify_calls = [c for c in caller.calls if _is_keyword_verify(c)]
    assert len(verify_calls) >= 1
