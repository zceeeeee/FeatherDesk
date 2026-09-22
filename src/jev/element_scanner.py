"""
Element Scanner for Jev Integration.

Inspects the live Playwright page, filters interactive elements based on ARIA roles
and DOM heuristics, and assigns ref IDs (e1..eN) suitable for System 1 fast decision making.
"""

from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class ScannedElement(BaseModel):
    """Represents an interactive candidate element extracted from the webpage."""
    ref: str = Field(description="Unique short reference ID, e.g. e1, e2")
    tag: str = Field(description="HTML tag name, e.g. input, button, a")
    role: str = Field(description="ARIA role, e.g. searchbox, button, link, textbox")
    name: str = Field(default="", description="Visible text or accessible label")
    placeholder: str = Field(default="", description="Placeholder attribute if input")
    value: str = Field(default="", description="Current value if input")
    selector: str = Field(description="Usable CSS or ID selector for Playwright execution")
    bbox: dict[str, float] = Field(default_factory=dict, description="Bounding box rect {x, y, w, h}")

    @property
    def description(self) -> str:
        """Compact 1-line description formatted for Jev prompt criteria."""
        if self.tag in ("input", "textarea") or self.role in ("searchbox", "textbox"):
            parts = [f"<{self.tag} role='{self.role}' (Editable Input Field)>"]
            if self.name and self.name not in ("搜索输入框", "文本输入框"):
                parts.append(f"label='{self.name[:35]}'")
            elif self.name:
                parts.append(f"role_desc='{self.name}'")
            if self.placeholder:
                parts.append(f"placeholder='{self.placeholder[:35]}' (recommendation hint)")
            if self.value:
                parts.append(f"val='{self.value[:30]}'")
            parts.append(f"sel='{self.selector}'")
            return " | ".join(parts)

        parts = [f"<{self.tag} role='{self.role}'>"]
        if self.name:
            parts.append(f"text='{self.name[:40]}'")
        if self.placeholder:
            parts.append(f"placeholder='{self.placeholder[:40]}'")
        if self.value:
            parts.append(f"val='{self.value[:30]}'")
        parts.append(f"sel='{self.selector}'")
        return " | ".join(parts)


