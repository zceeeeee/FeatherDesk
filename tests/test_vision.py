"""Tests for core.vision — screenshot + multimodal LLM page analysis."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.vision import (
    ElementInfo,
    PageAnalysis,
    VisionModule,
    get_vision_module,
    reset_vision_module,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_page():
    """Mock Playwright page that returns screenshot bytes."""
    with patch("src.core.vision.get_browser_manager") as mock_get_bm:
        bm = MagicMock()
        page = MagicMock()
        # 1x1 red PNG
        page.screenshot.return_value = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
            b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
            b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        bm.get_page.return_value = page
        mock_get_bm.return_value = bm
        yield page


@pytest.fixture
def sample_analysis_json():
    return json.dumps(
        {
            "summary": "这是一个登录页面",
            "elements": [
                {
                    "description": "用户名输入框",
                    "x": 100,
                    "y": 200,
                    "width": 200,
                    "height": 30,
                    "suggested_selector": "#username",
                    "confidence": 0.95,
                },
                {
                    "description": "登录按钮",
                    "x": 100,
                    "y": 300,
                    "width": 80,
                    "height": 35,
                    "suggested_selector": "#login-btn",
                    "confidence": 0.9,
                },
            ],
            "suggested_actions": ["填写用户名和密码", "点击登录按钮"],
        }
    )


@pytest.fixture
def vision_with_mock_llm(sample_analysis_json):
    """Create a VisionModule with mocked LLM response."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        vm = VisionModule(provider="anthropic", api_key="test-key")
        vm._call_llm = MagicMock(return_value=sample_analysis_json)
        return vm


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_element_info_defaults(self):
        elem = ElementInfo()
        assert elem.description == ""
        assert elem.x == 0
        assert elem.y == 0
        assert elem.confidence == 0.0

    def test_page_analysis_defaults(self):
        analysis = PageAnalysis()
        assert analysis.summary == ""
        assert analysis.elements == []
        assert analysis.suggested_actions == []


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------


class TestProviderDetection:
    def test_detect_anthropic(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}, clear=True):
            vm = VisionModule(api_key="key")
            assert vm._provider == "anthropic"

    def test_detect_openai(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True):
            # Remove anthropic key if set
            import os

            os.environ.pop("ANTHROPIC_API_KEY", None)
            vm = VisionModule(api_key="key")
            assert vm._provider == "openai"

    def test_no_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            import os

            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            with pytest.raises(ValueError, match="未找到"):
                VisionModule()

    def test_vision_env_overrides_model_and_base_url(self):
        with patch.dict(
            "os.environ",
            {
                "VISION_PROVIDER": "mimo",
                "VISION_API_KEY": "vision-key",
                "VISION_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
                "VISION_MODEL": "mimo-v2.5",
            },
            clear=True,
        ):
            vm = VisionModule()

        assert vm._provider == "mimo"
        assert vm._api_key == "vision-key"
        assert vm._base_url == "https://token-plan-cn.xiaomimimo.com/v1"
        assert vm._model == "mimo-v2.5"

    def test_openai_compatible_vision_reuses_llm_model_when_no_vision_model(self):
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "openai-key",
                "OPENAI_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
                "OPENAI_MODEL": "mimo-v2.5",
            },
            clear=True,
        ):
            vm = VisionModule()

        assert vm._provider == "openai"
        assert vm._base_url == "https://token-plan-cn.xiaomimimo.com/v1"
        assert vm._model == "mimo-v2.5"

    def test_openai_compatible_call_uses_configured_endpoint_and_model(self):
        with patch.dict(
            "os.environ",
            {
                "VISION_PROVIDER": "mimo",
                "VISION_API_KEY": "vision-key",
                "VISION_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
                "VISION_MODEL": "mimo-v2.5",
            },
            clear=True,
        ):
            vm = VisionModule()

        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"summary": "ok"}'}}]
        }
        with patch("httpx.post", return_value=response) as mock_post:
            assert vm._call_openai("prompt", "image") == '{"summary": "ok"}'

        url = mock_post.call_args.args[0]
        payload = mock_post.call_args.kwargs["json"]
        assert url == "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
        assert payload["model"] == "mimo-v2.5"


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


class TestPromptBuilding:
    def test_base_prompt(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
            vm = VisionModule(api_key="key")
            prompt = vm._build_prompt(None)
            assert "JSON" in prompt
            assert "elements" in prompt

    def test_prompt_with_question(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
            vm = VisionModule(api_key="key")
            prompt = vm._build_prompt("登录按钮在哪里？")
            assert "登录按钮在哪里？" in prompt


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


class TestResponseParsing:
    def test_parse_valid_json(self, vision_with_mock_llm, sample_analysis_json):
        analysis = vision_with_mock_llm._parse_response(sample_analysis_json)
        assert analysis.summary == "这是一个登录页面"
        assert len(analysis.elements) == 2
        assert analysis.elements[0].description == "用户名输入框"
        assert analysis.elements[0].x == 100
        assert analysis.elements[0].confidence == 0.95
        assert len(analysis.suggested_actions) == 2

    def test_parse_json_in_markdown(self, vision_with_mock_llm):
        raw = 'Here is the analysis:\n```json\n{"summary": "test"}\n```\nDone.'
        analysis = vision_with_mock_llm._parse_response(raw)
        assert analysis.summary == "test"

    def test_parse_invalid_json(self, vision_with_mock_llm):
        raw = "This is not JSON at all."
        analysis = vision_with_mock_llm._parse_response(raw)
        assert analysis.summary == raw

    def test_parse_partial_json(self, vision_with_mock_llm):
        raw = '{"summary": "partial", "elements": []}'
        analysis = vision_with_mock_llm._parse_response(raw)
        assert analysis.summary == "partial"
        assert analysis.elements == []


# ---------------------------------------------------------------------------
# analyze_page
# ---------------------------------------------------------------------------


class TestAnalyzePage:
    def test_analyze_page_success(self, vision_with_mock_llm, mock_page):
        analysis = vision_with_mock_llm.analyze_page()
        assert analysis.summary == "这是一个登录页面"
        assert len(analysis.elements) == 2
        mock_page.screenshot.assert_called_once()

    def test_analyze_page_with_question(self, vision_with_mock_llm, mock_page):
        analysis = vision_with_mock_llm.analyze_page(question="找登录按钮")
        assert analysis.summary == "这是一个登录页面"


# ---------------------------------------------------------------------------
# find_element
# ---------------------------------------------------------------------------


class TestFindElement:
    def test_find_existing_element(self, vision_with_mock_llm, mock_page):
        elem = vision_with_mock_llm.find_element("登录按钮")
        assert elem is not None
        assert "登录按钮" in elem.description
        assert elem.suggested_selector == "#login-btn"

    def test_find_nonexistent_element(self, vision_with_mock_llm, mock_page):
        elem = vision_with_mock_llm.find_element("不存在的元素")
        assert elem is None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def teardown_method(self):
        reset_vision_module()

    def test_singleton(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
            v1 = get_vision_module(api_key="key")
            v2 = get_vision_module()
            assert v1 is v2

    def test_reset(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
            v1 = get_vision_module(api_key="key")
            reset_vision_module()
            v2 = get_vision_module(api_key="key")
            assert v1 is not v2
