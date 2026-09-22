"""Unit and API tests for Jev Web Application."""

import pytest
from src.jev.web_app import app, session
from src.jev.element_scanner import ScannedElement


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Jev 页面元素决策与耗时监控工作台" in html
    assert "操作耗时全量审计日志" in html
    assert "候选交互元素标号表" in html


def test_api_status(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ready"
    assert "has_api_key" in data
    assert "mode" in data


def test_api_decide_and_history(client):
    # Setup test elements in session
    session.current_elements = [
        ScannedElement(
            ref="e1",
            tag="input",
            role="searchbox",
            placeholder="搜索",
            selector="#search-kw",
        ),
        ScannedElement(
            ref="e2",
            tag="button",
            role="button",
            name="搜索一下",
            selector="#search-btn",
        ),
    ]
    session.current_task = "在搜索框输入 machine learning"
    session.current_url = "https://example.com"

    # Call /api/decide
    res = client.post("/api/decide", json={
        "task": "在搜索框输入 machine learning",
        "url": "https://example.com",
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["decision"]["target_ref"] == "e1"
    assert data["decision"]["action_type"] == "fill"
    assert data["decision"]["input_value"] == "machine learning"
    assert "jev_planning_ms" in data["timing"]
    assert data["timing"]["jev_planning_ms"] >= 0

    # Call /api/history to verify timing tracking
    res_hist = client.get("/api/history")
    assert res_hist.status_code == 200
    hist_data = res_hist.get_json()
    assert hist_data["total_operations"] >= 1
    assert hist_data["total_time_ms"] >= 0
    assert hist_data["counts"]["jev"] >= 1
    latest = hist_data["history"][0]
    assert latest["step"] == "JEV_PLAN"
    assert "timing_ms" in latest
    assert "breakdown" in latest


def test_api_config(client):
    # Test GET config
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.get_json()
    assert "configured" in data
    assert "masked_key" in data

    # Test POST config to set dummy key
    dummy_key = "apikey_1234567890abcdef1234567890abcdef"
    res_set = client.post("/api/config", json={"api_key": dummy_key})
    assert res_set.status_code == 200
    set_data = res_set.get_json()
    assert set_data["success"] is True
    assert set_data["configured"] is True
    assert "..." in set_data["masked_key"]

    # Verify status reflects key
    res_status = client.get("/api/status")
    assert res_status.get_json()["has_api_key"] is True

    # Test POST config with empty to clear key
    res_clear = client.post("/api/config", json={"api_key": ""})
    assert res_clear.status_code == 200
    clear_data = res_clear.get_json()
    assert clear_data["success"] is True
    assert clear_data["configured"] is False
