"""Screenshot plus multimodal LLM page analysis."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field

from src.core.browser_manager import get_browser_manager


@dataclass
class ElementInfo:
    """Information about an element detected on the page."""

    description: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    suggested_selector: str = ""
    confidence: float = 0.0


@dataclass
class PageAnalysis:
    """Structured page analysis returned by the vision module."""

    summary: str = ""
    elements: list[ElementInfo] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    raw_response: str = ""


class VisionModule:
    """Analyze screenshots with a configured multimodal LLM provider."""

    def __init__(self, provider: str | None = None, api_key: str | None = None) -> None:
        self._provider = provider or self._detect_provider()
        self._api_key = api_key or self._get_api_key()

    def analyze_page(self, question: str | None = None) -> PageAnalysis:
        page = get_browser_manager().get_page()
        screenshot_bytes = page.screenshot()
        b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")
        prompt = self._build_prompt(question)
        raw_response = self._call_llm(prompt, b64_image)
        return self._parse_response(raw_response)

    def find_element(self, description: str) -> ElementInfo | None:
        analysis = self.analyze_page(
            question=f"找到'{description}'元素的位置和属性"
        )
        needle = description.lower()
        for element in analysis.elements:
            if needle in element.description.lower():
                return element
        return None

    def _detect_provider(self) -> str:
        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        raise ValueError(
            "未找到 API Key。请设置 ANTHROPIC_API_KEY 或 OPENAI_API_KEY 环境变量。"
        )

    def _get_api_key(self) -> str:
        if self._provider == "anthropic":
            key = os.getenv("ANTHROPIC_API_KEY", "")
        elif self._provider == "openai":
            key = os.getenv("OPENAI_API_KEY", "")
        else:
            key = ""

        if not key:
            raise ValueError(
                f"未找到 {self._provider.upper()}_API_KEY 环境变量。"
            )
        return key

    def _build_prompt(self, question: str | None) -> str:
        prompt = """你是一个网页分析专家。请分析这张网页截图，并返回以下信息：
1. 页面概述：简要描述页面内容和当前状态。
2. 可交互元素：列出可见的按钮、输入框、链接等，包含元素描述、坐标、尺寸、建议 CSS 选择器和置信度。
3. 建议操作：基于当前页面状态，建议下一步操作。

请只返回 JSON，格式如下：
{
  "summary": "页面概述",
  "elements": [
    {
      "description": "元素描述",
      "x": 100,
      "y": 200,
      "width": 80,
      "height": 30,
      "suggested_selector": "#button-id",
      "confidence": 0.9
    }
  ],
  "suggested_actions": ["建议操作1", "建议操作2"]
}
"""
        if question:
            prompt += f"\n特别关注：{question}"
        return prompt

    def _call_llm(self, prompt: str, b64_image: str) -> str:
        if self._provider == "anthropic":
            return self._call_anthropic(prompt, b64_image)
        if self._provider == "openai":
            return self._call_openai(prompt, b64_image)
        raise ValueError(f"不支持的 LLM 提供商: {self._provider}")

    def _call_anthropic(self, prompt: str, b64_image: str) -> str:
        import httpx

        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64_image,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]

    def _call_openai(self, prompt: str, b64_image: str) -> str:
        import httpx

        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64_image}"
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _parse_response(self, raw_response: str) -> PageAnalysis:
        analysis = PageAnalysis(raw_response=raw_response)
        try:
            json_start = raw_response.find("{")
            json_end = raw_response.rfind("}") + 1
            if json_start == -1 or json_end <= json_start:
                analysis.summary = raw_response
                return analysis

            data = json.loads(raw_response[json_start:json_end])
            analysis.summary = data.get("summary", "")
            analysis.suggested_actions = data.get("suggested_actions", [])
            for item in data.get("elements", []):
                analysis.elements.append(
                    ElementInfo(
                        description=item.get("description", ""),
                        x=item.get("x", 0),
                        y=item.get("y", 0),
                        width=item.get("width", 0),
                        height=item.get("height", 0),
                        suggested_selector=item.get("suggested_selector", ""),
                        confidence=item.get("confidence", 0.0),
                    )
                )
        except (json.JSONDecodeError, TypeError, AttributeError):
            analysis.summary = raw_response
        return analysis


_instance: VisionModule | None = None


def get_vision_module(
    provider: str | None = None,
    api_key: str | None = None,
) -> VisionModule:
    """Return the process-wide VisionModule instance."""
    global _instance
    if _instance is None:
        _instance = VisionModule(provider=provider, api_key=api_key)
    return _instance


def reset_vision_module() -> None:
    """Reset the process-wide VisionModule instance."""
    global _instance
    _instance = None
