"""BOSS 直聘搜索适配器。

在 BOSS 直聘搜索指定关键词，支持城市筛选。
"""

# BOSS 直聘城市代码
_CITY_CODES = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "南京": "101190100",
    "武汉": "101200100",
    "西安": "101110100",
    "苏州": "101190400",
    "长沙": "101250100",
    "天津": "101030100",
    "重庆": "101040100",
    "郑州": "101180100",
    "东莞": "101281600",
    "青岛": "101120200",
    "合肥": "101220100",
    "厦门": "101230200",
    "昆明": "101290100",
    "大连": "101070200",
    "珠海": "101280700",
    "佛山": "101280800",
    "宁波": "101210400",
}

# 用于从关键词中识别城市
_ALL_CITIES = "|".join(_CITY_CODES.keys())


def _extract_city_from_keyword(keyword: str) -> tuple:
    """从关键词中提取城市和纯关键词。

    Returns:
        (city, pure_keyword) 元组。
    """
    import re

    # 匹配 "深圳的AI产品经理" 或 "深圳AI产品经理" 或 "AI产品经理深圳"
    match = re.search(
        rf"({_ALL_CITIES})(?:的|地|\\s)*(.+)",
        keyword,
    )
    if match:
        return match.group(1), match.group(2).strip()

    # 匹配关键词末尾的城市 "AI产品经理在深圳"
    match = re.search(
        rf"(.+?)(?:在|去|到)({_ALL_CITIES})$",
        keyword,
    )
    if match:
        return match.group(2), match.group(1).strip()

    return "全国", keyword


def run(keyword: str):
    """在 BOSS 直聘搜索职位。

    Args:
        keyword: 搜索内容，包含城市和职位关键词（如 "深圳的AI产品经理"）。

    流程:
        1. 从关键词中解析城市和职位
        2. 构造 BOSS 直聘搜索结果页 URL
        3. 直接导航到结果页
    """
    keyword = str(keyword or "").strip()
    if not keyword or keyword == "-1":
        raise ValueError("BOSS直聘搜索需要职位关键词")

    city, pure_keyword = _extract_city_from_keyword(keyword)
    city_code = _CITY_CODES.get(city, _CITY_CODES["全国"])
    target_url = f"https://www.zhipin.com/web/geek/jobs?city={city_code}&query={url_quote(pure_keyword)}"

    goto(target_url)
    log(f"BOSS直聘搜索完成: {pure_keyword} ({city})")
