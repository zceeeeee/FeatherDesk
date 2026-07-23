"""Tests for the Taobao product search skill adapter."""

from __future__ import annotations

from pathlib import Path

from src.core.script_engine import ScriptEngine


def test_taobao_skill_opens_login_before_search_and_returns_structured_result():
    urls = []
    logs = []
    engine = ScriptEngine()
    engine.register_functions(
        {
            "goto": lambda url: urls.append(url) or "ok",
            "wait": lambda seconds: None,
            "url_quote": lambda value: value.replace(" ", "+"),
            "taobao_collect_products": lambda keyword, max_items=20: {
                "keyword": keyword,
                "products": [],
            },
            "log": lambda message: logs.append(message),
        }
    )
    source = Path("src/skill_library/search/taobao_search.py").read_text(
        encoding="utf-8"
    )

    result = engine.execute(source + '\nresult = run("蓝牙 耳机")\n')

    assert result.success is True
    assert urls == [
        "https://login.taobao.com/member/login.jhtml",
        "https://s.taobao.com/search?q=蓝牙+耳机",
    ]
    assert result.return_value == {"keyword": "蓝牙 耳机", "products": []}
    assert any("蓝牙 耳机" in message for message in logs)


def test_taobao_skill_contract_describes_three_images_and_five_detail_rows():
    source = Path("src/skill_library/search/taobao_search.py").read_text(
        encoding="utf-8"
    )
    metadata = Path("skills/search/taobao_search.yaml").read_text(encoding="utf-8")

    assert "first three product images and five product detail rows" in source
    assert "前三张图片、前五个商品明细" in metadata
    assert metadata.index("https://login.taobao.com/member/login.jhtml") < (
        metadata.index("https://s.taobao.com/search")
    )


def test_taobao_skill_waits_for_confirmed_login_before_collecting_products(
    monkeypatch,
):
    events: list[str] = []
    now = [100.0]
    monkeypatch.setattr("src.core.login_guard.time.monotonic", lambda: now[0])

    class FakeContext:
        def __init__(self):
            self.logged_in = False

        def storage_state(self):
            cookies = []
            if self.logged_in:
                cookies = [
                    {
                        "name": "tracknick",
                        "value": "buyer",
                        "domain": ".taobao.com",
                    },
                    {
                        "name": "cookie2",
                        "value": "session",
                        "domain": ".taobao.com",
                    },
                ]
            return {"cookies": cookies, "origins": []}

    class FakePage:
        def __init__(self, context):
            self.context = context
            self.url = "about:blank"
            self.login_required = False

        class LoginFrameLocator:
            def __init__(self, page):
                self.page = page

            def count(self):
                return 1 if self.page.login_required else 0

            def nth(self, index):
                assert index == 0
                return self

            def is_visible(self):
                return self.page.login_required

            def get_attribute(self, name):
                assert name == "src"
                return "https://login.taobao.com/member/login.jhtml?style=mini"

        def locator(self, selector):
            assert "login.taobao.com" in selector
            return self.LoginFrameLocator(self)

        def evaluate(self, code):
            if "GENERIC_LOGIN_PROMPT_DETECTOR" in code:
                return {
                    "success": True,
                    "login_required": False,
                    "url": self.url,
                }
            return None

        def wait_for_timeout(self, _milliseconds):
            raise AssertionError("Taobao login must wait for desktop confirmation")

        def is_closed(self):
            return False

    class FakeBrowserManager:
        def __init__(self):
            self._context = FakeContext()
            self.page = FakePage(self._context)
            self.current_domain = ""
            self.saved_domains: list[str] = []

        def get_page(self):
            return self.page

        def save_auth(self, domain=None):
            self.saved_domains.append(domain)
            return True

    browser_manager = FakeBrowserManager()
    engine = ScriptEngine(browser_manager)

    class FakePanel:
        def toggle(self, _page, _visible):
            return None

        def log(self, _page, _message):
            return None

        def set_title(self, _page, title):
            events.append(f"title:{title}")

        def prompt(self, page, question):
            assert "[已经完成]" in question
            events.append("login_confirmed")
            page.login_required = False
            page.context.logged_in = True
            return "已经完成"

    monkeypatch.setattr("src.panel.get_panel_manager", lambda: FakePanel())

    def navigate(url):
        browser_manager.page.url = url
        if url.startswith("https://login.taobao.com/"):
            events.append("goto_login")
        else:
            events.append("goto_search")
        now[0] += 3.0
        return "ok"

    engine.register_functions(
        {
            "goto": navigate,
            "wait": lambda _seconds: None,
            "url_quote": lambda value: value,
            "taobao_collect_products": lambda keyword, max_items=20: (
                events.append("collect"),
                {"keyword": keyword, "products": []},
            )[-1],
            "log": lambda _message: None,
        }
    )
    source = Path("src/skill_library/search/taobao_search.py").read_text(
        encoding="utf-8"
    )

    result = engine.execute(source + '\nresult = run("keyboard")\n')

    assert result.success is True
    assert events == [
        "goto_login",
        "title:确认已登录完成",
        "login_confirmed",
        "title:",
        "goto_search",
        "collect",
    ]
    assert browser_manager.saved_domains == ["taobao"]
