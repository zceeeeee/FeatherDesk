"""Unit tests for LLM Planner and Dual-Model Comparison."""

import json
import os
from unittest.mock import MagicMock
import pytest

from src.jev.element_scanner import ScannedElement
from src.jev.jev_client import JevDecision, ComparisonResult
from src.jev.llm_planner import LLMPlanner, LLMDecision
from src.jev.web_app import app, session


@pytest.fixture
def sample_elements():
    return [
        ScannedElement(
            ref="e1",
            tag="input",
            role="searchbox",
            placeholder="搜索关键词",
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


def test_llm_planner_unconfigured(sample_elements):
    planner = LLMPlanner(api_key="")
    planner.api_key = ""
    decision = planner.plan(
        task="在搜索框输入 python",
        page_url="https://www.baidu.com",
        elements=sample_elements,
    )
    assert isinstance(decision, LLMDecision)
    assert decision.status == "unconfigured"
    assert decision.target_ref == "none"
    assert decision.action_type == "complete"


def test_llm_planner_mock_structured_output(sample_elements):
    mock_response_payload = {
        "target_ref": "e1",
        "action_type": "fill",
        "input_value": "pytest",
        "confidence": 0.98,
        "rationale": "Target e1 is the input search box matching the fill requirement.",
    }

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(mock_response_payload)
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    planner = LLMPlanner(api_key="test-key", model="mimo-v2.5")
    planner._client = mock_client

    decision = planner.plan(
        task="在搜索框输入 pytest",
        page_url="https://www.baidu.com",
        elements=sample_elements,
    )

    assert decision.status == "success"
    assert decision.target_ref == "e1"
    assert decision.action_type == "fill"
    assert decision.input_value == "pytest"
    assert decision.confidence == 0.98
    assert decision.target_element is not None
    assert decision.target_element.selector == "#kw"


def test_comparison_result_metrics(sample_elements):
    jev_dec = JevDecision(
        target_ref="e1",
        action_type="fill",
        input_value="test",
        confidence=0.92,
        timing_ms=320.0,
    )
    llm_dec = LLMDecision(
        target_ref="e1",
        action_type="fill",
        input_value="test",
        confidence=0.95,
        timing_ms=1280.0,
        model_name="mimo-v2.5",
    )

    cmp = ComparisonResult(
        jev_target="e1",
        jev_action="fill",
        jev_timing_ms=320.0,
        llm_target="e1",
        llm_action="fill",
        llm_timing_ms=1280.0,
        llm_model="mimo-v2.5",
        is_agreement=True,
        speedup_ratio=4.0,
        latency_diff_ms=960.0,
        summary="Double model agreement test",
        jev_decision=jev_dec,
        llm_decision=llm_dec,
    )

    assert cmp.is_agreement is True
    assert cmp.speedup_ratio == 4.0
    assert cmp.latency_diff_ms == 960.0
    assert cmp.jev_decision.timing_ms == 320.0
    assert cmp.llm_decision.timing_ms == 1280.0


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_api_config_dual_keys(client, tmp_path, monkeypatch):
    test_env = tmp_path / ".env"
    monkeypatch.setattr("src.jev.web_app._env_path", test_env)

    # Save original environment state
    orig_env = {
        "TYPESAFE_API_KEY": os.environ.get("TYPESAFE_API_KEY"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL"),
        "OPENAI_MODEL": os.environ.get("OPENAI_MODEL"),
    }

    try:
        # Test POST config with both keys
        res = client.post("/api/config", json={
            "api_key": "apikey_typesafe_mock_key_1234567890",
            "llm_api_key": "sk-openai-mock-key-9876543210",
            "llm_base_url": "https://api.test-llm.com/v1",
            "llm_model": "test-model-turbo",
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["configured"] is True
        assert data["llm_configured"] is True

        # Test GET config
        res_get = client.get("/api/config")
        assert res_get.status_code == 200
        get_data = res_get.get_json()
        assert get_data["configured"] is True
        assert get_data["llm_configured"] is True
        assert get_data["llm_model"] == "test-model-turbo"
        assert get_data["llm_base_url"] == "https://api.test-llm.com/v1"
    finally:
        # Restore environment
        for k, v in orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


def test_api_decide_dual_model_response(client, sample_elements):
    session.current_elements = sample_elements
    session.current_task = "在搜索框输入 machine learning"
    session.current_url = "https://www.baidu.com"
    session.current_page_title = "百度一下，你就知道"

    res = client.post("/api/decide", json={
        "task": "在搜索框输入 machine learning",
        "url": "https://www.baidu.com",
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "decision" in data
    assert "llm_decision" in data
    assert "comparison" in data
    assert "timing" in data
    assert "speedup_ratio" in data["comparison"]
    assert "is_agreement" in data["comparison"]
