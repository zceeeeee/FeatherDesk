"""Layer 3 helpers for extracting and presenting Taobao product results."""

from __future__ import annotations

import base64
import io
import math
import re
from statistics import mean, median
from typing import Any
from urllib.parse import urljoin

from PIL import Image, ImageDraw


class TaobaoResultError(RuntimeError):
    """Raised when the Taobao result page cannot be read."""


TAOBAO_RESULT_SCRIPT = r"""
(limit) => {
  const maxItems = Math.max(1, Number(limit) || 20);
  const blocked = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SVG"]);
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (node) => {
    if (!node || blocked.has(node.tagName)) return false;
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      rect.width > 0 && rect.height > 0;
  };
  const firstText = (root, selectors) => {
    for (const selector of selectors) {
      const node = root.querySelector(selector);
      if (node && visible(node)) {
        const value = clean(node.innerText || node.textContent);
        if (value) return value;
      }
    }
    return "";
  };
  const roots = Array.from(document.querySelectorAll(
    '[data-id], [class*="doubleCardWrapper"], [class*="Card"], ' +
    'a[href*="item.taobao.com"], a[href*="detail.tmall.com"]'
  ));
  const products = [];
  const seen = new Set();
  for (const node of roots) {
    if (!visible(node)) continue;
    const root = node.closest('[data-id], [class*="doubleCardWrapper"], [class*="Card"]') || node;
    if (!visible(root)) continue;
    const link = root.matches('a[href*="item.taobao.com"], a[href*="detail.tmall.com"]')
      ? root
      : root.querySelector('a[href*="item.taobao.com"], a[href*="detail.tmall.com"]');
    const productUrl = link ? link.href : "";
    const id = root.getAttribute("data-id") || productUrl || clean(root.innerText);
    if (!id || seen.has(id)) continue;
    const text = clean(root.innerText);
    if (!text || text.length < 2) continue;
    const title = firstText(root, [
      '[class*="title"]', '[class*="Title"]', '[data-title]'
    ]) || clean(link && link.innerText) || text.split(/\n| {2,}/)[0];
    const shop = firstText(root, [
      '[class*="shop"]', '[class*="Shop"]', '[class*="seller"]',
      '[class*="Seller"]', '[class*="店铺"]'
    ]);
    const price = firstText(root, [
      '[class*="price"]', '[class*="Price"]', '[class*="money"]',
      '[class*="Money"]'
    ]) || ((text.match(/[¥￥]\s*[\d,.]+/) || [""])[0]);
    const image = root.querySelector("img");
    const imageUrl = image && (image.currentSrc || image.src ||
      image.getAttribute("data-src") || image.getAttribute("data-lazy-src")) || "";
    if (!title) continue;
    products.push({
      title: clean(title),
      shop: clean(shop),
      price: clean(price),
      image_url: String(imageUrl || ""),
      product_url: productUrl
    });
    seen.add(id);
    if (products.length >= maxItems) break;
  }
  return { products };
}
"""


_WHITESPACE_RE = re.compile(r"\s+")
_PRICE_RE = re.compile(r"(?:¥|￥|RMB|人民币)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)")


def _clean(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip()


def _as_url(value: Any, *, base_url: str = "") -> str:
    text = _clean(value)
    if text.startswith("//"):
        return f"https:{text}"
    return urljoin(base_url, text) if text else ""


def _parse_price(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    match = _PRICE_RE.search(_clean(value))
    if not match:
        return None
    try:
        number = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _normalize_product(raw: Any, *, base_url: str = "") -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title = _clean(raw.get("title") or raw.get("name"))
    if not title:
        return None
    numeric_price = raw.get("price")
    display_price = raw.get("price_text") or raw.get("priceText") or numeric_price
    if numeric_price in (None, ""):
        numeric_price = display_price
    return {
        "title": title,
        "shop": _clean(raw.get("shop") or raw.get("shop_name") or raw.get("seller")),
        "price": _parse_price(numeric_price),
        "price_text": _clean(display_price),
        "image_url": _as_url(
            raw.get("image_url") or raw.get("image") or raw.get("img"),
            base_url=base_url,
        ),
        "product_url": _as_url(
            raw.get("product_url") or raw.get("url") or raw.get("link"),
            base_url=base_url,
        ),
    }


def extract_taobao_products(page: Any, *, max_items: int = 20) -> list[dict[str, Any]]:
    """Extract visible product cards from a Taobao result page."""
    if page is None or not hasattr(page, "evaluate"):
        raise TaobaoResultError("Taobao result page is unavailable")
    try:
        payload = page.evaluate(TAOBAO_RESULT_SCRIPT, max(1, int(max_items)))
    except Exception as exc:
        raise TaobaoResultError(f"Failed to extract Taobao results: {exc}") from exc
    raw_products = payload.get("products", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_products, list):
        return []
    base_url = str(getattr(page, "url", "") or "")
    products: list[dict[str, Any]] = []
    for raw in raw_products[: max(1, int(max_items))]:
        normalized = _normalize_product(raw, base_url=base_url)
        if normalized:
            products.append(normalized)
    return products


def _histogram(values: list[float]) -> list[dict[str, Any]]:
    if not values:
        return []
    low, high = min(values), max(values)
    if low == high:
        return [{"start": low, "end": high, "count": len(values)}]
    bin_count = min(8, max(2, math.ceil(math.sqrt(len(values)))))
    width = (high - low) / bin_count
    bins = [
        {"start": low + index * width, "end": low + (index + 1) * width, "count": 0}
        for index in range(bin_count)
    ]
    for value in values:
        index = min(bin_count - 1, int((value - low) / width))
        bins[index]["count"] += 1
    return bins


def _render_histogram(values: list[float]) -> dict[str, Any] | None:
    bins = _histogram(values)
    if not bins:
        return None
    width, height = 720, 390
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = 64, 24, width - 24, height - 62
    max_count = max(item["count"] for item in bins) or 1
    draw.line((left, top, left, bottom), fill="#344054", width=2)
    draw.line((left, bottom, right, bottom), fill="#344054", width=2)
    bar_width = (right - left) / len(bins)
    for index, item in enumerate(bins):
        bar_height = (bottom - top) * item["count"] / max_count
        x1 = left + index * bar_width + 5
        x2 = left + (index + 1) * bar_width - 5
        y1 = bottom - bar_height
        draw.rectangle((x1, y1, x2, bottom), fill="#67a2c5", outline="#3e7d9f")
        draw.text((x1 + 3, max(top, y1 - 16)), str(item["count"]), fill="#344054")
        draw.text((x1 + 2, bottom + 8), f"{item['start']:.0f}", fill="#344054")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "mime_type": "image/png",
        "data_url": f"data:image/png;base64,{encoded}",
        "bins": bins,
    }


def build_taobao_search_result(
    keyword: str,
    products: list[dict[str, Any]],
    *,
    max_products: int = 3,
) -> dict[str, Any]:
    """Build the bounded artifact shown by the desktop chat."""
    normalized = [
        item for item in (_normalize_product(product) for product in products) if item
    ]
    selected = normalized[: max(1, int(max_products))]
    prices = [item["price"] for item in normalized if item["price"] is not None]
    statistics = None
    histogram = None
    if prices:
        statistics = {
            "count": len(prices),
            "min": min(prices),
            "max": max(prices),
            "average": mean(prices),
            "median": median(prices),
        }
        histogram = _render_histogram(prices)
    return {
        "type": "taobao_product_search",
        "keyword": _clean(keyword),
        "products": selected,
        "statistics": statistics,
        "histogram": histogram,
    }
