"""
任务拆分器 —— 将用户的一句复合指令拆分为多个独立子任务。

拆分策略（两级）：
1. 规则拆分：按中文句号 `。` / 英文句号 `.` 拆分（零成本）
2. LLM 拆分：处理 "然后"、"接着"、"并且" 等连接词（可选）

边界处理：
- URL 中的点号不拆分
- 引号内的句号不拆分
- 省略号不拆分
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class TaskSplitter:
    """将用户输入拆分为多个独立子任务。"""

    # 连接词模式（中文 + 英文）
    _CONNECTOR_PATTERN = re.compile(
        r"(?:然后|接着|随后|再|接下来|之后|并且|同时|另外|"
        r"and then|then|after that|next|also|meanwhile)",
        re.IGNORECASE,
    )

    def __init__(self, llm_caller: Any = None) -> None:
        """
        Args:
            llm_caller: 可选的 LLM 调用器，需提供 .call(prompt) -> str 方法。
                        为 None 时禁用 LLM 拆分，仅用规则。
        """
        self._llm_caller = llm_caller

    def split(self, task: str) -> List[str]:
        """拆分任务，返回子任务列表。

        始终返回至少一个元素。如果无法拆分，返回 [原始任务]。

        Args:
            task: 用户的原始输入。

        Returns:
            子任务列表（去除空串和纯标点）。
        """
        task = task.strip()
        if not task:
            return [task]

        # L1: 规则拆分
        sub_tasks = self._rule_split(task)

        # 规则拆分出多个 → 直接返回
        if len(sub_tasks) > 1:
            logger.info("Rule split: %d sub-tasks", len(sub_tasks))
            return sub_tasks

        # L2: 规则只拆出 1 个 → 尝试连接词拆分
        connector_tasks = self._connector_split(task)
        if len(connector_tasks) > 1:
            logger.info("Connector split: %d sub-tasks", len(connector_tasks))
            return connector_tasks

        # L3: LLM 兜底（可选）
        if self._llm_caller:
            llm_tasks = self._llm_split(task)
            if llm_tasks and len(llm_tasks) > 1:
                logger.info("LLM split: %d sub-tasks", len(llm_tasks))
                return llm_tasks

        # 无法拆分 → 返回原始任务
        return [task]

    # -------------------------------------------------------------------
    # L1: 规则拆分（按句号）
    # -------------------------------------------------------------------

    def _rule_split(self, task: str) -> List[str]:
        """按中文句号 `。` 和英文句号 `.` 拆分，处理边界情况。"""
        # 先保护 URL 中的点号
        protected = self._protect_urls(task)
        # 保护引号内的句号
        protected = self._protect_quoted(protected)

        # 按句号拆分
        parts = re.split(r"[。.]", protected)

        # 还原被保护的内容
        restored = [self._restore(p) for p in parts]

        # 清理：去空串、去纯标点
        cleaned = []
        for part in restored:
            part = part.strip()
            part = self._strip_trailing_punctuation(part)
            if part and not self._is_pure_punctuation(part):
                cleaned.append(part)

        return cleaned

    def _protect_urls(self, text: str) -> str:
        """将 URL 中的点号替换为占位符，避免被拆分。"""
        def replace_url_dot(match: re.Match) -> str:
            return match.group(0).replace(".", "«DOT»")

        return re.sub(
            r"https?://[^\s<>\"'""''「」]+",
            replace_url_dot,
            text,
        )

    def _protect_quoted(self, text: str) -> str:
        """将引号内的句号替换为占位符。"""
        # 用占位符逐步保护引号内容
        result = text

        # 匹配成对引号（贪婪匹配中间内容）
        quote_pairs = [
            ("“", "”"),  # ""
            ("‘", "’"),  # ''
            ("「", "」"),  # 「」
            ('"', '"'),
            ("'", "'"),
        ]

        for open_q, close_q in quote_pairs:
            pattern = re.escape(open_q) + r"(.*?)" + re.escape(close_q)

            def protect_inner(match: re.Match, _o=open_q, _c=close_q) -> str:
                inner = match.group(1).replace(".", "«DOT»").replace("。", "«CDOT»")
                return _o + inner + _c

            result = re.sub(pattern, protect_inner, result, flags=re.DOTALL)

        return result

    @staticmethod
    def _restore(text: str) -> str:
        """还原被保护的点号。"""
        return text.replace("«DOT»", ".").replace("«CDOT»", "。")

    @staticmethod
    def _strip_trailing_punctuation(text: str) -> str:
        """去除末尾的标点符号（但保留引号内的内容）。"""
        return re.sub(r"[，,；;、：:！!？?·\s]+$", "", text)

    @staticmethod
    def _is_pure_punctuation(text: str) -> bool:
        """判断文本是否全是标点或空白。"""
        return bool(re.fullmatch(r"[\s，,。.；;、：:！!？?·\-—…·''\"\"''「」\(\)（）\[\]【】]+", text))

    # -------------------------------------------------------------------
    # L2: 连接词拆分
    # -------------------------------------------------------------------

    def _connector_split(self, task: str) -> List[str]:
        """按连接词（然后、接着、并且 等）拆分。"""
        parts = self._CONNECTOR_PATTERN.split(task)
        cleaned = []
        for part in parts:
            part = part.strip()
            part = self._strip_trailing_punctuation(part)
            if part and not self._is_pure_punctuation(part):
                cleaned.append(part)
        return cleaned

    # -------------------------------------------------------------------
    # L3: LLM 拆分
    # -------------------------------------------------------------------

    def _llm_split(self, task: str) -> Optional[List[str]]:
        """用 LLM 判断是否包含多个意图，返回拆分后的子任务列表。"""
        if not self._llm_caller:
            return None

        prompt = (
            f"用户输入了一句浏览器操作指令。请判断这句指令是否包含多个独立的操作步骤。\n\n"
            f"用户指令: {task}\n\n"
            f"规则:\n"
            f"1. 如果只有一个操作，返回 [原始指令]\n"
            f"2. 如果有多个操作，按顺序拆分为多个子任务\n"
            f"3. 每个子任务应该是完整的、可独立执行的指令\n"
            f"4. 去掉连接词（然后、接着、并且等），只保留操作本身\n\n"
            f"返回 JSON 格式: {{\"tasks\": [\"子任务1\", \"子任务2\", ...]}}"
        )

        schema = {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
            },
            "required": ["tasks"],
        }

        try:
            from src.core.llm_utils import chat_json_with_retry

            data = chat_json_with_retry(
                self._llm_caller._client if hasattr(self._llm_caller, '_client') else self._llm_caller,
                prompt,
                system_prompt="你是一个任务拆分器。将用户的复合指令拆分为独立的子任务。",
                schema=schema,
            )
            tasks = data.get("tasks", [])
            if isinstance(tasks, list) and len(tasks) >= 1:
                return [t.strip() for t in tasks if isinstance(t, str) and t.strip()]
        except Exception as exc:
            logger.warning("LLM task split failed: %s", exc)

        return None


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_instance: TaskSplitter | None = None


def get_task_splitter(llm_caller: Any = None) -> TaskSplitter:
    """获取全局单例 TaskSplitter。"""
    global _instance
    if _instance is None:
        _instance = TaskSplitter(llm_caller=llm_caller)
    return _instance


def reset_task_splitter() -> None:
    """重置全局单例（用于测试）。"""
    global _instance
    _instance = None
