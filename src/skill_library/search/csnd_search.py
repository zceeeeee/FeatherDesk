""""csnd搜索适配器"""
def run(keyword: str):
    """在csnd搜索关键词。

    Args:
        keyword: 搜索关键词。

    流程:
        1. 构造csnd搜索结果页 URL
        2. 直接导航到结果页
    """
    goto(f"https://so.csdn.net/so/search?q={keyword}")
    log(f"csnd搜索完成: {keyword}")