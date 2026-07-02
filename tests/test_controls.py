"""Tests for layer_2.controls — high-level browser control functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.layer_2.controls import (
    get_controls_exports,
    get_page_text,
    get_page_title,
    get_page_url,
    go_back,
    go_forward,
    goto,
    mouse_click,
    reload_page,
    screenshot,
    smart_click,
    smart_fill,
    smart_fill_form,
    smart_login,
    smart_search,
    upload_file,
    wait,
    wait_for_element,
    wait_for_navigation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bm():
    """Mock BrowserManager with a mock page."""
    with patch("src.layer_2.controls.get_browser_manager") as mock_get_bm:
        bm = MagicMock()
        page = MagicMock()
        page.url = "https://example.com"
        page.title.return_value = "Example"
        page.evaluate.return_value = "Page text content"
        page.is_visible.return_value = True
        page.click.return_value = None
        page.fill.return_value = None
        page.goto.return_value = MagicMock(status=200)
        page.go_back.return_value = None
        page.go_forward.return_value = None
        page.reload.return_value = None
        page.wait_for_load_state.return_value = None
        page.wait_for_selector.return_value = None
        page.screenshot.return_value = None
        bm.get_page.return_value = page
        mock_get_bm.return_value = bm
        yield bm, page


@pytest.fixture
def sample_yaml_dir(tmp_path):
    """Write a sample domain YAML for testing."""
    import yaml

    data = {
        "name": "test_site",
        "base_url": "https://example.com",
        "locators": {
            "username": {
                "css": ["#user", "input[name='username']"],
            },
            "password": {
                "css": ["#pass", "input[name='password']"],
            },
            "submit": {
                "css": ["#submit", "button[type='submit']"],
            },
            "search_input": {
                "css": ["#search", "input[name='q']"],
            },
            "search_button": {
                "css": ["#search-btn", "button.search"],
            },
        },
    }
    path = tmp_path / "test_site.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return str(tmp_path)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


class TestNavigation:
    def test_goto(self, mock_bm):
        result = goto("https://example.com")
        assert "成功" in result or "example.com" in result

    def test_go_back(self, mock_bm):
        result = go_back()
        assert "后退" in result

    def test_go_forward(self, mock_bm):
        result = go_forward()
        assert "前进" in result

    def test_reload(self, mock_bm):
        result = reload_page()
        assert "刷新" in result

    def test_mouse_click(self, mock_bm):
        _bm, page = mock_bm
        result = mouse_click(12, 34)
        assert result["success"] is True
        assert result["x"] == 12
        assert result["y"] == 34
        page.mouse.click.assert_called_once_with(12.0, 34.0)

    def test_upload_file(self, mock_bm, tmp_path):
        _bm, page = mock_bm
        image = tmp_path / "note.jpg"
        image.write_bytes(b"fake image")

        result = upload_file("input[type='file']", str(image))

        assert result["success"] is True
        assert result["selector"] == "input[type='file']"
        page.set_input_files.assert_called_once_with(
            "input[type='file']",
            str(image.resolve()),
        )


# ---------------------------------------------------------------------------
# smart_click / smart_fill
# ---------------------------------------------------------------------------


class TestSmartClick:
    @patch("src.layer_2.controls._DOMAINS_DIR", "/tmp/domains")
    @patch("src.layer_2.controls.load_domain")
    @patch("src.layer_2.controls.get_element_selectors")
    def test_success(self, mock_get_sels, mock_load, mock_bm):
        from src.layer_3.domain_loader import DomainConfig

        mock_load.return_value = DomainConfig(
            name="test", locators={"btn": {"css": ["#btn"]}}
        )
        mock_get_sels.return_value = ["#btn"]
        bm, page = mock_bm
        page.is_visible.return_value = True

        result = smart_click("btn", domain="test")
        assert result["success"] is True
        assert result["used_selector"] == "#btn"

    @patch("src.layer_2.controls._DOMAINS_DIR", "/tmp/domains")
    @patch("src.layer_2.controls.load_domain")
    def test_domain_not_found(self, mock_load, mock_bm):
        mock_load.side_effect = FileNotFoundError("not found")
        result = smart_click("btn", domain="missing")
        assert result["success"] is False
        assert "加载失败" in result["error"]


class TestSmartFill:
    @patch("src.layer_2.controls._DOMAINS_DIR", "/tmp/domains")
    @patch("src.layer_2.controls.load_domain")
    @patch("src.layer_2.controls.get_element_selectors")
    def test_success(self, mock_get_sels, mock_load, mock_bm):
        from src.layer_3.domain_loader import DomainConfig

        mock_load.return_value = DomainConfig(
            name="test", locators={"input": {"css": ["#input"]}}
        )
        mock_get_sels.return_value = ["#input"]
        bm, page = mock_bm
        page.is_visible.return_value = True

        result = smart_fill("input", "hello", domain="test")
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Composite operations
# ---------------------------------------------------------------------------


class TestSmartLogin:
    @patch("src.layer_2.controls._DOMAINS_DIR")
    @patch("src.layer_2.controls.load_domain")
    @patch("src.layer_2.controls.get_element_selectors")
    def test_success_flow(self, mock_get_sels, mock_load, mock_dir, mock_bm):
        from src.layer_3.domain_loader import DomainConfig

        mock_dir.__str__ = lambda self: "/tmp"
        mock_load.return_value = DomainConfig(
            name="test",
            base_url="https://example.com",
            locators={
                "username": {"css": ["#user"]},
                "password": {"css": ["#pass"]},
                "submit": {"css": ["#submit"]},
            },
        )

        # Return different selectors based on element name
        def get_sels(config, name):
            return config.locators[name].css

        mock_get_sels.side_effect = get_sels
        bm, page = mock_bm
        page.is_visible.return_value = True

        result = smart_login("test", "admin", "1234")
        assert result["success"] is True
        # 6 steps: navigate, fill_username, fill_password, click_submit,
        #          wait_navigation, save_cookies
        assert len(result["steps"]) == 6

    @patch("src.layer_2.controls._DOMAINS_DIR")
    @patch("src.layer_2.controls.load_domain")
    def test_domain_not_found(self, mock_load, mock_dir, mock_bm):
        mock_load.side_effect = FileNotFoundError("not found")
        result = smart_login("missing", "admin", "1234")
        assert result["success"] is False


class TestSmartSearch:
    @patch("src.layer_2.controls._DOMAINS_DIR")
    @patch("src.layer_2.controls.load_domain")
    @patch("src.layer_2.controls.get_element_selectors")
    def test_success_flow(self, mock_get_sels, mock_load, mock_dir, mock_bm):
        from src.layer_3.domain_loader import DomainConfig

        mock_load.return_value = DomainConfig(
            name="test",
            base_url="https://example.com",
            locators={
                "search_input": {"css": ["#q"]},
                "search_button": {"css": ["#btn"]},
            },
        )

        def get_sels(config, name):
            return config.locators[name].css

        mock_get_sels.side_effect = get_sels
        bm, page = mock_bm
        page.is_visible.return_value = True

        result = smart_search("test", "python")
        assert result["success"] is True
        assert len(result["steps"]) == 4


class TestSmartFillForm:
    @patch("src.layer_2.controls._DOMAINS_DIR")
    @patch("src.layer_2.controls.load_domain")
    @patch("src.layer_2.controls.get_element_selectors")
    def test_success(self, mock_get_sels, mock_load, mock_dir, mock_bm):
        from src.layer_3.domain_loader import DomainConfig

        mock_load.return_value = DomainConfig(
            name="test",
            locators={
                "username": {"css": ["#user"]},
                "password": {"css": ["#pass"]},
            },
        )

        def get_sels(config, name):
            return config.locators[name].css

        mock_get_sels.side_effect = get_sels
        bm, page = mock_bm
        page.is_visible.return_value = True

        result = smart_fill_form("test", {"username": "admin", "password": "1234"})
        assert result["success"] is True
        assert "username" in result["results"]
        assert "password" in result["results"]


# ---------------------------------------------------------------------------
# Wait functions
# ---------------------------------------------------------------------------


class TestWait:
    def test_wait_for_navigation(self, mock_bm):
        result = wait_for_navigation(timeout=5)
        assert "完成" in result or "加载" in result

    def test_wait_for_element(self, mock_bm):
        result = wait_for_element("#btn", timeout=5)
        assert "已出现" in result

    @patch("src.layer_2.controls.time.sleep")
    def test_wait(self, mock_sleep):
        result = wait(2.0)
        assert "2.0" in result


# ---------------------------------------------------------------------------
# Page info
# ---------------------------------------------------------------------------


class TestPageInfo:
    def test_get_url(self, mock_bm):
        assert get_page_url() == "https://example.com"

    def test_get_title(self, mock_bm):
        assert get_page_title() == "Example"

    def test_get_text(self, mock_bm):
        assert get_page_text() == "Page text content"

    def test_screenshot(self, mock_bm):
        result = screenshot("test.png")
        assert result == "test.png"


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


class TestExports:
    def test_get_controls_exports(self):
        exports = get_controls_exports()
        assert "goto" in exports
        assert "smart_click" in exports
        assert "smart_fill" in exports
        assert "smart_login" in exports
        assert "smart_search" in exports
        assert "smart_fill_form" in exports
        assert "wait_for_navigation" in exports
        assert "wait_for_element" in exports
        assert "wait" in exports
        assert "get_url" in exports
        assert "get_title" in exports
        assert "get_text" in exports
        assert "screenshot" in exports
        assert "mouse_click" in exports
        assert "type_text" in exports
        assert "press_key" in exports
        assert "upload_file" in exports
        assert len(exports) >= 15