_ELEMENT_SCAN_JS = r"""
(options) => {
  const maxElements = Number(options?.maxElements || 50);
  
  const truncate = (val, max = 60) => {
    val = (val || '').replace(/\s+/g, ' ').trim();
    return val.length > max ? val.slice(0, max - 1) + '…' : val;
  };

  const safeCssEscape = (value) => {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(value);
    }
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  };

  const getBestSelector = (el) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
    if (el.id && !/^\d/.test(el.id) && !el.id.includes(':')) {
      return `#${safeCssEscape(el.id)}`;
    }
    const nameAttr = el.getAttribute('name');
    if (nameAttr) {
      return `${el.tagName.toLowerCase()}[name="${nameAttr.replace(/"/g, '\\"')}"]`;
    }
    const testId = el.getAttribute('data-testid') || el.getAttribute('data-test-id');
    if (testId) {
      return `[data-testid="${testId.replace(/"/g, '\\"')}"]`;
    }
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) {
      return `${el.tagName.toLowerCase()}[aria-label="${ariaLabel.replace(/"/g, '\\"')}"]`;
    }

    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 3) {
      let part = current.tagName.toLowerCase();
      if (current.id && !/^\d/.test(current.id)) {
        part = `#${safeCssEscape(current.id)}`;
        parts.unshift(part);
        break;
      }
      const classes = Array.from(current.classList || [])
        .filter(c => !c.includes('active') && !c.includes('hover') && !c.includes(':') && c.length < 25)
        .slice(0, 2)
        .map(c => `.${safeCssEscape(c)}`)
        .join('');
      if (classes) part += classes;
      parts.unshift(part);
      current = current.parentElement;
    }
    return parts.join(' > ');
  };

  const inferRole = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit.toLowerCase();
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const id = (el.id || '').toLowerCase();
    const cls = (el.className || '').toString().toLowerCase();
    const nameAttr = (el.getAttribute('name') || '').toLowerCase();

    if (tag === 'a' && el.hasAttribute('href')) return 'link';
    if (tag === 'button') return 'button';
    if (tag === 'select') return 'combobox';

    // Input & Textarea Role Detection
    if (tag === 'input' || tag === 'textarea') {
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'submit' || type === 'button') return 'button';
      if (type === 'search' || 
          id.includes('search') || id.includes('kw') || id.includes('chat') ||
          cls.includes('search') || cls.includes('chat') ||
          nameAttr.includes('search') || nameAttr.includes('wd') || nameAttr.includes('query')) {
        return 'searchbox';
      }
      return 'textbox';
    }
    if (el.hasAttribute('contenteditable')) return 'textbox';
    if (cls.includes('btn') || cls.includes('button')) return 'button';
    if (cls.includes('search-input') || cls.includes('search_input')) return 'searchbox';
    if (el.onclick || el.getAttribute('tabindex') === '0') return 'button';
    return 'generic';
  };

  const isVisible = (el) => {
    if (el.nodeType !== Node.ELEMENT_NODE) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    if (Number(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    if (!rect || rect.width <= 1 || rect.height <= 1) return false;
    if (rect.bottom < 0 || rect.right < 0) return false;
    return true;
  };

  const INTERACTIVE_ROLES = new Set([
    'button', 'link', 'textbox', 'searchbox', 'checkbox', 'radio',
    'combobox', 'tab', 'menuitem', 'option', 'switch'
  ]);

  const candidates = [];
  const allNodes = document.querySelectorAll(
    'a[href], button, input, textarea, select, [role], [onclick], [tabindex="0"], [contenteditable]'
  );

  for (const el of allNodes) {
    if (!isVisible(el)) continue;
    const role = inferRole(el);
    if (!INTERACTIVE_ROLES.has(role)) continue;

    const tag = el.tagName.toLowerCase();
    const rect = el.getBoundingClientRect();
    const isInput = (tag === 'input' || tag === 'textarea' || el.hasAttribute('contenteditable'));

    let name = '';
    if (isInput) {
      // For input/textarea, accessible name must NOT blindly grab innerText / placeholder recommendations
      if (el.getAttribute('aria-label')) {
        name = truncate(el.getAttribute('aria-label'), 50);
      } else if (el.id) {
        const labelEl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (labelEl && labelEl.innerText) {
          name = truncate(labelEl.innerText, 50);
        }
      }
      if (!name && el.getAttribute('title')) {
        name = truncate(el.getAttribute('title'), 50);
      }
      // If no explicit label, assign clear semantic role name
      if (!name) {
        const idLower = (el.id || '').toLowerCase();
        if (role === 'searchbox' || idLower.includes('search') || idLower.includes('kw') || idLower.includes('chat')) {
          name = '搜索输入框';
        } else {
          name = '文本输入框';
        }
      }
    } else {
      if (el.innerText) {
        name = truncate(el.innerText, 50);
      }
      if (!name && el.getAttribute('aria-label')) {
        name = truncate(el.getAttribute('aria-label'), 50);
      }
      if (!name && el.getAttribute('title')) {
        name = truncate(el.getAttribute('title'), 50);
      }
      if (!name && el.getAttribute('value')) {
        name = truncate(el.getAttribute('value'), 50);
      }
    }

    // Capture placeholder (or innerText recommendations in textarea)
    let rawPlaceholder = el.getAttribute('placeholder') || '';
    if (!rawPlaceholder && isInput && el.innerText && el.innerText.trim() !== name) {
      rawPlaceholder = el.innerText.trim();
    }
    const placeholder = truncate(rawPlaceholder, 50);
    const value = el.value || '';
    const selector = getBestSelector(el);

    candidates.push({
      tag,
      role,
      name,
      placeholder,
      value: truncate(value, 30),
      selector,
      bbox: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    });

    if (candidates.length >= maxElements) break;
  }

  return candidates;
}
"""


class ElementScanner:
    """Extracts and assigns refs to interactive elements on a Playwright Page."""

    def __init__(self, max_elements: int = 40) -> None:
        self.max_elements = max_elements

    async def scan_async(self, page: Any) -> List[ScannedElement]:
        """Asynchronously scan the given Playwright async page."""
        raw_elements = await page.evaluate(
            _ELEMENT_SCAN_JS,
            {"maxElements": self.max_elements}
        )
        return self._build_scanned_elements(raw_elements)

    def scan_sync(self, page: Any) -> List[ScannedElement]:
        """Synchronously scan the given Playwright sync page."""
        raw_elements = page.evaluate(
            _ELEMENT_SCAN_JS,
            {"maxElements": self.max_elements}
        )
        return self._build_scanned_elements(raw_elements)

    def _build_scanned_elements(self, raw_elements: list[dict[str, Any]]) -> List[ScannedElement]:
        results: List[ScannedElement] = []
        for i, raw in enumerate(raw_elements, start=1):
            ref = f"e{i}"
            results.append(
                ScannedElement(
                    ref=ref,
                    tag=raw.get("tag", "div"),
                    role=raw.get("role", "generic"),
                    name=raw.get("name", ""),
                    placeholder=raw.get("placeholder", ""),
                    value=raw.get("value", ""),
                    selector=raw.get("selector", ""),
                    bbox=raw.get("bbox", {}),
                )
            )
        return results
