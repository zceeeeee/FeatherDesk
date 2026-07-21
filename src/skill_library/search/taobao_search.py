"""Taobao product search adapter."""


def run(keyword: str):
    """Search Taobao and return the first three products with price data."""
    keyword = str(keyword or "").strip()
    if not keyword or keyword == "-1":
        raise ValueError("淘宝搜索需要商品关键词")
    goto(f"https://s.taobao.com/search?q={url_quote(keyword)}")
    wait(3)
    result = taobao_collect_products(keyword, max_items=20)
    log(f"淘宝商品搜索完成: {keyword}，找到 {len(result.get('products', []))} 个结果")
    return result
