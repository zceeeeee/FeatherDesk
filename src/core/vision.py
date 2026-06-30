"""
视觉模块 —— 截图 + 页面分析。

[2026-06-30] LLM 多模态调用已暂时禁用（网络超时问题），
当前仅保留截图能力，返回基础页面信息。
待网络环境稳定后可恢复 LLM 分析。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.browser_manager import get_browser_manager

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ElementInfo:
    """视觉识别到的元素信息。"""

    description: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    suggested_selector: str = ""
    confidence: float = 0.0


@dataclass
class PageAnalysis:
    """页面分析结果。"""

    summary: str = ""
    elements: list[ElementInfo] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    raw_response: str = ""


# ---------------------------------------------------------------------------
# 视觉模块
# ---------------------------------------------------------------------------


class VisionModule:
    """截图 + 页面分析。"""

    def __init__(self, provider: str | None = None, api_key: str | None = None) -> None:
        """初始化视觉模块。

        Args:
            provider: LLM 提供商 ('anthropic' 或 'openai')，默认自动检测。
            api_key: API Key，默认从环境变量读取。
        """
        # [DISABLED] LLM 提供商检测已禁用，避免无 API Key 时启动报错
        # self._provider = provider or self._detect_provider()
        # self._api_key = api_key or self._get_api_key()
        self._provider = provider
        self._api_key = api_key

    def analyze_page(self, question: str | None = None) -> PageAnalysis:
        """截图并返回基础页面信息。

        [2026-06-30] LLM 分析已暂时禁用，仅保留截图和基础信息。

        Args:
            question: 可选的针对性问题（当前未使用）。

        Returns:
            PageAnalysis 包含页面基础信息。
        """
        # 1. 截图
        page = get_browser_manager().get_page()

        # 2. 获取基础页面信息（不调用 LLM）
        url = page.url
        title = page.title()

        return PageAnalysis(
            summary=f"{title} ({url})",
            elements=[],
            suggested_actions=[],
            raw_response="",
        )

        # --- 以下为原始 LLM 分析流程，已禁用 ---
        # screenshot_bytes = page.screenshot()
        # b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")
        # prompt = self._build_prompt(question)
        # raw_response = self._call_llm(prompt, b64_image)
        # return self._parse_response(raw_response)

    # def find_element(self, description: str) -> ElementInfo | None:
    #     """用视觉找元素，返回坐标和选择器建议。"""
    #     analysis = self.analyze_page(question=f"找到'{description}'元素的位置和属性")
    #     for elem in analysis.elements:
    #         if description.lower() in elem.description.lower():
    #             return elem
    #     return None
    #
    # def _detect_provider(self) -> str:
    #     """自动检测可用的 LLM 提供商。"""
    #     if os.getenv("ANTHROPIC_API_KEY"):
    #         return "anthropic"
    #     if os.getenv("OPENAI_API_KEY"):
    #         return "openai"
    #     raise ValueError(
    #         "未找到 API Key。请设置 ANTHROPIC_API_KEY 或 OPENAI_API_KEY 环境变量。"
    #     )
    #
    # def _get_api_key(self) -> str:
    #     """获取 API Key。"""
    #     if self._provider == "anthropic":
    #         key = os.getenv("ANTHROPIC_API_KEY", "")
    #     elif self._provider == "openai":
    #         key = os.getenv("OPENAI_API_KEY", "")
    #     else:
    #         key = ""
    #     if not key:
    #         raise ValueError(f"未找到 {self._provider.upper()}_API_KEY 环境变量。")
    #     return key
    #
    # def _build_prompt(self, question: str | None) -> str:
    #     """构造发送给 LLM 的 prompt。"""
    #     base_prompt = """你是一个网页分析专家。请分析这张网页截图，并返回以下信息：
    # 1. **页面概述**: 简要描述页面内容和当前状态
    # 2. **可交互元素**: 列出所有可见的可交互元素（按钮、输入框、链接等），包含：
    #    - 元素描述
    #    - 大致坐标 (x, y)
    #    - 建议的 CSS 选择器
    # 3. **建议操作**: 基于当前页面状态，建议下一步操作
    # 请用以下 JSON 格式返回：
    # ```json
    # {
    #   "summary": "页面概述",
    #   "elements": [
    #     {
    #       "description": "元素描述",
    #       "x": 100, "y": 200, "width": 80, "height": 30,
    #       "suggested_selector": "#button-id",
    #       "confidence": 0.9
    #     }
    #   ],
    #   "suggested_actions": ["建议操作1", "建议操作2"]
    # }
    # ```"""
    #     if question:
    #         base_prompt += f"\n\n**特别关注**: {question}"
    #     return base_prompt
    #
    # def _call_llm(self, prompt: str, b64_image: str) -> str:
    #     """调用多模态 LLM。"""
    #     if self._provider == "anthropic":
    #         return self._call_anthropic(prompt, b64_image)
    #     elif self._provider == "openai":
    #         return self._call_openai(prompt, b64_image)
    #     else:
    #         raise ValueError(f"不支持的 LLM 提供商: {self._provider}")
    #
    # def _call_anthropic(self, prompt: str, b64_image: str) -> str:
    #     """调用 Claude Vision API。"""
    #     import httpx
    #     response = httpx.post(
    #         "https://api.anthropic.com/v1/messages",
    #         headers={
    #             "x-api-key": self._api_key,
    #             "anthropic-version": "2023-06-01",
    #             "content-type": "application/json",
    #         },
    #         json={
    #             "model": "claude-sonnet-4-20250514",
    #             "max_tokens": 4096,
    #             "messages": [{"role": "user", "content": [
    #                 {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64_image}},
    #                 {"type": "text", "text": prompt},
    #             ]}],
    #         },
    #         timeout=60.0,
    #     )
    #     response.raise_for_status()
    #     return response.json()["content"][0]["text"]
    #
    # def _call_openai(self, prompt: str, b64_image: str) -> str:
    #     """调用 GPT-4V API。"""
    #     import httpx
    #     response = httpx.post(
    #         "https://api.openai.com/v1/chat/completions",
    #         headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
    #         json={
    #             "model": "gpt-4o",
    #             "max_tokens": 4096,
    #             "messages": [{"role": "user", "content": [
    #                 {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
    #                 {"type": "text", "text": prompt},
    #             ]}],
    #         },
    #         timeout=60.0,
    #     )
    #     response.raise_for_status()
    #     return response.json()["choices"][0]["message"]["content"]
    #
    # def _parse_response(self, raw_response: str) -> PageAnalysis:
    #     """解析 LLM 返回的 JSON。"""
    #     import json
    #     analysis = PageAnalysis(raw_response=raw_response)
    #     try:
    #         json_start = raw_response.find("{")
    #         json_end = raw_response.rfind("}") + 1
    #         if json_start == -1 or json_end == 0:
    #             analysis.summary = raw_response
    #             return analysis
    #         data = json.loads(raw_response[json_start:json_end])
    #         analysis.summary = data.get("summary", "")
    #         analysis.suggested_actions = data.get("suggested_actions", [])
    #         for elem_data in data.get("elements", []):
    #             elem = ElementInfo(
    #                 description=elem_data.get("description", ""),
    #                 x=elem_data.get("x", 0), y=elem_data.get("y", 0),
    #                 width=elem_data.get("width", 0), height=elem_data.get("height", 0),
    #                 suggested_selector=elem_data.get("suggested_selector", ""),
    #                 confidence=elem_data.get("confidence", 0.0),
    #             )
    #             analysis.elements.append(elem)
    #     except (json.JSONDecodeError, KeyError):
    #         analysis.summary = raw_response
    #     return analysis


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_instance: VisionModule | None = None


def get_vision_module(
    provider: str | None = None,
    api_key: str | None = None,
) -> VisionModule:
    """获取全局单例 VisionModule。"""
    global _instance
    if _instance is None:
        _instance = VisionModule(provider=provider, api_key=api_key)
    return _instance


def reset_vision_module() -> None:
    """重置全局单例（用于测试）。"""
    global _instance
    _instance = None
