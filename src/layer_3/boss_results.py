"""Layer 3 helpers for extracting and presenting BOSS Zhipin job results."""

from __future__ import annotations

import re
from typing import Any


class BossResultError(RuntimeError):
    """Raised when the BOSS result page cannot be read."""


# ---------------------------------------------------------------------------
# City parsing (moved from boss_search.py to avoid import re in sandbox)
# ---------------------------------------------------------------------------

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

_ALL_CITIES = "|".join(_CITY_CODES.keys())


def parse_boss_keyword(keyword: str) -> tuple[str, str, str]:
    """Parse a BOSS keyword string into (city, city_code, pure_keyword).

    Args:
        keyword: Raw keyword like "深圳的AI产品经理" or "AI产品经理".

    Returns:
        (city_name, city_code, pure_keyword) tuple.
    """
    keyword = str(keyword or "").strip()
    if not keyword:
        return "全国", _CITY_CODES["全国"], ""

    # 去掉逗号及后面的内容（如 "AI产品经理岗位，分析前5页" → "AI产品经理岗位"）
    keyword = re.split(r"[，,。.;；]", keyword, maxsplit=1)[0].strip()

    # Match "深圳的AI产品经理" or "深圳AI产品经理" or "深圳地区的AI产品经理"
    match = re.search(rf"({_ALL_CITIES})(?:地区的?|的|地|\s)*(.+)", keyword)
    if match:
        city = match.group(1)
        pure = match.group(2).strip()
        return city, _CITY_CODES.get(city, _CITY_CODES["全国"]), pure

    # Match "AI产品经理在深圳"
    match = re.search(rf"(.+?)(?:在|去|到)({_ALL_CITIES})$", keyword)
    if match:
        city = match.group(2)
        pure = match.group(1).strip()
        return city, _CITY_CODES.get(city, _CITY_CODES["全国"]), pure

    return "全国", _CITY_CODES["全国"], keyword


def build_boss_search_url(keyword: str) -> tuple[str, str, str]:
    """Build the BOSS Zhipin search URL from a keyword string.

    Args:
        keyword: Raw keyword like "深圳的AI产品经理".

    Returns:
        (url, city, pure_keyword) tuple.
    """
    from urllib.parse import quote_plus

    city, city_code, pure_keyword = parse_boss_keyword(keyword)
    url = f"https://www.zhipin.com/web/geek/jobs?city={city_code}&query={quote_plus(pure_keyword)}"
    return url, city, pure_keyword


# ---------------------------------------------------------------------------
# JavaScript extractors
# ---------------------------------------------------------------------------

BOSS_RESULT_SCRIPT = r"""
(maxItems) => {
  const limit = Math.max(1, Number(maxItems) || 30);
  const clean = (s) => String(s || "").replace(/\s+/g, " ").trim();

  // BOSS 直聘职位卡片选择器
  const cards = document.querySelectorAll(".job-card-wrapper");
  const jobs = [];
  const seen = new Set();

  for (const card of cards) {
    if (jobs.length >= limit) break;

    // 职位名
    const titleEl = card.querySelector(".job-name");
    const title = clean(titleEl ? (titleEl.innerText || titleEl.textContent) : "");
    if (!title) continue;

    // 公司名
    const companyEl = card.querySelector(".company-name a");
    const company = clean(companyEl ? (companyEl.innerText || companyEl.textContent) : "");
    const key = title + "|" + company;
    if (seen.has(key)) continue;
    seen.add(key);

    // 薪资 — 在 .job-info 下的 .salary
    const salaryEl = card.querySelector(".job-info .salary, .salary");
    const salary = clean(salaryEl ? (salaryEl.innerText || salaryEl.textContent) : "");

    // 地点 — 在 .job-info 下的 .job-area
    const areaEl = card.querySelector(".job-info .job-area, .job-area");
    const area = clean(areaEl ? (areaEl.innerText || areaEl.textContent) : "");

    // 要求标签 — 在 .job-info 下的 .tag-list 或 info-desc
    const tagListEl = card.querySelector(".job-info .tag-list");
    let tags = clean(tagListEl ? (tagListEl.innerText || tagListEl.textContent) : "");

    // 如果 tag-list 为空，尝试从所有 info-desc 中提取（跳过第一个，那是薪资+地点）
    if (!tags) {
      const descs = card.querySelectorAll(".job-info .info-desc");
      const tagParts = [];
      for (let i = 1; i < descs.length; i++) {
        const t = clean(descs[i].innerText || descs[i].textContent);
        if (t) tagParts.push(t);
      }
      tags = tagParts.join(" ");
    }

    // 公司链接
    const companyLink = companyEl && companyEl.href ? companyEl.href : "";

    // 职位链接
    const jobLinkEl = card.querySelector("a[href*='/job_detail']");
    const jobUrl = jobLinkEl ? jobLinkEl.href : "";

    jobs.push({
      title: title,
      company: company,
      salary: salary,
      area: area,
      tags: tags,
      job_url: jobUrl,
      company_url: companyLink,
    });
  }

  return { jobs: jobs, total_cards: cards.length };
}
"""


# ---------------------------------------------------------------------------
# Python helpers
# ---------------------------------------------------------------------------


