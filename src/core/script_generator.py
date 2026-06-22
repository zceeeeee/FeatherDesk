"""
脚本生成器 —— 根据任务描述生成 Python 脚本。

支持多种任务类型：
- 搜索任务：提取关键词，选择搜索引擎
- 导航任务：提取 URL，直接导航
- 截图任务：保存当前页面
- 提取任务：提取页面文本/链接
- 表单任务：填写表单字段
- 翻页任务：遍历多页内容
- 登录任务：填写用户名密码
- 复合任务：组合多个操作
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class TaskIntent:
    """解析后的任务意图。"""

    action: str  # search, navigate, screenshot, extract, fill, paginate, login, composite
    target: str = ""  # 目标 URL 或搜索关键词
    parameters: dict = None  # 额外参数

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class ScriptGenerator:
    """根据任务描述生成 Python 脚本。"""

    # 搜索引擎/网站配置
    SEARCH_ENGINES = {
        "baidu": {
            "url": "https://www.baidu.com",
            "input": "#kw",
            "submit": "#su",
            "name": "百度",
        },
        "google": {
            "url": "https://www.google.com",
            "input": "textarea[name='q']",
            "submit": "input[name='btnK']",
            "name": "Google",
        },
        "bing": {
            "url": "https://cn.bing.com",
            "input": "#sb_form_q",
            "submit": "#sb_form_go",
            "name": "必应",
        },
        "sogou": {
            "url": "https://www.sogou.com",
            "input": "#query",
            "submit": "#stb",
            "name": "搜狗",
        },
        "so": {
            "url": "https://www.so.com",
            "input": "#input",
            "submit": "#search-button",
            "name": "360搜索",
        },
        "dangdang": {
            "url": "https://www.dangdang.com",
            "input": "#key_S",
            "submit": ".button",
            "name": "当当",
        },
        "csdn": {
            "url": "https://so.csdn.net/so/search?q=",
            "input": "#toolbar-search-input",
            "submit": ".toolbar-search-btn",
            "name": "CSDN",
        },
        "gitee": {
            "url": "https://search.gitee.com/?type=repository&q=",
            "input": "#search-input",
            "submit": ".search-btn",
            "name": "Gitee",
        },
        "baike": {
            "url": "https://baike.baidu.com",
            "input": "#query",
            "submit": ".search-btn",
            "name": "百度百科",
        },
        "toutiao": {
            "url": "https://so.toutiao.com/search?keyword=",
            "input": "input[placeholder*='搜索']",
            "submit": ".search-btn",
            "name": "今日头条",
        },
        "zhihu": {
            "url": "https://www.zhihu.com/search",
            "input": ".Input-wrapper input",
            "submit": ".SearchBar-searchButton",
            "name": "知乎",
        },
        "douban": {
            "url": "https://www.douban.com",
            "input": "#inp-query",
            "submit": ".bn",
            "name": "豆瓣",
        },
        "bilibili": {
            "url": "https://search.bilibili.com/all?keyword=",
            "input": ".nav-search-input",
            "submit": ".nav-search-btn",
            "name": "B站",
        },
        "weibo": {
            "url": "https://s.weibo.com",
            "input": "#search-input",
            "submit": "[node-type='searchbtn']",
            "name": "微博",
        },
        "wenku": {
            "url": "https://wenku.baidu.com",
            "input": "#search-input",
            "submit": ".search-btn",
            "name": "百度文库",
        },
        "taobao": {
            "url": "https://www.taobao.com",
            "input": "#q",
            "submit": ".btn-search",
            "name": "淘宝",
        },
        "jd": {
            "url": "https://www.jd.com",
            "input": "#key",
            "submit": ".button",
            "name": "京东",
        },
        "pdd": {
            "url": "https://www.pinduoduo.com",
            "input": "input[placeholder*='搜索']",
            "submit": ".search-btn",
            "name": "拼多多",
        },
        "weather": {
            "url": "https://www.weather.com.cn",
            "input": "#search_input",
            "submit": ".search-btn",
            "name": "天气网",
        },
    }

    def generate(self, task: str, page_summary: str = "") -> str | None:
        """根据任务描述生成脚本。

        Args:
            task: 用户的任务描述。
            page_summary: 当前页面摘要。

        Returns:
            生成的 Python 脚本，或 None（无法生成）。
        """
        intent = self.parse_intent(task)
        if intent is None:
            return None

        return self._intent_to_script(intent)

    def parse_intent(self, task: str) -> TaskIntent | None:
        """解析任务描述为结构化意图。"""
        task_lower = task.lower().strip()

        # 截图任务（最简单，优先检测）
        if any(kw in task_lower for kw in ["截图", "screenshot", "截屏", "保存页面"]):
            return TaskIntent(action="screenshot")

        # 导航任务
        url = self._extract_url(task)
        if url and any(kw in task_lower for kw in ["打开", "导航", "goto", "open", "访问", "去"]):
            return TaskIntent(action="navigate", target=url)

        # 纯 URL 也视为导航
        if url and len(task.strip()) < len(url) + 10:
            return TaskIntent(action="navigate", target=url)

        # 搜索任务
        if any(kw in task_lower for kw in ["搜索", "search", "查找", "找", "查", "搜", "查询", "lookup"]):
            keyword = self._extract_keyword(task)
            engine = self._detect_search_engine(task)
            if keyword:
                return TaskIntent(
                    action="search",
                    target=keyword,
                    parameters={"engine": engine},
                )

        # 提取任务
        if any(kw in task_lower for kw in ["提取", "extract", "获取文本", "抓取", "爬取"]):
            return TaskIntent(action="extract")

        # 翻页任务
        if any(kw in task_lower for kw in ["翻页", "下一页", "next page", "分页", "遍历"]):
            pages = self._extract_number(task, default=5)
            return TaskIntent(action="paginate", parameters={"max_pages": pages})

        # 表单任务
        if any(kw in task_lower for kw in ["填写", "填入", "输入", "fill", "表单"]):
            return TaskIntent(action="fill")

        # 登录任务
        if any(kw in task_lower for kw in ["登录", "login", "sign in", "登陆"]):
            return TaskIntent(action="login")

        # 点击任务
        if any(kw in task_lower for kw in ["点击", "click", "按", "按钮"]):
            target = self._extract_click_target(task)
            if target:
                return TaskIntent(action="click", target=target)

        # 滚动任务
        if any(kw in task_lower for kw in ["滚动", "scroll", "下滑", "上滑"]):
            direction = "down" if any(kw in task_lower for kw in ["下", "down"]) else "up"
            return TaskIntent(action="scroll", parameters={"direction": direction})

        # 等待任务
        if any(kw in task_lower for kw in ["等待", "wait", "暂停"]):
            seconds = self._extract_number(task, default=3)
            return TaskIntent(action="wait", parameters={"seconds": seconds})

        return None

    def _intent_to_script(self, intent: TaskIntent) -> str:
        """将意图转换为 Python 脚本。"""
        if intent.action == "screenshot":
            return self._gen_screenshot()

        if intent.action == "navigate":
            return self._gen_navigate(intent.target)

        if intent.action == "search":
            engine = intent.parameters.get("engine", "baidu")
            return self._gen_search(intent.target, engine)

        if intent.action == "extract":
            return self._gen_extract()

        if intent.action == "paginate":
            max_pages = intent.parameters.get("max_pages", 5)
            return self._gen_paginate(max_pages)

        if intent.action == "fill":
            return self._gen_fill()

        if intent.action == "login":
            return self._gen_login()

        if intent.action == "click":
            return self._gen_click(intent.target)

        if intent.action == "scroll":
            direction = intent.parameters.get("direction", "down")
            return self._gen_scroll(direction)

        if intent.action == "wait":
            seconds = intent.parameters.get("seconds", 3)
            return self._gen_wait(seconds)

        return None

    # -------------------------------------------------------------------
    # 脚本模板
    # -------------------------------------------------------------------

    def _gen_screenshot(self) -> str:
        return 'screenshot("task_screenshot.png")\nlog("截图完成")'

    def _gen_navigate(self, url: str) -> str:
        return f'goto("{url}")\nwait_for_navigation()\nlog("导航完成: {url}")'

    def _gen_search(self, keyword: str, engine: str) -> str:
        cfg = self.SEARCH_ENGINES.get(engine, self.SEARCH_ENGINES["baidu"])

        # 某些网站支持 URL 直接搜索
        url_search_engines = ["csdn", "gitee", "bilibili", "toutiao"]
        if engine in url_search_engines:
            return f'goto("{cfg["url"]}{keyword}")\nwait_for_navigation()\nlog("{cfg["name"]}搜索完成: {keyword}")'

        # 某些网站需要用 JS 操作（headless 模式下元素可能被隐藏）
        js_engines = ["baidu"]
        if engine in js_engines:
            url = cfg["url"]
            inp = cfg["input"]
            btn = cfg["submit"]
            return (
                f'goto("{url}")\n'
                f'wait_for_navigation()\n'
                f"run_js('document.querySelector(\\\"{inp}\\\").value = \\\"{keyword}\\\"')\n"
                f"run_js('document.querySelector(\\\"{btn}\\\").click()')\n"
                f'wait(3)\n'
                f'log("{cfg["name"]}搜索完成: {keyword}")'
            )

        # 表单搜索（默认）
        return (
            f'goto("{cfg["url"]}")\n'
            f'wait_for_navigation()\n'
            f'fill("{cfg["input"]}", "{keyword}")\n'
            f'click("{cfg["submit"]}")\n'
            f'wait_for_navigation()\n'
            f'log("{cfg["name"]}搜索完成: {keyword}")'
        )

    def _gen_extract(self) -> str:
        return '''text = get_text()
log(f"提取文本长度: {len(text)}")
print(text[:2000])'''

    def _gen_paginate(self, max_pages: int) -> str:
        return f'''for page_num in range(1, {max_pages + 1}):
    log(f"正在处理第 {{page_num}} 页")
    text = get_text()
    print(f"--- 第 {{page_num}} 页 ---")
    print(text[:500])
    result = click("text=下一页", "a.next", "text=Next", "text=»")
    if not result.get("success"):
        log("没有更多页面")
        break
    wait_for_navigation()
    wait(1.0)
log("翻页完成")'''

    def _gen_fill(self) -> str:
        return '''# 请根据实际页面修改选择器和值
# fill("#name", "张三")
# fill("#email", "test@example.com")
# click("#submit")
log("表单填写模板 - 请根据实际页面修改")'''

    def _gen_login(self) -> str:
        return '''# 请根据实际网站修改选择器
# goto("https://example.com/login")
# fill("#username", "your_username")
# fill("#password", "your_password")
# click("#login-btn")
# wait_for_navigation()
log("登录模板 - 请根据实际网站修改")'''

    def _gen_click(self, target: str) -> str:
        return f'''result = click("{target}")
if result.get("success"):
    log("点击成功: {target}")
    wait_for_navigation()
else:
    log("点击失败: {target}")'''

    def _gen_scroll(self, direction: str) -> str:
        if direction == "down":
            return '''page.evaluate("window.scrollBy(0, 500)")
wait(0.5)
log("向下滚动")'''
        else:
            return '''page.evaluate("window.scrollBy(0, -500)")
wait(0.5)
log("向上滚动")'''

    def _gen_wait(self, seconds: int) -> str:
        return f'wait({seconds})\nlog("等待 {seconds} 秒")'

    # -------------------------------------------------------------------
    # 辅助方法
    # -------------------------------------------------------------------

    def _extract_keyword(self, task: str) -> str | None:
        """从任务描述中提取搜索关键词。"""
        # 匹配 "在XXX搜索/查询YYY" 模式
        patterns = [
            r'(?:在|到)(?:百度|google|bing|谷歌|必应|搜狗|360|当当|CSDN|Gitee|百科|头条|知乎|豆瓣|B站|微博|文库|淘宝|京东|拼多多|天气网)?(?:上)?(?:搜索|查询|查找)[:\s]*(.+)',
            r'(?:百度|google|bing|搜狗|360|当当|CSDN|Gitee|百科|头条|知乎|豆瓣|B站|微博|文库|淘宝|京东|拼多多)?(?:搜索|查询|查找)[:\s]*(.+)',
            r'(?:搜索|查询|查找)[:\s]*(.+)',
            r'search\s+(?:for\s+)?(.+)',
            r'找[:\s]*(.+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, task, re.IGNORECASE)
            if match:
                keyword = match.group(1).strip()
                # 清理尾部
                keyword = re.sub(r'[，。,.!?！？]$', '', keyword)
                if keyword:
                    return keyword

        # 降级：去掉常见动词前缀
        prefixes = ["帮我在百度搜索", "在百度搜索", "帮我搜索", "百度搜索",
                     "search for", "search", "搜索", "查找", "找", "查"]
        task_lower_stripped = task.lower().strip()
        for prefix in prefixes:
            if task_lower_stripped.startswith(prefix):
                keyword = task[len(prefix):].strip()
                keyword = re.sub(r'[，。,.!?！？]$', '', keyword)
                if keyword:
                    return keyword

        return None

    def _extract_url(self, task: str) -> str | None:
        """从任务描述中提取 URL。"""
        # 匹配完整 URL
        url_pattern = r'https?://[\w\-./?=&%#+~:@!$&\'()*+,;]+'
        match = re.search(url_pattern, task)
        if match:
            url = match.group(0).rstrip(".,;:!?")
            return url

        # 匹配域名
        domain_pattern = r'(?:^|\s)([\w-]+\.(com|cn|org|net|io|dev|cc))(?:\s|$|[，。,.])'
        match = re.search(domain_pattern, task)
        if match:
            return f"https://{match.group(1)}"

        return None

    def _detect_search_engine(self, task: str) -> str:
        """检测用户想用哪个搜索引擎/网站。"""
        task_lower = task.lower()
        if any(kw in task_lower for kw in ["google", "谷歌"]):
            return "google"
        if any(kw in task_lower for kw in ["bing", "必应"]):
            return "bing"
        if any(kw in task_lower for kw in ["搜狗", "sogou"]):
            return "sogou"
        if any(kw in task_lower for kw in ["360", "so.com"]):
            return "so"
        if any(kw in task_lower for kw in ["当当", "dangdang"]):
            return "dangdang"
        if any(kw in task_lower for kw in ["csdn"]):
            return "csdn"
        if any(kw in task_lower for kw in ["gitee"]):
            return "gitee"
        if any(kw in task_lower for kw in ["百科", "baike"]):
            return "baike"
        if any(kw in task_lower for kw in ["头条", "toutiao"]):
            return "toutiao"
        if any(kw in task_lower for kw in ["知乎", "zhihu"]):
            return "zhihu"
        if any(kw in task_lower for kw in ["豆瓣", "douban"]):
            return "douban"
        if any(kw in task_lower for kw in ["b站", "bilibili", "哔哩"]):
            return "bilibili"
        if any(kw in task_lower for kw in ["微博", "weibo", "热搜"]):
            return "weibo"
        if any(kw in task_lower for kw in ["文库", "wenku"]):
            return "wenku"
        if any(kw in task_lower for kw in ["淘宝", "taobao"]):
            return "taobao"
        if any(kw in task_lower for kw in ["京东", "jd"]):
            return "jd"
        if any(kw in task_lower for kw in ["拼多多", "pdd"]):
            return "pdd"
        if any(kw in task_lower for kw in ["天气", "weather"]):
            return "weather"
        return "baidu"  # 默认百度

    def _extract_number(self, task: str, default: int = 5) -> int:
        """从任务描述中提取数字。"""
        match = re.search(r'(\d+)\s*(?:页|个|次|步|秒)', task)
        if match:
            return int(match.group(1))
        return default

    def _extract_click_target(self, task: str) -> str | None:
        """提取点击目标。"""
        # 匹配引号内的选择器
        match = re.search(r'["\']([^"\']+)["\']', task)
        if match:
            return match.group(1)

        # 匹配 "点击XXX" 模式
        match = re.search(r'点击[:\s]*(.+)', task)
        if match:
            target = match.group(1).strip()
            # 如果是纯文本，用 text= 选择器
            if not target.startswith(('#', '.', '/', '[')):
                return f"text={target}"
            return target

        return None
