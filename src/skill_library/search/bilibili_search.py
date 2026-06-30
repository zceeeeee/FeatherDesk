"""bilibili 搜索。"""

def run(keyword: str):
    """在bilibili搜索关键词。

    Args:
        keyword: 搜索关键词。

    流程:
        1. 构造百度搜索结果页 URL
        2. 直接导航到结果页
    """
    goto(f"https://search.bilibili.com/all?keyword={keyword}")
    log(f"Bing搜索完成: {keyword}")