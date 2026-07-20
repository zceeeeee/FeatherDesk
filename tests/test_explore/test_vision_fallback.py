"""Tests for guarded Explore visual fallback behavior."""

from src.core.explore.executor import ExploreExecutor
from src.core.explore.models import (
    Action,
    ActionBatch,
    ErrorCode,
    ExploreConfig,
    ScreenshotMeta,
    SnapshotMode,
    SnapshotResponse,
    VisualTarget,
)
from src.core.explore.vision_router import VisionRouter
from src.core.llm_client import LLMClient, LLMConfig


class FakeMouse:
    def __init__(self):
        self.calls = []

    def click(self, x, y):
        self.calls.append(("click", x, y))

    def move(self, x, y):
        self.calls.append(("move", x, y))


class FakePage:
    url = "https://example.com/app"

    def __init__(self):
        self.mouse = FakeMouse()

    def evaluate(self, _code):
        return {"width": 1000, "height": 500, "scrollX": 0, "scrollY": 0}


def _visual_snapshot(description="Open menu"):
    return SnapshotResponse(
        version="snapshot_v2",
        mode=SnapshotMode.COMPACT,
        url="https://example.com/app",
        visual_targets=[
            VisualTarget(
                ref="v1",
                description=description,
                role="button",
                x=0.10,
                y=0.20,
                width=0.20,
                height=0.10,
                confidence=0.95,
            )
        ],
        screenshot_meta=ScreenshotMeta(
            url="https://example.com/app",
            viewport_width=1000,
            viewport_height=500,
        ),
    )


def test_visual_ref_click_is_converted_to_css_viewport_center():
    page = FakePage()
    executor = ExploreExecutor(page, config=ExploreConfig())
    executor.update_snapshot(_visual_snapshot())

    result = executor.execute(
        ActionBatch(
            actions=[Action(action="click", ref="v1", snapshot_v="snapshot_v2")]
        )
    )

    assert result.success is True
    assert page.mouse.calls == [("click", 200, 125)]


def test_visual_ref_hover_uses_mouse_move():
    page = FakePage()
    executor = ExploreExecutor(page, config=ExploreConfig())
    executor.update_snapshot(_visual_snapshot())

    result = executor.execute(ActionBatch(actions=[Action(action="hover", ref="v1")]))

    assert result.success is True
    assert page.mouse.calls == [("move", 200, 125)]


def test_sensitive_visual_click_is_blocked():
    page = FakePage()
    executor = ExploreExecutor(page, config=ExploreConfig())
    executor.update_snapshot(_visual_snapshot("确认支付"))

    result = executor.execute(ActionBatch(actions=[Action(action="click", ref="v1")]))

    assert result.success is False
    assert result.error_code == ErrorCode.ELEMENT_NOT_INTERACTABLE
    assert page.mouse.calls == []


def test_visual_coordinates_are_rejected_after_navigation():
    page = FakePage()
    page.url = "https://example.com/other"
    executor = ExploreExecutor(page, config=ExploreConfig())
    executor.update_snapshot(_visual_snapshot())

    result = executor.execute(ActionBatch(actions=[Action(action="click", ref="v1")]))

    assert result.success is False
    assert result.error_code == ErrorCode.SNAPSHOT_STALE


def test_vision_gate_requires_explicit_enablement():
    client = LLMClient(LLMConfig(api_key="test", model="gpt-4o"))
    assert VisionRouter(ExploreConfig(), client).available is False
    assert VisionRouter(ExploreConfig(vision_enabled=True), client).available is True


def test_mimo_text_model_is_not_inferred_as_visual(monkeypatch):
    monkeypatch.delenv("LLM_SUPPORTS_VISION", raising=False)
    client = LLMClient(LLMConfig(api_key="test", model="mimo-v2.5-pro"))
    assert client.supports_vision is False
