"""Xiaohongshu 搜索适配器。"""
def run(keyword: str):
    """在xiaohongshu搜索关键词。

    Args:
        keyword: 搜索关键词。

    流程:
        1. 构造google搜索结果页 URL
        2. 直接导航到结果页
    """
    goto(f"https://www.xiaohongshu.com/search_result_ai?keyword={keyword}")
    log(f"xiaohongshu搜索完成: {keyword}")