def _clean(value: Any) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_salary_range(salary_text: str) -> dict[str, Any]:
    """Parse salary text like '15-25K' or '15-25K·13薪' into structured data."""
    text = _clean(salary_text)
    if not text:
        return {"text": "", "min": None, "max": None, "months": None}

    months_match = re.search(r"[·.]\s*(\d+)\s*薪", text)
    months = int(months_match.group(1)) if months_match else None

    range_match = re.search(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)\s*([Kk万千]?)", text)
    if not range_match:
        return {"text": text, "min": None, "max": None, "months": months}

    low = float(range_match.group(1))
    high = float(range_match.group(2))
    unit = range_match.group(3).upper()

    if unit in ("万",):
        low *= 10
        high *= 10

    return {"text": text, "min": low, "max": high, "months": months}


def _normalize_job(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a raw job dict into a clean structure."""
    if not isinstance(raw, dict):
        return None
    title = _clean(raw.get("title"))
    if not title:
        return None

    salary_info = _parse_salary_range(raw.get("salary", ""))

    return {
        "title": title,
        "company": _clean(raw.get("company")),
        "salary": salary_info["text"],
        "salary_min": salary_info["min"],
        "salary_max": salary_info["max"],
        "salary_months": salary_info["months"],
        "area": _clean(raw.get("area")),
        "tags": _clean(raw.get("tags")),
        "job_url": _clean(raw.get("job_url")),
        "company_url": _clean(raw.get("company_url")),
    }


def extract_boss_jobs(page: Any, *, max_items: int = 30) -> list[dict[str, Any]]:
    """Extract visible job cards from a BOSS Zhipin result page."""
    if page is None or not hasattr(page, "evaluate"):
        raise BossResultError("BOSS result page is unavailable")
    try:
        payload = page.evaluate(BOSS_RESULT_SCRIPT, max(1, int(max_items)))
    except Exception as exc:
        raise BossResultError(f"Failed to extract BOSS results: {exc}") from exc

    raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if not isinstance(raw_jobs, list):
        return []

    jobs: list[dict[str, Any]] = []
    for raw in raw_jobs[: max(1, int(max_items))]:
        normalized = _normalize_job(raw)
        if normalized:
            jobs.append(normalized)
    return jobs


def _ocr_salary_from_card(page: Any, card_index: int) -> str:
    """Screenshot a single job card's salary element and OCR it.

    Args:
        page: Playwright page object.
        card_index: Zero-based index of the job card on the page.

    Returns:
        Salary text extracted via OCR, or empty string if failed.
    """
    import asyncio

    from src.core.ocr import get_ocr_module

    ocr = get_ocr_module()
    if ocr is None:
        return ""

    # Find the salary element within the Nth job card
    salary_el = page.locator(
        ".job-card-wrapper .salary, "
        ".job-card-wrapper [class*='salary'], "
        ".job-list .job-card .salary"
    ).nth(card_index)

    try:
        if not salary_el.is_visible(timeout=2000):
            return ""
        screenshot_bytes = salary_el.screenshot()
    except Exception:
        return ""

    if not screenshot_bytes:
        return ""

    try:
        result = asyncio.run(ocr.recognize(screenshot_bytes))
    except Exception:
        return ""

    text = (result.raw_text or "").strip()
    # Match salary patterns: "15-25K", "2-4万·13薪", "面议" etc.
    salary_match = re.search(
        r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)\s*[Kk万千](?:\s*[·.]\s*\d+\s*薪)?",
        text,
    )
    if salary_match:
        return salary_match.group(0).strip()

    if "面议" in text:
        return "面议"

    # Fallback: return whatever OCR found (cleaned)
    cleaned = re.sub(r"[^\d\-~Kk万千·薪面议]", "", text).strip()
    return cleaned if len(cleaned) >= 2 else ""


def enrich_boss_salaries(page: Any, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill in missing salaries by OCR-ing individual job card screenshots.

    For each job with an empty salary field, locates the corresponding
    job card element on the page, screenshots the salary area, runs
    Windows OCR, and updates the salary field.

    Args:
        page: Playwright page object (must be on the BOSS search results page).
        jobs: List of job dicts (may have empty salary fields).

    Returns:
        The same list with salary fields updated in-place.
    """
    if page is None or not hasattr(page, "locator"):
        return jobs

    for i, job in enumerate(jobs):
        salary = _clean(job.get("salary"))
        if salary:
            continue  # already has salary from DOM

        ocr_salary = _ocr_salary_from_card(page, i)
        if ocr_salary:
            job["salary"] = ocr_salary
            salary_info = _parse_salary_range(ocr_salary)
            job["salary_min"] = salary_info["min"]
            job["salary_max"] = salary_info["max"]
            job["salary_months"] = salary_info["months"]

    return jobs


def build_boss_search_result(
    keyword: str,
    jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a structured result artifact from collected jobs."""
    normalized = [item for item in (_normalize_job(j) for j in jobs) if item]

    salaries = [j["salary_min"] for j in normalized if j.get("salary_min") is not None]
    salary_stats = None
    if salaries:
        from statistics import mean, median
        salary_stats = {
            "count": len(salaries),
            "min": min(salaries),
            "max": max(salaries),
            "average": round(mean(salaries), 1),
            "median": round(median(salaries), 1),
        }

    company_counts: dict[str, int] = {}
    for j in normalized:
        name = j.get("company", "")
        if name:
            company_counts[name] = company_counts.get(name, 0) + 1
    top_companies = sorted(company_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "type": "boss_job_search",
        "keyword": _clean(keyword),
        "total_jobs": len(normalized),
        "jobs": normalized,
        "salary_stats": salary_stats,
        "top_companies": [{"name": name, "count": count} for name, count in top_companies],
    }
