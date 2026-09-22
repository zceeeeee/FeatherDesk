"""
LLM Decision Planner with Structured Output for Jev Comparison.

Connects to any OpenAI-compatible API (OpenAI, DeepSeek, Qwen, MIMO, OneAPI, etc.)
and outputs structured element decisions to compare performance against TypeSafe Jev System 1.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .element_scanner import ScannedElement


class LLMDecision(BaseModel):
    """Structured decision returned by the general LLM."""
    target_ref: str = Field(description="Selected element ref, e.g. e1, e2 or 'none'")
    target_element: Optional[ScannedElement] = Field(default=None, description="Matched element object")
    action_type: str = Field(description="Atomic action: fill, click, press, hover, scroll, complete")
    input_value: Optional[str] = Field(default=None, description="Value to type if action is fill")
    confidence: float = Field(default=0.0, description="Decision confidence [0.0 - 1.0]")
    rationale: str = Field(default="", description="Reasoning process for the choice")
    model_name: str = Field(default="", description="Model evaluated")
    timing_ms: float = Field(default=0.0, description="Inference latency in milliseconds")
    status: str = Field(default="success", description="success or error message")


_SYSTEM_PROMPT = """You are a precise Web Automation Decision Agent.
Your task is to analyze the user's natural language goal, the current webpage context, and the list of available interactive elements on the page, then decide the single next atomic action to take.

Candidate interactive elements are provided in ARIA notation with unique refs (e.g. e1, e2).
Available atomic actions:
- "fill": type text into a searchbox, textbox or input field.
- "click": click a button, link or clickable element.
- "press": press a keyboard key (like Enter).
- "hover": hover over an element.
- "scroll": scroll the page view.
- "complete": user task is already finished.

IMPORTANT GUIDANCE:
1. If the user wants to search or enter text, find the editable searchbox or textbox, and specify action_type="fill" and the exact string to input in input_value.
2. Search inputs may contain dynamic placeholders or hot search suggestions (e.g. recommendation hints). Do not confuse them with static content.
3. You MUST respond with a valid JSON object strictly matching this schema:
{
  "target_ref": "e1", // or 'none' if no element matches
  "action_type": "fill", // fill, click, press, hover, scroll, complete
  "input_value": "text to type or null",
  "confidence": 0.95, // float between 0.0 and 1.0
  "rationale": "Brief 1-sentence rationale explaining the decision"
}
Output strictly JSON, without markdown fences or extra explanations.
"""


class LLMPlanner:
    """General LLM Planner for side-by-side comparison with Jev."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 25.0,
    ) -> None:
        self.api_key = (
            api_key
            if api_key is not None
            else (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
        )
        self.base_url = (
            base_url
            if base_url is not None
            else (os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        )
        self.model = (
            model
            if model is not None
            else (os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini").strip()
        )
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Whether a valid API key is present."""
        return bool(self.api_key)

    def plan(
        self,
        task: str,
        page_url: str,
        elements: List[ScannedElement],
        page_title: str = "",
    ) -> LLMDecision:
        """
        Execute structured LLM decision planning and record precise inference latency.
        """
        if not self.is_configured:
            # Fallback mock decision if no LLM key configured
            return LLMDecision(
                target_ref="none",
                action_type="complete",
                confidence=0.0,
                rationale="LLM API Key 未配置。请在设置中配置 OPENAI_API_KEY 启用大模型对比。",
                model_name=self.model,
                timing_ms=0.0,
                status="unconfigured",
            )

        element_by_ref = {el.ref: el for el in elements}
        element_lines = [f"[{el.ref}] {el.description}" for el in elements[:25]]
        elements_context = "\n".join(element_lines)

        user_content = f"""Task: {task}
Page URL: {page_url}
Page Title: {page_title}
Total Interactive Elements: {len(elements)}

Candidate Elements:
{elements_context}

Choose the single best element ref and action to advance the user's task. Return JSON:"""

        t_start = time.perf_counter()

        try:
            if hasattr(self, "_client") and self._client is not None:
                client = self._client
            else:
                from openai import OpenAI
                client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout,
                )

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            elapsed_ms = (time.perf_counter() - t_start) * 1000
            raw_text = response.choices[0].message.content or "{}"
            parsed = self._parse_json_safely(raw_text)

            target_ref = parsed.get("target_ref", "none")
            action_type = parsed.get("action_type", "click").lower()
            input_value = parsed.get("input_value")
            confidence = float(parsed.get("confidence", 0.85))
            rationale = parsed.get("rationale", "")

            # If input_value is empty but action is fill, attempt extraction from task
            if action_type == "fill" and not input_value:
                from .jev_client import _extract_fill_value_from_task
                input_value = _extract_fill_value_from_task(task)

            target_el = element_by_ref.get(target_ref)

            return LLMDecision(
                target_ref=target_ref,
                target_element=target_el,
                action_type=action_type,
                input_value=input_value,
                confidence=round(confidence, 2),
                rationale=rationale or f"LLM 结构化决策推断目标为 {target_ref}",
                model_name=self.model,
                timing_ms=round(elapsed_ms, 1),
                status="success",
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t_start) * 1000
            return LLMDecision(
                target_ref="none",
                action_type="error",
                confidence=0.0,
                rationale=f"LLM 推理异常: {str(e)}",
                model_name=self.model,
                timing_ms=round(elapsed_ms, 1),
                status=f"failed: {str(e)}",
            )

    @staticmethod
    def _parse_json_safely(raw_text: str) -> Dict[str, Any]:
        """Strip markdown fences and parse json."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            # Fallback regex extraction
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
            return {}
