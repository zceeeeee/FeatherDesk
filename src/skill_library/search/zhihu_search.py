"""知乎 搜索适配器。"""
def run(keyword: str):
    """在知乎搜索关键词。

    Args:
        keyword: 搜索关键词。

    流程:
        1. 构造知乎搜索结果页 URL
        2. 直接导航到结果页
    """
    goto(f"https://www.zhihu.com/search?q={keyword}")
    log(f"yotube搜索完成: {keyword}")

