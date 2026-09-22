"""
Jev System 1 Decision Client for Element & Action Planning.

Connects to the TypeSafe AI Jev System 1 API (or runs intelligent local heuristic fallback
when TYPESAFE_API_KEY is not configured) to choose the best candidate element and atomic action.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .element_scanner import ScannedElement


class JevDecision(BaseModel):
    """The structured decision returned by Jev for the current step."""
    target_ref: str = Field(description="Selected element ref, e.g. e1, e2 or 'none'")
    target_element: Optional[ScannedElement] = Field(default=None, description="The matched ScannedElement object")
    action_type: str = Field(description="Atomic action type: fill, click, press, hover, scroll, complete")
    input_value: Optional[str] = Field(default=None, description="Value to input if action_type is fill")
    confidence: float = Field(default=0.0, description="Decision confidence score [0.0 - 1.0]")
    probabilities: Dict[str, float] = Field(default_factory=dict, description="Probability distribution across candidates")
    is_goal_achieved: bool = Field(default=False, description="Whether the user goal is already fulfilled")
    mode: str = Field(default="cloud_api", description="Execution mode: 'cloud_api' or 'heuristic_fallback'")
    model_name: str = Field(default="jev-latest", description="Model name evaluated")
    rationale: str = Field(default="", description="Reasoning or description of the decision")


def _extract_fill_value_from_task(task: str) -> Optional[str]:
    """Helper to extract intended input text from natural language task."""
    patterns = [
        r'(?:输入|填入|填写|键入|录入|搜索|type|fill|search\s*for)\s*["“\']([^"”\']+)["”\']',
        r'(?:在.+?[中里]?\s*)?(?:输入|填入|填写|键入|录入)\s*(.+?)(?:\s*并|\s*后|\s*，|\s*,|\s*$|\s+点击)',
        r'(?:搜索|search\s*for)\s*(.+?)(?:\s*并|\s*后|\s*，|\s*,|\s*$|\s+点击)',
        r'type\s*["\']?([^"\']+)["\']?',
        r'fill\s*["\']?([^"\']+)["\']?',
    ]
    for p in patterns:
        m = re.search(p, task, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val and val not in ("框", "内容", "文字", "信息", "用户", "密码", "账号"):
                return val
    return None


class JevPlanner:
    """Jev Planner for rapid element selection and primitive action prediction."""

    def __init__(self, api_key: Optional[str] = None, model: str = "jev-latest") -> None:
        self.api_key = os.getenv("TYPESAFE_API_KEY", "").strip() if api_key is None else api_key.strip()
        self.model = model

    def plan(
        self,
        task: str,
        page_url: str,
        page_title: str,
        elements: List[ScannedElement],
    ) -> JevDecision:
        """
        Synchronously plan the next element and action.
        If TYPESAFE_API_KEY is valid, queries TypeSafe Jev API.
        Otherwise falls back to high-fidelity local heuristic mode.
        """
        if self.api_key:
            try:
                return self._call_typesafe_api(task, page_url, page_title, elements)
            except Exception as e:
                # Log fallback and proceed with heuristic
                fallback_decision = self._heuristic_plan(task, page_url, page_title, elements)
                fallback_decision.rationale = f"[API Fallback due to: {e}] " + fallback_decision.rationale
                return fallback_decision
        else:
            return self._heuristic_plan(task, page_url, page_title, elements)

    def _call_typesafe_api(
        self,
        task: str,
        page_url: str,
        page_title: str,
        elements: List[ScannedElement],
    ) -> JevDecision:
        """Make live request to TypeSafe Jev API."""
        from typesafe_sdk import Choice, Noul, TypeSafeClient

        # Prioritize candidates relevant to the user intent (input/search vs click)
        task_lower = task.lower()
        is_fill_intent = any(w in task_lower for w in ["输入", "搜索", "填", "type", "search", "fill", "query"])

        def _candidate_relevance(el: ScannedElement) -> int:
            rel = 0
            if is_fill_intent:
                if el.role == "searchbox":
                    rel += 100
                elif el.role == "textbox" or el.tag in ("input", "textarea"):
                    rel += 80
                elif el.role == "button" and any(k in (el.name + " " + el.selector).lower() for k in ("搜索", "search", "百度一下", "submit", "查询")):
                    rel += 50
                elif el.role == "button":
                    rel += 10
                elif el.role == "link":
                    rel += 1
            else:
                if el.role in ("button", "link"):
                    rel += 30
                    for kw in task_lower.split():
                        if len(kw) >= 2 and kw in el.name.lower():
                            rel += 40
                elif el.role in ("searchbox", "textbox"):
                    rel += 10
            return rel

        # Sort elements by task relevance to ensure high-priority candidates are evaluated first
        ranked_elements = sorted(elements, key=_candidate_relevance, reverse=True)
        # Select top 16 candidates to keep LLM response time under 2-3s and eliminate timeouts
        selected_candidates = ranked_elements[:16]

        criteria_map: Dict[str, Optional[str]] = {}
        element_by_ref: Dict[str, ScannedElement] = {}
        for el in selected_candidates:
            criteria_map[el.ref] = el.description
            element_by_ref[el.ref] = el
        criteria_map["none"] = "None of the elements match the required task"

        action_criteria = {
            "fill": "Type text into searchbox or textbox",
            "click": "Click on button, link, or clickable element",
            "press": "Press keyboard key like Enter",
            "hover": "Hover mouse over element",
            "scroll": "Scroll page view up or down",
            "complete": "Goal is already complete, no action needed",
        }

        with TypeSafeClient(api_key=self.api_key, timeout=15.0) as client:
            response = client.system_one(
                model=self.model,
                state={
                    "user_task": task,
                    "page_url": page_url,
                    "page_title": page_title,
                    "elements_count": len(elements),
                },
                questions={
                    "target_element": Choice(
                        instructions=(
                            "Which element should be operated on to achieve the user task? "
                            "Note: Search inputs or textareas may contain dynamic recommendation placeholders or hints. "
                            "If the task requires typing or searching, select the editable search/text input field."
                        ),
                        criteria=criteria_map,
                    ),
                    "action_type": Choice(
                        instructions="What atomic action should be executed on the chosen element?",
                        criteria=action_criteria,
                    ),
                    "is_goal_complete": Noul(
                        instructions="Is the user task already fulfilled on the current page?",
                    ),
                },
            )

        chosen_ref = response.answers["target_element"].choice
        chosen_action = response.answers["action_type"].choice
        confidence = response.answers["target_element"].confidence
        probs = response.answers["target_element"].probabilities or {}
        is_done = response.answers["is_goal_complete"].noul > 0.85

        input_val = None
        if chosen_action == "fill":
            input_val = _extract_fill_value_from_task(task)

        target_el = element_by_ref.get(chosen_ref)

        return JevDecision(
            target_ref=chosen_ref,
            target_element=target_el,
            action_type=chosen_action,
            input_value=input_val,
            confidence=round(confidence, 3),
            probabilities={k: round(v, 4) for k, v in probs.items() if v > 0.01},
            is_goal_achieved=is_done,
            mode="cloud_api",
            model_name=self.model,
            rationale=f"Jev System 1 evaluation: selected {chosen_ref} ({chosen_action}) with confidence {confidence:.2f}",
        )

    def _heuristic_plan(
        self,
        task: str,
        page_url: str,
        page_title: str,
        elements: List[ScannedElement],
    ) -> JevDecision:
        """
        High-fidelity local heuristic decision engine.
        Acts as offline mock when TYPESAFE_API_KEY is absent.
        """
        task_lower = task.lower()
        extracted_val = _extract_fill_value_from_task(task)

        # 1. Check if user intends to input / search first
        needs_fill = any(w in task for w in ["输入", "搜索", "填", "type", "search", "fill", "query"])
        needs_click = any(w in task for w in ["点击", "按", "click", "打开", "选择"])
        
        chosen_el: Optional[ScannedElement] = None
        chosen_action: str = "click"
        confidence: float = 0.92

        if needs_fill and extracted_val:
            best_input_score = -1
            for el in elements:
                if el.role in ("searchbox", "textbox") or el.tag in ("input", "textarea"):
                    score = 1
                    el_meta = (el.name + " " + el.placeholder + " " + el.selector + " " + el.role).lower()
                    if ("用户" in task_lower or "user" in task_lower or "login" in task_lower or "账号" in task_lower) and \
                       any(k in el_meta for k in ("login", "user", "email", "account", "name")):
                        score += 10
                    elif ("密码" in task_lower or "password" in task_lower or "pwd" in task_lower) and \
                         any(k in el_meta for k in ("pass", "pwd")):
                        score += 10
                    elif ("搜索" in task_lower or "search" in task_lower or "kw" in task_lower) and \
                          (el.role == "searchbox" or any(k in el_meta for k in ("search", "kw", "query", "chat", "q"))):
                        score += 15
                    elif el.role == "searchbox":
                        score += 10
                    if score > best_input_score:
                        best_input_score = score
                        chosen_el = el
                        chosen_action = "fill"

        if not chosen_el:
            # Score elements by keyword similarity
            best_score = -1
            for el in elements:
                score = 0
                el_text = (el.name + " " + el.placeholder + " " + el.selector).lower()
                for kw in ["搜索", "确定", "提交", "登录", "search", "submit", "login", "百度一下", "sign in", "log in"]:
                    if kw in task_lower and kw in el_text:
                        score += 5
                if el.role in ("button", "link"):
                    score += 2
                if score > best_score:
                    best_score = score
                    chosen_el = el
            if chosen_el:
                chosen_action = "click"
                confidence = 0.88

        # Fallback to first interactive element if none scored
        if not chosen_el and elements:
            chosen_el = elements[0]
            chosen_action = "click"
            confidence = 0.65

        target_ref = chosen_el.ref if chosen_el else "none"

        probs = {target_ref: confidence}
        if len(elements) > 1:
            remaining = round(1.0 - confidence, 3)
            probs["other"] = remaining

        return JevDecision(
            target_ref=target_ref,
            target_element=chosen_el,
            action_type=chosen_action,
            input_value=extracted_val if chosen_action == "fill" else None,
            confidence=confidence,
            probabilities=probs,
            is_goal_achieved=False,
            mode="heuristic_fallback",
            model_name="jev-local-mock (Set TYPESAFE_API_KEY for cloud Jev)",
            rationale=f"Heuristic decision: Matched task requirements to {target_ref} with action '{chosen_action}'",
        )
