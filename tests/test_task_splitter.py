"""TaskSplitter 单元测试。"""

import pytest

from src.core.task_splitter import TaskSplitter, reset_task_splitter


@pytest.fixture(autouse=True)
def _reset_splitter():
    """每个测试前重置全局单例。"""
    reset_task_splitter()
    yield
    reset_task_splitter()


class TestRuleSplit:
    """规则拆分测试。"""

    def test_chinese_period(self):
        splitter = TaskSplitter()
        result = splitter.split("打开百度。搜索Python教程")
        assert result == ["打开百度", "搜索Python教程"]

    def test_english_period(self):
        splitter = TaskSplitter()
        result = splitter.split("open baidu. search python")
        assert result == ["open baidu", "search python"]

    def test_multiple_periods(self):
        splitter = TaskSplitter()
        result = splitter.split("打开百度。搜索Python。截个图")
        assert result == ["打开百度", "搜索Python", "截个图"]

    def test_mixed_periods(self):
        splitter = TaskSplitter()
        result = splitter.split("打开百度.搜索Python。截个图")
        assert result == ["打开百度", "搜索Python", "截个图"]

    def test_single_command_no_split(self):
        splitter = TaskSplitter()
        result = splitter.split("搜索Python教程")
        assert result == ["搜索Python教程"]

    def test_empty_string(self):
        splitter = TaskSplitter()
        result = splitter.split("")
        assert result == [""]

    def test_whitespace_only(self):
        splitter = TaskSplitter()
        result = splitter.split("   ")
        assert result == [""]


class TestURLProtection:
    """URL 中的点号不拆分。"""

    def test_url_not_split(self):
        splitter = TaskSplitter()
        # 没有句号分隔，URL 中的点号不应被当作句号拆分
        result = splitter.split("打开 https://www.bilibili.com 搜索Python")
        assert len(result) == 1
        assert "https://www.bilibili.com" in result[0]

    def test_url_with_path(self):
        splitter = TaskSplitter()
        # URL 结尾的 . 后面是中文，URL 保护后不会被拆分
        result = splitter.split("打开 https://github.com/user/repo.查看代码")
        assert len(result) == 1  # URL 保护后整个作为一个任务

    def test_url_in_middle(self):
        splitter = TaskSplitter()
        result = splitter.split("打开 https://www.baidu.com。搜索Python")
        assert len(result) == 2
        assert "https://www.baidu.com" in result[0]
        assert "搜索Python" in result[1]


class TestQuotedProtection:
    """引号内的句号不拆分。"""

    def test_chinese_quotes(self):
        splitter = TaskSplitter()
        result = splitter.split("发布内容为「hello。world」。然后截图")
        assert len(result) == 2
        assert "hello。world" in result[0]

    def test_single_quotes(self):
        splitter = TaskSplitter()
        result = splitter.split("设置标题为'测试。标题'。保存")
        assert len(result) == 2
        assert "测试。标题" in result[0]

    def test_double_quotes(self):
        splitter = TaskSplitter()
        result = splitter.split('设置名称为"hello.world"。提交')
        assert len(result) == 2
        assert "hello.world" in result[0]


class TestConnectorSplit:
    """连接词拆分测试。"""

    def test_then_connector(self):
        splitter = TaskSplitter()
        result = splitter.split("打开百度然后搜索Python")
        assert len(result) == 2
        assert "打开百度" in result[0]
        assert "搜索Python" in result[1]

    def test_then_connector_chinese(self):
        splitter = TaskSplitter()
        result = splitter.split("打开百度，然后搜索Python教程")
        assert len(result) == 2

    def test_next_connector(self):
        splitter = TaskSplitter()
        result = splitter.split("打开百度接着搜索Python")
        assert len(result) == 2

    def test_also_connector(self):
        splitter = TaskSplitter()
        result = splitter.split("打开百度同时打开谷歌")
        assert len(result) == 2

    def test_and_then_english(self):
        splitter = TaskSplitter()
        result = splitter.split("open baidu and then search python")
        assert len(result) == 2

    def test_period_takes_priority(self):
        """句号拆分优先于连接词拆分。"""
        splitter = TaskSplitter()
        result = splitter.split("打开百度。搜索Python然后截图")
        # 句号拆分出 2 个，第二个含 "然后" 不再拆分（规则拆分已出多个，跳过连接词）
        assert len(result) == 2
        assert result[0] == "打开百度"
        assert "搜索Python" in result[1] or "截图" in result[1]


class TestEdgeCases:
    """边界情况测试。"""

    def test_trailing_punctuation(self):
        splitter = TaskSplitter()
        result = splitter.split("打开百度，。搜索Python；。截个图")
        assert len(result) == 3

    def test_consecutive_periods(self):
        splitter = TaskSplitter()
        result = splitter.split("打开百度。。搜索Python")
        assert len(result) == 2

    def test_ellipsis_not_split(self):
        splitter = TaskSplitter()
        result = splitter.split("等一下...然后搜索Python")
        # 省略号不应被拆分成多个空任务
        assert len(result) >= 1

    def test_preserves_content(self):
        splitter = TaskSplitter()
        result = splitter.split("在知乎搜索 AI Agent。在B站搜索 Playwright 教程")
        assert len(result) == 2
        assert "知乎" in result[0]
        assert "B站" in result[1]


class TestLLMSplit:
    """LLM 拆分测试（需要 mock）。"""

    def test_no_llm_caller_returns_single(self):
        """没有 LLM 调用器时，无法拆分就返回原始任务。"""
        splitter = TaskSplitter(llm_caller=None)
        result = splitter.split("打开百度搜索Python")
        assert result == ["打开百度搜索Python"]
