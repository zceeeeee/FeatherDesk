"""Taobao product search adapter."""

LOGIN_URL = "https://login.taobao.com/member/login.jhtml"


def run(keyword: str):
    """Return the first three product images and five product detail rows."""
    keyword = str(keyword or "").strip()
    if not keyword or keyword == "-1":
        raise ValueError("淘宝搜索需要商品关键词")
    goto(LOGIN_URL)
    goto(f"https://s.taobao.com/search?q={url_quote(keyword)}")
    wait(3)
    result = taobao_collect_products(keyword, max_items=20)
    log(f"淘宝商品搜索完成: {keyword}，找到 {len(result.get('products', []))} 个结果")
    return result
