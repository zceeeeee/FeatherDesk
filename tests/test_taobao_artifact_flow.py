"""Tests for passing structured skill results to desktop messages."""

from __future__ import annotations

from src.core.agent_loop import AgentLoop, AgentState, AgentStep, AgentTaskResult
from src.core.script_engine import ScriptEngine


def test_script_engine_captures_explicit_result_value():
    result = ScriptEngine().execute("__result__ = {'type': 'taobao_product_search'}")

    assert result.success is True
    assert result.return_value == {"type": "taobao_product_search"}


def test_task_result_has_structured_artifacts_for_task_service():
    result = AgentTaskResult(success=True, task="淘宝搜索耳机")

    assert result.artifacts == {}


def test_agent_loop_collects_structured_script_artifact():
    agent = AgentLoop()
    agent._script_engine = ScriptEngine()
    agent._task_artifacts = {}
    step = AgentStep(
        step_number=1,
        state=AgentState.ACT,
        script="__result__ = {'type': 'taobao_product_search', 'products': []}",
    )

    state = agent._do_act(step)

    assert state is AgentState.DONE
    assert agent._task_artifacts["taobao_product_search"] == {
        "type": "taobao_product_search",
        "products": [],
    }
