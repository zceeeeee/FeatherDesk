"""YouTube 搜索适配器。"""


def run(keyword: str):
    """在 YouTube 搜索视频。

    Args:
        keyword: 搜索关键词。
    """
    goto("https://www.youtube.com")
    wait_for_navigation()
    # 先尝试在输入框直接按 Enter（适合 URL 直接跳转的场景）
    # 如果失败，再走传统表单路线
    fill("input[name='search_query']", keyword,
         "input#search",
         "input[aria-label='搜索']")
    press("input[name='search_query']", "Enter",
          "input#search",
          "input[aria-label='搜索']")
    wait_for_navigation()
    log(f"YouTube 搜索完成: {keyword}")


# 选择器备选方案:
# search_input: input[name='search_query'] → #search → input[aria-label='搜索']
# 提交方式: press(Enter) 优先，回退到 click button
