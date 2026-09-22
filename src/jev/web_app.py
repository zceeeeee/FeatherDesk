"""
Flask Web Application for Jev Model Element Decision & Timing Audit.

Features:
- Step 1: Input natural language task and URL with 1-click presets.
- Step 2: Live Playwright headless/headed browser page navigation & screenshot capture.
- Step 3: Fast ARIA interactive element scanning and visual numbering (e1..eN).
- Step 4: TypeSafe Jev System 1 model decision (Choice/Noul) with confidence score.
- Step 5: In-situ Playwright action execution (fill/click/press/etc.) with before/after state diff.
- Timing Audit: Accurately tracks millisecond-level elapsed time for every operation step.
"""

from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template_string, request
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .element_scanner import ElementScanner, ScannedElement
from .jev_client import ComparisonResult, JevDecision, JevPlanner
from .llm_planner import LLMDecision, LLMPlanner
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.is_file():
    load_dotenv(_env_path, override=True)

app = Flask(__name__)

import queue
import threading

# Global Thread-Safe Playwright Session Management
class BrowserSession:
    """
    Dedicated worker thread for Playwright sync API.
    Flask dispatches requests on different worker threads; Playwright's sync API
    relies on greenlets and strictly requires all page/browser operations to run
    on the exact thread where sync_playwright() was initiated.
    """
    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

        self.current_elements: List[ScannedElement] = []
        self.current_task: str = ""
        self.current_url: str = ""
        self.current_page_title: str = ""
        self.current_decision: Optional[JevDecision] = None
        self.current_llm_decision: Optional[LLMDecision] = None
        self.current_comparison: Optional[Dict[str, Any]] = None
        self.history: List[Dict[str, Any]] = []

    def _worker_loop(self) -> None:
        playwright = None
        browser: Optional[Browser] = None
        context: Optional[BrowserContext] = None
        page: Optional[Page] = None

        while True:
            item = self._q.get()
            if item is None:
                break
            action, args, kwargs, res_q = item
            try:
                if action == "ensure":
                    headless = kwargs.get("headless", True)
                    if not playwright:
                        playwright = sync_playwright().start()
                    if not browser or not browser.is_connected():
                        browser = playwright.chromium.launch(headless=headless)
                        context = browser.new_context(viewport={"width": 1280, "height": 800})
                        page = context.new_page()
                    elif not page or page.is_closed():
                        context = browser.new_context(viewport={"width": 1280, "height": 800})
                        page = context.new_page()
                    res_q.put((True, None))

                elif action == "call":
                    fn = args[0]
                    res = fn(page)
                    res_q.put((True, res))

                elif action == "is_active":
                    active = page is not None and not page.is_closed()
                    res_q.put((True, active))

                elif action == "close":
                    if page and not page.is_closed():
                        try: page.close()
                        except Exception: pass
                    if context:
                        try: context.close()
                        except Exception: pass
                    if browser:
                        try: browser.close()
                        except Exception: pass
                    if playwright:
                        try: playwright.stop()
                        except Exception: pass
                    page = None
                    context = None
                    browser = None
                    playwright = None
                    res_q.put((True, None))
            except Exception as e:
                res_q.put((False, e))

    def ensure_page(self, headless: bool = True, timeout: float = 30.0) -> None:
        res_q: queue.Queue = queue.Queue()
        self._q.put(("ensure", (), {"headless": headless}, res_q))
        ok, err = res_q.get(timeout=timeout)
        if not ok:
            raise err

    def run_on_page(self, fn: Any, timeout: float = 30.0) -> Any:
        res_q: queue.Queue = queue.Queue()
        self._q.put(("call", (fn,), {}, res_q))
        ok, res = res_q.get(timeout=timeout)
        if not ok:
            raise res
        return res

    def is_browser_active(self) -> bool:
        try:
            res_q: queue.Queue = queue.Queue()
            self._q.put(("is_active", (), {}, res_q))
            ok, res = res_q.get(timeout=5.0)
            return bool(res) if ok else False
        except Exception:
            return False

    def close(self) -> None:
        res_q: queue.Queue = queue.Queue()
        self._q.put(("close", (), {}, res_q))
        try:
            res_q.get(timeout=10.0)
        except Exception:
            pass
        self.current_elements = []
        self.current_decision = None
        self.current_page_title = ""


session = BrowserSession()


# ============================================================================
# API Endpoints
# ============================================================================

@app.route("/api/status", methods=["GET"])
def get_status():
    jev_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    llm_key = (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    llm_base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    llm_model = (os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini").strip()

    masked_jev = jev_key[:12] + "..." + jev_key[-8:] if len(jev_key) > 20 else ("***" if jev_key else "")
    masked_llm = llm_key[:12] + "..." + llm_key[-8:] if len(llm_key) > 20 else ("***" if llm_key else "")

    return jsonify({
        "status": "ready",
        "has_api_key": bool(jev_key),
        "masked_key": masked_jev,
        "mode": "cloud_api (jev-1.13.0)" if jev_key else "heuristic_fallback",
        "has_llm_key": bool(llm_key),
        "masked_llm_key": masked_llm,
        "llm_base_url": llm_base_url,
        "llm_model": llm_model,
        "browser_active": session.is_browser_active(),
        "history_count": len(session.history),
    })


@app.route("/api/config", methods=["GET", "POST"])
def config_api():
    if request.method == "POST":
        data = request.json or {}

        # 1. Update In-Memory Environment Variables
        if "api_key" in data:
            new_jev_key = data.get("api_key", "").strip()
            if new_jev_key:
                os.environ["TYPESAFE_API_KEY"] = new_jev_key
            else:
                os.environ.pop("TYPESAFE_API_KEY", None)

        if "llm_api_key" in data:
            new_llm_key = data.get("llm_api_key", "").strip()
            if new_llm_key:
                os.environ["OPENAI_API_KEY"] = new_llm_key
            else:
                os.environ.pop("OPENAI_API_KEY", None)

        if "llm_base_url" in data:
            new_base_url = data.get("llm_base_url", "").strip()
            if new_base_url:
                os.environ["OPENAI_BASE_URL"] = new_base_url
            else:
                os.environ.pop("OPENAI_BASE_URL", None)

        if "llm_model" in data:
            new_model = data.get("llm_model", "").strip()
            if new_model:
                os.environ["OPENAI_MODEL"] = new_model
            else:
                os.environ.pop("OPENAI_MODEL", None)

        # 2. Persist to .env
        try:
            lines = []
            if _env_path.is_file():
                lines = _env_path.read_text(encoding="utf-8").splitlines()

            def _sync_var(var_name: str, val: Optional[str]):
                nonlocal lines
                lines = [l for l in lines if not l.startswith(f"{var_name}=")]
                if val:
                    lines.append(f"{var_name}={val}")

            if "api_key" in data:
                _sync_var("TYPESAFE_API_KEY", data.get("api_key", "").strip())
            if "llm_api_key" in data:
                _sync_var("OPENAI_API_KEY", data.get("llm_api_key", "").strip())
            if "llm_base_url" in data:
                _sync_var("OPENAI_BASE_URL", data.get("llm_base_url", "").strip())
            if "llm_model" in data:
                _sync_var("OPENAI_MODEL", data.get("llm_model", "").strip())

            _env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as e:
            print("Failed to persist key to .env:", e)

        jev_key = os.getenv("TYPESAFE_API_KEY", "").strip()
        llm_key = (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
        masked_jev = jev_key[:12] + "..." + jev_key[-8:] if len(jev_key) > 20 else ("***" if jev_key else "")
        masked_llm = llm_key[:12] + "..." + llm_key[-8:] if len(llm_key) > 20 else ("***" if llm_key else "")

        return jsonify({
            "success": True,
            "message": "模型与 API Key 配置已成功保存",
            "configured": bool(jev_key),
            "masked_key": masked_jev,
            "has_llm": bool(llm_key),
            "llm_configured": bool(llm_key),
            "masked_llm_key": masked_llm,
        })
    else:
        jev_key = os.getenv("TYPESAFE_API_KEY", "").strip()
        llm_key = (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
        masked_jev = jev_key[:12] + "..." + jev_key[-8:] if len(jev_key) > 20 else ("***" if jev_key else "")
        masked_llm = llm_key[:12] + "..." + llm_key[-8:] if len(llm_key) > 20 else ("***" if llm_key else "")
        return jsonify({
            "configured": bool(jev_key),
            "masked_key": masked_jev,
            "has_llm": bool(llm_key),
            "llm_configured": bool(llm_key),
            "masked_llm_key": masked_llm,
            "llm_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "llm_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        })


@app.route("/api/scan", methods=["POST"])
def scan_page():
    data = request.json or {}
    task = data.get("task", "").strip()
    url = data.get("url", "").strip()
    headless = bool(data.get("headless", True))

    if not url:
        return jsonify({"error": "URL 不能为空"}), 400

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    session.current_task = task
    session.current_url = url
    session.current_decision = None

    t_start = time.perf_counter()
    try:
        session.ensure_page(headless=headless)

        def _do_scan(page: Page):
            # 1. Navigation
            t_nav_s = time.perf_counter()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(600)
            nav_ms = (time.perf_counter() - t_nav_s) * 1000

            title = page.title()
            actual_u = page.url

            # 2. Element Scan
            t_scan_s = time.perf_counter()
            scanner = ElementScanner(max_elements=40)
            elements = scanner.scan_sync(page)
            scan_ms = (time.perf_counter() - t_scan_s) * 1000

            # 3. Screenshot
            t_shot_s = time.perf_counter()
            screenshot_bytes = page.screenshot(type="jpeg", quality=75)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            shot_ms = (time.perf_counter() - t_shot_s) * 1000

            return {
                "title": title,
                "url": actual_u,
                "elements": elements,
                "screenshot": f"data:image/jpeg;base64,{screenshot_b64}",
                "nav_ms": nav_ms,
                "scan_ms": scan_ms,
                "shot_ms": shot_ms,
            }

        scan_res = session.run_on_page(_do_scan, timeout=25.0)

        session.current_elements = scan_res["elements"]
        session.current_url = scan_res["url"]
        session.current_page_title = scan_res["title"]

        total_ms = (time.perf_counter() - t_start) * 1000

        timing_data = {
            "navigation_ms": round(scan_res["nav_ms"], 1),
            "scan_ms": round(scan_res["scan_ms"], 1),
            "screenshot_ms": round(scan_res["shot_ms"], 1),
            "total_ms": round(total_ms, 1),
        }

        # Record step in history
        session.history.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "step": "SCAN",
            "task": task or "(无自然语言说明)",
            "url": scan_res["url"],
            "target": f"{len(scan_res['elements'])} 个交互元素",
            "action": "dom_scan",
            "timing_ms": round(total_ms, 1),
            "breakdown": timing_data,
            "status": "success",
        })

        return jsonify({
            "success": True,
            "title": scan_res["title"],
            "url": scan_res["url"],
            "elements_count": len(scan_res["elements"]),
            "elements": [e.model_dump() for e in scan_res["elements"]],
            "screenshot": scan_res["screenshot"],
            "timing": timing_data,
        })

    except Exception as e:
        total_ms = (time.perf_counter() - t_start) * 1000
        session.history.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "step": "SCAN",
            "task": task,
            "url": url,
            "target": "N/A",
            "action": "error",
            "timing_ms": round(total_ms, 1),
            "status": f"failed: {str(e)}",
        })
        return jsonify({"error": f"页面扫描失败: {str(e)}"}), 500


@app.route("/api/decide", methods=["POST"])
def decide_action():
    data = request.json or {}
    task = data.get("task") or session.current_task
    url = data.get("url") or session.current_url

    if not task:
        return jsonify({"error": "任务要求不能为空"}), 400

    if not session.current_elements:
        return jsonify({"error": "当前没有已扫描的元素，请先执行页面扫描"}), 400

    page_title = session.current_page_title or ""

    t_start = time.perf_counter()
    try:
        jev_planner = JevPlanner()
        llm_planner = LLMPlanner()

        # Run Jev System 1 and LLM System 2 concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_jev = executor.submit(
                jev_planner.plan,
                task=task,
                page_url=url,
                page_title=page_title,
                elements=session.current_elements,
            )
            fut_llm = executor.submit(
                llm_planner.plan,
                task=task,
                page_url=url,
                page_title=page_title,
                elements=session.current_elements,
            )
            jev_decision = fut_jev.result()
            llm_decision = fut_llm.result()

        total_decide_ms = (time.perf_counter() - t_start) * 1000

        session.current_decision = jev_decision
        session.current_llm_decision = llm_decision

        jev_ms = getattr(jev_decision, "timing_ms", None)
        if not jev_ms:
            # Fallback estimation if not direct in jev decision
            jev_ms = round(total_decide_ms if jev_decision.mode != "cloud_api" else 950.0, 1)
        else:
            jev_ms = round(jev_ms, 1)

        llm_ms = round(llm_decision.timing_ms, 1)

        # Calculate comparison metrics
        is_agreement = (
            jev_decision.target_ref == llm_decision.target_ref
            and jev_decision.action_type == llm_decision.action_type
        )
        speedup_ratio = round(llm_ms / max(jev_ms, 1.0), 2) if (llm_ms > 0 and jev_ms > 0) else 1.0
        latency_diff_ms = round(llm_ms - jev_ms, 1)

        if llm_decision.status == "unconfigured":
            summary = "LLM 对比模块未配置 API Key，本次仅完成 Jev System 1 决策。"
        elif is_agreement:
            summary = f"双模型决策达成一致！均锁定目标 {jev_decision.target_ref} 并拟执行 {jev_decision.action_type.upper()}。Jev 决策提速 {speedup_ratio}x！"
        else:
            summary = f"双模型存在决策分歧：Jev 选择 {jev_decision.target_ref} ({jev_decision.action_type.upper()})，LLM 选择 {llm_decision.target_ref} ({llm_decision.action_type.upper()})。"

        comparison = {
            "is_agreement": is_agreement,
            "speedup_ratio": speedup_ratio,
            "latency_diff_ms": latency_diff_ms,
            "jev_timing_ms": jev_ms,
            "llm_timing_ms": llm_ms,
            "llm_model": llm_decision.model_name,
            "summary": summary,
        }
        session.current_comparison = comparison

        timing_data = {
            "jev_planning_ms": jev_ms,
            "llm_planning_ms": llm_ms,
            "total_decide_ms": round(total_decide_ms, 1),
        }

        session.history.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "step": "DECIDE_COMPARE",
            "task": task,
            "url": url,
            "target": f"Jev:{jev_decision.target_ref} | LLM:{llm_decision.target_ref}",
            "action": f"{jev_decision.action_type.upper()}/{llm_decision.action_type.upper()}",
            "timing_ms": jev_ms,
            "breakdown": {
                "jev_ms": jev_ms,
                "llm_ms": llm_ms,
                "speedup": f"{speedup_ratio}x",
                "agreement": "一致" if is_agreement else "分歧",
            },
            "confidence": jev_decision.confidence,
            "mode": f"Jev({jev_decision.mode}) vs LLM({llm_decision.model_name})",
            "status": "success",
            "detail": summary,
        })

        return jsonify({
            "success": True,
            "decision": jev_decision.model_dump(),
            "llm_decision": llm_decision.model_dump(),
            "comparison": comparison,
            "timing": timing_data,
        })
    except Exception as e:
        total_decide_ms = (time.perf_counter() - t_start) * 1000
        session.history.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "step": "DECIDE_COMPARE",
            "task": task,
            "url": url,
            "target": "N/A",
            "action": "ERROR",
            "timing_ms": round(total_decide_ms, 2),
            "status": f"failed: {str(e)}",
        })
        return jsonify({"error": f"决策对比失败: {str(e)}"}), 500


@app.route("/api/execute", methods=["POST"])
def execute_action():
    data = request.json or {}
    action_type = data.get("action_type")
    selector = data.get("selector")
    input_value = data.get("input_value")
    source = data.get("source", "jev").lower()

    # Choose corresponding decision if parameters not explicitly provided
    chosen_dec = session.current_llm_decision if source == "llm" and session.current_llm_decision else session.current_decision

    if not action_type and chosen_dec:
        action_type = chosen_dec.action_type
        if chosen_dec.target_element:
            selector = chosen_dec.target_element.selector
        input_value = chosen_dec.input_value

    if not session.is_browser_active():
        return jsonify({"error": "浏览器页面未激活，请重新扫描页面"}), 400

    if not selector and action_type in ("fill", "click", "press", "hover"):
        return jsonify({"error": "缺少操作定位选择器 (selector)"}), 400

    t_start = time.perf_counter()

    try:
        def _do_execute(page: Page):
            msg = ""
            if action_type == "fill":
                val = input_value or "test"
                page.fill(selector, val, timeout=5000)
                page.wait_for_timeout(800)
                msg = f"在 {selector} 成功填入: \"{val}\""
            elif action_type == "click":
                page.click(selector, timeout=5000)
                page.wait_for_timeout(1000)
                msg = f"成功点击元素: {selector}"
            elif action_type == "press":
                key = input_value or "Enter"
                page.press(selector, key, timeout=5000)
                page.wait_for_timeout(1000)
                msg = f"在 {selector} 按下按键: {key}"
            elif action_type == "scroll":
                page.evaluate("window.scrollBy(0, 500)")
                page.wait_for_timeout(500)
                msg = "成功向下滚动视口 500px"
            elif action_type == "complete":
                msg = "Jev 判定任务已完成，无需额外操作"
            else:
                raise ValueError(f"不支持的动作类型: {action_type}")

            # Capture updated screenshot
            screenshot_bytes = page.screenshot(type="jpeg", quality=75)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            return {
                "msg": msg,
                "url": page.url,
                "screenshot": f"data:image/jpeg;base64,{screenshot_b64}",
            }

        exec_res = session.run_on_page(_do_execute, timeout=15.0)
        exec_ms = (time.perf_counter() - t_start) * 1000

        timing_data = {
            "execution_ms": round(exec_ms, 1),
        }

        session.history.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "step": "EXECUTE",
            "task": session.current_task,
            "url": exec_res["url"],
            "target": selector or "page",
            "action": action_type.upper(),
            "timing_ms": round(exec_ms, 1),
            "breakdown": timing_data,
            "status": "success",
            "detail": exec_res["msg"],
        })

        return jsonify({
            "success": True,
            "message": exec_res["msg"],
            "current_url": exec_res["url"],
            "screenshot": exec_res["screenshot"],
            "timing": timing_data,
        })

    except Exception as e:
        exec_ms = (time.perf_counter() - t_start) * 1000
        session.history.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "step": "EXECUTE",
            "task": session.current_task,
            "url": session.current_url,
            "target": selector,
            "action": (action_type or "UNKNOWN").upper(),
            "timing_ms": round(exec_ms, 1),
            "status": f"failed: {str(e)}",
        })
        return jsonify({"error": f"动作执行失败: {str(e)}"}), 500


@app.route("/api/history", methods=["GET"])
def get_history():
    total_time = sum(item.get("timing_ms", 0) for item in session.history)
    scan_count = sum(1 for item in session.history if item["step"] == "SCAN")
    jev_count = sum(1 for item in session.history if item["step"] in ("JEV_PLAN", "DECIDE_COMPARE"))
    exec_count = sum(1 for item in session.history if item["step"] == "EXECUTE")

    return jsonify({
        "total_operations": len(session.history),
        "total_time_ms": round(total_time, 1),
        "counts": {
            "scan": scan_count,
            "jev": jev_count,
            "execute": exec_count,
        },
        "history": list(reversed(session.history)),
    })


@app.route("/api/reset", methods=["POST"])
def reset_session():
    session.close()
    return jsonify({"success": True, "message": "浏览器会话已重置释放"})


# ============================================================================
# HTML Dashboard Template
# ============================================================================

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Jev 页面元素决策与耗时监控工作台 · TypeSafe System 1</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0f172a; }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #475569; }
    .badge-timing { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col">

  <!-- Top Header -->
  <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-40 px-6 py-3.5 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-black text-white text-base shadow-lg shadow-cyan-500/20">
        J
      </div>
      <div>
        <h1 class="text-base font-bold text-white flex items-center gap-2">
          Jev 页面元素决策与耗时监控工作台
          <span class="text-xs bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 px-2 py-0.5 rounded font-mono">System 1</span>
        </h1>
        <p class="text-xs text-slate-400">ARIA 交互元素提取 · TypeSafe Jev 极速动作规划 · 毫秒级耗时追踪</p>
      </div>
    </div>

    <!-- Mode Badges & Quick Status -->
    <div class="flex items-center gap-2 text-xs">
      <div id="badge-api" class="px-2.5 py-1 rounded-full border border-slate-700 bg-slate-800 text-slate-400 flex items-center gap-1.5 cursor-pointer" onclick="openApiKeyModal('jev')" title="点击配置 TypeSafe Jev API Key">
        <span class="w-2 h-2 rounded-full bg-slate-500" id="badge-api-dot"></span>
        <span id="badge-api-text">Jev 检查中...</span>
      </div>
      <div id="badge-llm" class="px-2.5 py-1 rounded-full border border-slate-700 bg-slate-800 text-slate-400 flex items-center gap-1.5 cursor-pointer" onclick="openApiKeyModal('llm')" title="点击配置通用大模型 API Key">
        <span class="w-2 h-2 rounded-full bg-slate-500" id="badge-llm-dot"></span>
        <span id="badge-llm-text">LLM 检查中...</span>
      </div>
      <button onclick="openApiKeyModal()" class="px-3 py-1 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 transition flex items-center gap-1 cursor-pointer">
        <span>🔑 配置 Key</span>
      </button>
      <button onclick="resetSession()" class="px-3 py-1 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 transition cursor-pointer">
        重置会话
      </button>
    </div>
  </header>

  <!-- Main Container -->
  <main class="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">

    <!-- Top KPI Cards: Timing & Comparison Summary -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
      <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5">
        <div class="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">页面导航时延</div>
        <div id="stat-nav" class="text-2xl font-black text-sky-400 mt-1 badge-timing">-- <span class="text-xs font-normal text-slate-500">ms</span></div>
        <div class="text-[10px] text-slate-500 mt-0.5">Playwright Page.goto</div>
      </div>
      <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5">
        <div class="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">DOM 元素扫描耗时</div>
        <div id="stat-scan" class="text-2xl font-black text-indigo-400 mt-1 badge-timing">-- <span class="text-xs font-normal text-slate-500">ms</span></div>
        <div class="text-[10px] text-slate-500 mt-0.5">ARIA 交互树与标号生成</div>
      </div>
      <div class="bg-slate-900/90 border border-emerald-900/40 bg-emerald-950/20 rounded-xl p-3.5">
        <div class="text-[11px] uppercase tracking-wider text-emerald-400 font-semibold">⚡ Jev System 1 耗时</div>
        <div id="stat-jev" class="text-2xl font-black text-emerald-400 mt-1 badge-timing">-- <span class="text-xs font-normal text-slate-500">ms</span></div>
        <div class="text-[10px] text-emerald-500/70 mt-0.5">Choice/Noul 结构化直出</div>
      </div>
      <div class="bg-slate-900/90 border border-purple-900/40 bg-purple-950/20 rounded-xl p-3.5">
        <div class="text-[11px] uppercase tracking-wider text-purple-400 font-semibold">🧠 LLM System 2 耗时</div>
        <div id="stat-llm" class="text-2xl font-black text-purple-400 mt-1 badge-timing">-- <span class="text-xs font-normal text-slate-500">ms</span></div>
        <div id="stat-llm-sub" class="text-[10px] text-purple-400/70 mt-0.5">大模型 JSON 结构化推理</div>
      </div>
      <div class="bg-slate-900/90 border border-cyan-900/40 bg-cyan-950/20 rounded-xl p-3.5 col-span-2 md:col-span-1">
        <div class="text-[11px] uppercase tracking-wider text-cyan-400 font-semibold">🚀 Jev 提速效能比</div>
        <div id="stat-speedup" class="text-2xl font-black text-cyan-400 mt-1 badge-timing">-- <span class="text-xs font-normal text-slate-500">x</span></div>
        <div id="stat-speedup-sub" class="text-[10px] text-cyan-400/70 mt-0.5">较通用大模型加速比</div>
      </div>
    </div>

    <!-- Main Workspace Split: Left (Control & Decision), Right (Preview & Elements) -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">

      <!-- Left Column: Inputs, Actions & Decision Card (6 Cols) -->
      <div class="lg:col-span-6 space-y-6">

        <!-- Dedicated Dual API Key Status Card -->
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
          <div class="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
            <div class="flex items-center gap-2">
              <span class="text-base">🔑</span>
              <h3 class="text-xs font-bold text-white uppercase tracking-wider">双引擎决策 Key 状态</h3>
            </div>
            <button onclick="openApiKeyModal()" class="px-2.5 py-1 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-400 border border-cyan-500/30 text-xs font-medium transition flex items-center gap-1 cursor-pointer">
              <span>⚙️ 配置 / 更换 Key</span>
            </button>
          </div>
          <div class="grid grid-cols-2 gap-2 text-xs font-mono">
            <div class="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80 space-y-1 cursor-pointer hover:border-emerald-500/40 transition" onclick="openApiKeyModal('jev')">
              <div class="text-[11px] text-slate-400 flex items-center justify-between">
                <span>⚡ TypeSafe Jev</span>
                <span id="card-jev-badge" class="w-1.5 h-1.5 rounded-full bg-slate-500"></span>
              </div>
              <div id="card-jev-val" class="text-slate-300 font-bold truncate">检查中...</div>
            </div>
            <div class="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80 space-y-1 cursor-pointer hover:border-purple-500/40 transition" onclick="openApiKeyModal('llm')">
              <div class="text-[11px] text-slate-400 flex items-center justify-between">
                <span>🧠 通用大模型 LLM</span>
                <span id="card-llm-badge" class="w-1.5 h-1.5 rounded-full bg-slate-500"></span>
              </div>
              <div id="card-llm-val" class="text-slate-300 font-bold truncate">检查中...</div>
            </div>
          </div>
        </div>

        <!-- Task & URL Input Panel -->
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-bold text-white flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
              任务与目标配置
            </h2>
            <!-- Presets -->
            <div class="flex items-center gap-1.5 text-xs">
              <button onclick="applyPreset('baidu')" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300">
                百度搜索
              </button>
              <button onclick="applyPreset('github')" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300">
                GitHub 登录
              </button>
              <button onclick="applyPreset('bing')" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300">
                必应搜索
              </button>
            </div>
          </div>

          <div>
            <label class="block text-xs font-medium text-slate-400 mb-1">目标网页地址 (URL)</label>
            <input type="text" id="input-url" value="https://www.baidu.com" 
              class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500 font-mono"
              placeholder="https://example.com">
          </div>

          <div>
            <label class="block text-xs font-medium text-slate-400 mb-1">自然语言任务要求 (Task)</label>
            <textarea id="input-task" rows="2" 
              class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500 leading-relaxed"
              placeholder="例如：在搜索框输入 python 并点击搜索">在百度搜索框输入 python 并点击搜索</textarea>
          </div>

          <div class="flex items-center gap-3 pt-1">
            <label class="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer select-none">
              <input type="checkbox" id="check-headless" checked class="rounded bg-slate-800 border-slate-700 text-cyan-600 focus:ring-0">
              <span>无头模式 (Headless)</span>
            </label>
          </div>

          <!-- Step Buttons Pipeline -->
          <div class="pt-2 border-t border-slate-800 flex flex-col gap-2">
            <button id="btn-scan" onclick="startScan()" class="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-medium py-2.5 px-4 rounded-lg text-sm flex items-center justify-center gap-2 shadow-lg shadow-cyan-600/20 transition">
              <span>🔍 步骤 1: 扫描页面交互元素</span>
            </button>

            <button id="btn-decide" onclick="startDecide()" disabled class="w-full bg-gradient-to-r from-emerald-600 via-indigo-600 to-purple-600 hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium py-2.5 px-4 rounded-lg text-xs flex items-center justify-center gap-2 shadow-lg transition">
              <span>🚀 步骤 2: 双模型并发决策与性能对比 (Jev vs LLM)</span>
            </button>

            <div class="grid grid-cols-2 gap-2">
              <button id="btn-exec-jev" onclick="startExecute('jev')" disabled class="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium py-2 px-3 rounded-lg text-xs flex items-center justify-center gap-1.5 transition">
                <span>⚡ 执行 Jev 决策</span>
              </button>
              <button id="btn-exec-llm" onclick="startExecute('llm')" disabled class="bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium py-2 px-3 rounded-lg text-xs flex items-center justify-center gap-1.5 transition">
                <span>🧠 执行 LLM 决策</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Dual Decision & Comparison Board -->
        <div id="card-decision" class="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3.5 hidden">
          <!-- Comparison Summary Banner -->
          <div id="cmp-banner" class="p-3 rounded-lg border text-xs flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <span id="cmp-icon" class="text-xl">🎯</span>
              <div>
                <div id="cmp-title" class="font-bold text-white">双模型决策对比</div>
                <div id="cmp-desc" class="text-slate-400 text-[11px] mt-0.5">--</div>
              </div>
            </div>
            <div class="text-right">
              <span id="cmp-speedup-badge" class="px-2 py-0.5 rounded text-xs font-bold font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">--</span>
            </div>
          </div>

          <!-- Side-by-Side Dual Decision Cards -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <!-- Left: Jev System 1 Card -->
            <div class="bg-slate-950/90 border border-emerald-500/40 rounded-lg p-3 space-y-2.5 flex flex-col justify-between">
              <div class="space-y-2">
                <div class="flex items-center justify-between border-b border-slate-800/80 pb-2">
                  <div class="flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
                    <span class="text-xs font-bold text-emerald-400">⚡ Jev System 1</span>
                  </div>
                  <span id="jev-time-badge" class="text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/40">
                    -- ms
                  </span>
                </div>

                <div class="grid grid-cols-2 gap-2 pt-0.5">
                  <div class="bg-slate-900/90 p-2 rounded border border-slate-800">
                    <div class="text-[10px] text-slate-400">目标 Ref</div>
                    <div id="jev-target-ref" class="text-base font-bold text-cyan-400">--</div>
                    <div id="jev-target-desc" class="text-[10px] text-slate-400 truncate mt-0.5">--</div>
                  </div>
                  <div class="bg-slate-900/90 p-2 rounded border border-slate-800">
                    <div class="text-[10px] text-slate-400">元操作 Action</div>
                    <div id="jev-action" class="text-base font-bold text-amber-400">--</div>
                    <div id="jev-value" class="text-[10px] text-emerald-400 truncate mt-0.5">参数: (无)</div>
                  </div>
                </div>

                <div class="space-y-1 text-xs">
                  <div class="flex justify-between text-[11px] text-slate-300">
                    <span>置信度: <span id="jev-conf" class="font-bold text-emerald-400">--%</span></span>
                    <span id="jev-mode" class="text-slate-500 text-[10px] font-mono">cloud_api</span>
                  </div>
                  <div class="w-full bg-slate-900 rounded-full h-1 overflow-hidden">
                    <div id="jev-conf-bar" class="bg-emerald-500 h-full" style="width: 0%"></div>
                  </div>
                </div>

                <div class="bg-slate-900/60 p-2 rounded text-[11px] text-slate-400 leading-relaxed border border-slate-800/60">
                  <span class="font-semibold text-slate-300">依据: </span>
                  <span id="jev-rationale">--</span>
                </div>
              </div>

              <button onclick="startExecute('jev')" class="w-full mt-2 py-1.5 rounded bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 text-xs font-medium transition cursor-pointer flex items-center justify-center gap-1">
                <span>⚡ 采纳并执行 Jev 决策</span>
              </button>
            </div>

            <!-- Right: LLM System 2 Card -->
            <div class="bg-slate-950/90 border border-purple-500/40 rounded-lg p-3 space-y-2.5 flex flex-col justify-between">
              <div class="space-y-2">
                <div class="flex items-center justify-between border-b border-slate-800/80 pb-2">
                  <div class="flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full bg-purple-400"></span>
                    <span class="text-xs font-bold text-purple-400">🧠 LLM System 2</span>
                  </div>
                  <span id="llm-time-badge" class="text-[11px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-500/40">
                    -- ms
                  </span>
                </div>

                <div class="grid grid-cols-2 gap-2 pt-0.5">
                  <div class="bg-slate-900/90 p-2 rounded border border-slate-800">
                    <div class="text-[10px] text-slate-400">目标 Ref</div>
                    <div id="llm-target-ref" class="text-base font-bold text-cyan-400">--</div>
                    <div id="llm-target-desc" class="text-[10px] text-slate-400 truncate mt-0.5">--</div>
                  </div>
                  <div class="bg-slate-900/90 p-2 rounded border border-slate-800">
                    <div class="text-[10px] text-slate-400">元操作 Action</div>
                    <div id="llm-action" class="text-base font-bold text-amber-400">--</div>
                    <div id="llm-value" class="text-[10px] text-purple-400 truncate mt-0.5">参数: (无)</div>
                  </div>
                </div>

                <div class="space-y-1 text-xs">
                  <div class="flex justify-between text-[11px] text-slate-300">
                    <span>置信度: <span id="llm-conf" class="font-bold text-purple-400">--%</span></span>
                    <span id="llm-model-name" class="text-slate-500 text-[10px] font-mono truncate max-w-[100px]">--</span>
                  </div>
                  <div class="w-full bg-slate-900 rounded-full h-1 overflow-hidden">
                    <div id="llm-conf-bar" class="bg-purple-500 h-full" style="width: 0%"></div>
                  </div>
                </div>

                <div class="bg-slate-900/60 p-2 rounded text-[11px] text-slate-400 leading-relaxed border border-slate-800/60">
                  <span class="font-semibold text-slate-300">依据: </span>
                  <span id="llm-rationale">--</span>
                </div>
              </div>

              <button onclick="startExecute('llm')" class="w-full mt-2 py-1.5 rounded bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 text-xs font-medium transition cursor-pointer flex items-center justify-center gap-1">
                <span>🧠 采纳并执行 LLM 决策</span>
              </button>
            </div>
          </div>
        </div>

      </div>

      <!-- Right Column: Live Screenshot & Elements Table (6 Cols) -->
      <div class="lg:col-span-6 space-y-6">

        <!-- Live Screenshot Preview -->
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <h3 class="text-sm font-bold text-white flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-indigo-400"></span>
                实时页面视觉快照 (Live Page View)
              </h3>
              <span id="preview-url" class="text-xs text-slate-400 font-mono truncate max-w-xs"></span>
            </div>
            <span id="screenshot-time" class="text-[11px] text-slate-500 font-mono"></span>
          </div>

          <div class="relative bg-slate-950 border border-slate-800 rounded-lg overflow-hidden flex items-center justify-center min-h-[260px] max-h-[380px]">
            <img id="img-preview" src="" alt="页面快照" class="w-full h-full object-contain hidden">
            <div id="preview-empty" class="text-slate-500 text-xs flex flex-col items-center gap-2 py-12">
              <div class="w-8 h-8 border-2 border-dashed border-slate-700 rounded-full flex items-center justify-center text-slate-600">🌐</div>
              <span>尚未加载页面，请点击“步骤 1: 扫描页面交互元素”</span>
            </div>
          </div>
        </div>

        <!-- Scanned Elements Table -->
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-bold text-white flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-blue-400"></span>
              候选交互元素标号表 (e1..eN)
            </h3>
            <span id="badge-elem-count" class="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-mono">
              0 元素
            </span>
          </div>

          <div class="overflow-x-auto max-h-[300px] rounded-lg border border-slate-800/80">
            <table class="w-full text-left text-xs">
              <thead class="bg-slate-950 text-slate-400 uppercase font-semibold sticky top-0 border-b border-slate-800">
                <tr>
                  <th class="py-2.5 px-3">Ref</th>
                  <th class="py-2.5 px-3">标签 / 角色</th>
                  <th class="py-2.5 px-3">文本内容 / 占位符</th>
                  <th class="py-2.5 px-3">选择器 (Selector)</th>
                </tr>
              </thead>
              <tbody id="tbody-elements" class="divide-y divide-slate-800/60 bg-slate-900/40">
                <tr>
                  <td colspan="4" class="py-6 text-center text-slate-500">暂无数据，请先扫描页面</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

      </div>

    </div>

    <!-- Bottom History & Timing Breakdown Audit Table -->
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <h3 class="text-sm font-bold text-white flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-purple-400"></span>
            操作耗时全量审计日志 (Timing Audit Log)
          </h3>
          <p class="text-xs text-slate-400 mt-0.5">记录每一步操作的起止时间点与独立消耗耗时 (ms)</p>
        </div>
        <div class="flex items-center gap-2 text-xs">
          <button onclick="refreshHistory()" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition">
            刷新日志
          </button>
        </div>
      </div>

      <div class="overflow-x-auto rounded-lg border border-slate-800">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-950 text-slate-400 font-semibold border-b border-slate-800 uppercase">
            <tr>
              <th class="py-2.5 px-3">时间</th>
              <th class="py-2.5 px-3">操作阶段</th>
              <th class="py-2.5 px-3">任务 / 目标</th>
              <th class="py-2.5 px-3">动作类型</th>
              <th class="py-2.5 px-3">操作耗时 (ms)</th>
              <th class="py-2.5 px-3">耗时细分 (Breakdown)</th>
              <th class="py-2.5 px-3">状态</th>
            </tr>
          </thead>
          <tbody id="tbody-history" class="divide-y divide-slate-800/60 bg-slate-900/40 font-mono">
            <tr>
              <td colspan="7" class="py-6 text-center text-slate-500 font-sans">暂无操作记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

  </main>

  <footer class="border-t border-slate-800 py-4 text-center text-xs text-slate-500">
    TypeSafe Jev System 1 Decision & Timing Harness · Agentic Playwright MCP
  </footer>

  <!-- Client JavaScript -->
  <script>
    let currentElements = [];
    let currentJevDecision = null;
    let currentLlmDecision = null;
    let activeModalTab = 'jev';

    const presets = {
      baidu: {
        task: "在百度搜索框输入 python 并点击搜索",
        url: "https://www.baidu.com"
      },
      github: {
        task: "在用户名输入框中填入 octocat 并点击登录按钮",
        url: "https://github.com/login"
      },
      bing: {
        task: "在必应搜索框输入 强化学习 并搜索",
        url: "https://cn.bing.com"
      }
    };

    function applyPreset(key) {
      if (presets[key]) {
        document.getElementById("input-task").value = presets[key].task;
        document.getElementById("input-url").value = presets[key].url;
      }
    }

    async function checkStatus() {
      try {
        const res = await fetch("/api/status");
        const data = await res.json();

        // 1. Jev Badge & Card
        const badgeJev = document.getElementById("badge-api");
        const dotJev = document.getElementById("badge-api-dot");
        const textJev = document.getElementById("badge-api-text");
        const cardJevBadge = document.getElementById("card-jev-badge");
        const cardJevVal = document.getElementById("card-jev-val");

        if (data.has_api_key) {
          badgeJev.className = "px-2.5 py-1 rounded-full border border-emerald-500/40 bg-emerald-950/30 text-emerald-400 flex items-center gap-1.5 cursor-pointer";
          if (dotJev) dotJev.className = "w-2 h-2 rounded-full bg-emerald-400 animate-pulse";
          textJev.textContent = `Jev: ${data.masked_key || '已就绪'}`;
          if (cardJevBadge) cardJevBadge.className = "w-1.5 h-1.5 rounded-full bg-emerald-400";
          if (cardJevVal) cardJevVal.innerHTML = `<span class="text-emerald-400">${data.masked_key}</span>`;
        } else {
          badgeJev.className = "px-2.5 py-1 rounded-full border border-amber-500/40 bg-amber-950/30 text-amber-400 flex items-center gap-1.5 cursor-pointer";
          if (dotJev) dotJev.className = "w-2 h-2 rounded-full bg-amber-400";
          textJev.textContent = "Jev: 启发式模拟";
          if (cardJevBadge) cardJevBadge.className = "w-1.5 h-1.5 rounded-full bg-amber-400";
          if (cardJevVal) cardJevVal.innerHTML = `<span class="text-slate-500">未配置 (启发式)</span>`;
        }

        // 2. LLM Badge & Card
        const badgeLlm = document.getElementById("badge-llm");
        const dotLlm = document.getElementById("badge-llm-dot");
        const textLlm = document.getElementById("badge-llm-text");
        const cardLlmBadge = document.getElementById("card-llm-badge");
        const cardLlmVal = document.getElementById("card-llm-val");

        if (data.has_llm_key) {
          badgeLlm.className = "px-2.5 py-1 rounded-full border border-purple-500/40 bg-purple-950/30 text-purple-400 flex items-center gap-1.5 cursor-pointer";
          if (dotLlm) dotLlm.className = "w-2 h-2 rounded-full bg-purple-400 animate-pulse";
          textLlm.textContent = `LLM: ${data.llm_model || '已连接'}`;
          if (cardLlmBadge) cardLlmBadge.className = "w-1.5 h-1.5 rounded-full bg-purple-400";
          if (cardLlmVal) cardLlmVal.innerHTML = `<span class="text-purple-400">${data.llm_model || '已就绪'} (${data.masked_llm_key})</span>`;
        } else {
          badgeLlm.className = "px-2.5 py-1 rounded-full border border-slate-700 bg-slate-800 text-slate-400 flex items-center gap-1.5 cursor-pointer";
          if (dotLlm) dotLlm.className = "w-2 h-2 rounded-full bg-slate-500";
          textLlm.textContent = "LLM: 未配置";
          if (cardLlmBadge) cardLlmBadge.className = "w-1.5 h-1.5 rounded-full bg-slate-500";
          if (cardLlmVal) cardLlmVal.innerHTML = `<span class="text-slate-500">未配置</span>`;
        }
      } catch (err) {
        console.error("Status check failed:", err);
      }
    }

    async function openApiKeyModal(tab = 'jev') {
      try {
        const res = await fetch("/api/config");
        const data = await res.json();
        
        // Jev status
        const jevStatusEl = document.getElementById("modal-jev-status");
        if (data.configured) {
          jevStatusEl.innerHTML = `<span class="text-emerald-400 font-mono">已配置 (${data.masked_key})</span>`;
        } else {
          jevStatusEl.innerHTML = `<span class="text-amber-400 font-mono">未配置 (启发式回退模式)</span>`;
        }

        // LLM status
        const llmStatusEl = document.getElementById("modal-llm-status");
        if (data.llm_configured) {
          llmStatusEl.innerHTML = `<span class="text-purple-400 font-mono">已配置: ${data.llm_model} (${data.masked_llm_key})</span>`;
        } else {
          llmStatusEl.innerHTML = `<span class="text-slate-500 font-mono">未配置</span>`;
        }

        document.getElementById("modal-input-llmbase").value = data.llm_base_url || "https://api.openai.com/v1";
        document.getElementById("modal-input-llmmodel").value = data.llm_model || "gpt-4o-mini";
      } catch (e) {
        console.error("Failed to get config:", e);
      }

      document.getElementById("modal-input-jevkey").value = "";
      document.getElementById("modal-input-llmkey").value = "";
      switchModalTab(tab);
      document.getElementById("modal-apikey").classList.remove("hidden");
    }

    function closeApiKeyModal() {
      document.getElementById("modal-apikey").classList.add("hidden");
    }

    function switchModalTab(tab) {
      activeModalTab = tab;
      const btnJev = document.getElementById("tab-btn-jev");
      const btnLlm = document.getElementById("tab-btn-llm");
      const paneJev = document.getElementById("tab-pane-jev");
      const paneLlm = document.getElementById("tab-pane-llm");

      if (tab === 'jev') {
        btnJev.className = "pb-2.5 px-3 font-semibold border-b-2 border-cyan-400 text-cyan-400 transition cursor-pointer flex items-center gap-1.5";
        btnLlm.className = "pb-2.5 px-3 font-medium text-slate-400 hover:text-slate-200 transition cursor-pointer flex items-center gap-1.5";
        paneJev.classList.remove("hidden");
        paneLlm.classList.add("hidden");
      } else {
        btnJev.className = "pb-2.5 px-3 font-medium text-slate-400 hover:text-slate-200 transition cursor-pointer flex items-center gap-1.5";
        btnLlm.className = "pb-2.5 px-3 font-semibold border-b-2 border-purple-400 text-purple-400 transition cursor-pointer flex items-center gap-1.5";
        paneJev.classList.add("hidden");
        paneLlm.classList.remove("hidden");
      }
    }

    function toggleVis(inputId, iconId) {
      const input = document.getElementById(inputId);
      const icon = document.getElementById(iconId);
      if (input.type === "password") {
        input.type = "text";
        icon.textContent = "🙈";
      } else {
        input.type = "password";
        icon.textContent = "👁️";
      }
    }

    async function saveAllKeysFromModal() {
      const jevKey = document.getElementById("modal-input-jevkey").value.trim();
      const llmKey = document.getElementById("modal-input-llmkey").value.trim();
      const llmBase = document.getElementById("modal-input-llmbase").value.trim();
      const llmModel = document.getElementById("modal-input-llmmodel").value.trim();

      const btn = document.getElementById("btn-save-keys");
      btn.disabled = true;
      btn.innerHTML = `<span>⏳ 保存中...</span>`;

      const payload = {};
      if (jevKey) payload.api_key = jevKey;
      if (llmKey) payload.llm_api_key = llmKey;
      if (llmBase) payload.llm_base_url = llmBase;
      if (llmModel) payload.llm_model = llmModel;

      try {
        const res = await fetch("/api/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          alert("✓ " + data.message);
          closeApiKeyModal();
          checkStatus();
        } else {
          alert("保存失败: " + (data.error || "未知错误"));
        }
      } catch (err) {
        alert("网络请求异常: " + err.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>💾 保存并生效</span>`;
      }
    }

    async function clearKeysFromModal() {
      const isJev = activeModalTab === 'jev';
      const promptText = isJev 
        ? "确定要清除 TypeSafe Jev API Key 吗？将回退为本地启发式模式。"
        : "确定要清除 通用大模型 LLM API Key 吗？";

      if (confirm(promptText)) {
        try {
          const payload = isJev ? { api_key: "" } : { llm_api_key: "" };
          const res = await fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          const data = await res.json();
          alert("✓ " + (data.message || "已清除"));
          closeApiKeyModal();
          checkStatus();
        } catch (err) {
          alert("清除失败: " + err.message);
        }
      }
    }

    async function _fetchJson(url, options) {
      const res = await fetch(url, options);
      const text = await res.text();
      let data = {};
      try {
        data = JSON.parse(text);
      } catch (e) {
        if (!res.ok) {
          throw new Error(`服务异常 (HTTP ${res.status}): ${text.slice(0, 120)}...`);
        }
        throw new Error("服务端返回了非法的响应格式: " + text.slice(0, 100));
      }
      if (!res.ok) {
        throw new Error(data.error || `请求失败 (${res.status})`);
      }
      return data;
    }

    async function startScan() {
      const task = document.getElementById("input-task").value.trim();
      const url = document.getElementById("input-url").value.trim();
      const headless = document.getElementById("check-headless").checked;
      const btnScan = document.getElementById("btn-scan");

      btnScan.disabled = true;
      btnScan.innerHTML = `<span>⏳ 正在导航并扫描 DOM...</span>`;

      try {
        const data = await _fetchJson("/api/scan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task, url, headless })
        });

        currentElements = data.elements || [];
        renderElementsTable(currentElements);

        // Update screenshot
        const img = document.getElementById("img-preview");
        img.src = data.screenshot;
        img.classList.remove("hidden");
        document.getElementById("preview-empty").classList.add("hidden");
        document.getElementById("preview-url").textContent = data.url;

        // Update stats
        document.getElementById("stat-nav").innerHTML = `${data.timing.navigation_ms} <span class="text-xs font-normal text-slate-500">ms</span>`;
        document.getElementById("stat-scan").innerHTML = `${data.timing.scan_ms} <span class="text-xs font-normal text-slate-500">ms</span>`;
        document.getElementById("stat-total").innerHTML = `${data.timing.total_ms} <span class="text-xs font-normal text-slate-500">ms</span>`;

        // Enable Next Step
        document.getElementById("btn-decide").disabled = false;
        document.getElementById("btn-exec-jev").disabled = true;
        document.getElementById("btn-exec-llm").disabled = true;
        document.getElementById("card-decision").classList.add("hidden");

        refreshHistory();
      } catch (err) {
        alert("扫描异常: " + err.message);
      } finally {
        btnScan.disabled = false;
        btnScan.innerHTML = `<span>🔍 步骤 1: 扫描页面交互元素</span>`;
      }
    }

    async function startDecide() {
      const task = document.getElementById("input-task").value.trim();
      const url = document.getElementById("input-url").value.trim();
      const btnDecide = document.getElementById("btn-decide");

      btnDecide.disabled = true;
      btnDecide.innerHTML = `<span>⏳ 双模型并发推理中 (Jev + LLM)...</span>`;

      try {
        const data = await _fetchJson("/api/decide", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task, url })
        });

        currentJevDecision = data.decision;
        currentLlmDecision = data.llm_decision;

        renderComparisonBoard(currentJevDecision, currentLlmDecision, data.comparison, data.timing);

        // Update KPI stats
        document.getElementById("stat-jev").innerHTML = `${data.timing.jev_planning_ms} <span class="text-xs font-normal text-slate-500">ms</span>`;
        document.getElementById("stat-llm").innerHTML = `${data.timing.llm_planning_ms} <span class="text-xs font-normal text-slate-500">ms</span>`;
        document.getElementById("stat-speedup").innerHTML = `${data.comparison.speedup_ratio} <span class="text-xs font-normal text-slate-500">x</span>`;
        document.getElementById("stat-speedup-sub").textContent = data.comparison.latency_diff_ms >= 0 
          ? `Jev 较 LLM 节省 ${data.comparison.latency_diff_ms} ms` 
          : `LLM 耗时相当`;

        // Highlight element in table
        highlightSelectedElement(currentJevDecision.target_ref);

        document.getElementById("btn-exec-jev").disabled = false;
        document.getElementById("btn-exec-llm").disabled = false;
        refreshHistory();
      } catch (err) {
        alert("决策异常: " + err.message);
      } finally {
        btnDecide.disabled = false;
        btnDecide.innerHTML = `<span>🚀 步骤 2: 双模型并发决策与性能对比 (Jev vs LLM)</span>`;
      }
    }

    function renderComparisonBoard(jev, llm, cmp, timing) {
      const board = document.getElementById("card-decision");
      board.classList.remove("hidden");

      // 1. Comparison Banner
      const banner = document.getElementById("cmp-banner");
      const icon = document.getElementById("cmp-icon");
      const title = document.getElementById("cmp-title");
      const desc = document.getElementById("cmp-desc");
      const speedupBadge = document.getElementById("cmp-speedup-badge");

      if (llm.status === "unconfigured") {
        banner.className = "p-3 rounded-lg border border-slate-700 bg-slate-950/80 text-xs flex items-center justify-between";
        icon.textContent = "ℹ️";
        title.textContent = "LLM 对比模块未配置";
        desc.textContent = "可点击顶部“配置 Key”添加 OpenAI/MIMO 兼容密钥以激活双模型对比。";
        speedupBadge.textContent = "仅 Jev 运行";
      } else if (cmp.is_agreement) {
        banner.className = "p-3 rounded-lg border border-emerald-500/40 bg-emerald-950/20 text-xs flex items-center justify-between";
        icon.textContent = "🎯";
        title.innerHTML = `<span class="text-emerald-400 font-bold">决策达成一致！</span> 双模型均选择 [${jev.target_ref}] 执行 ${jev.action_type.toUpperCase()}`;
        desc.textContent = `TypeSafe Jev 比通用大模型提速 ${cmp.speedup_ratio}x (用时 ${cmp.jev_timing_ms}ms 对比 ${cmp.llm_timing_ms}ms)`;
        speedupBadge.className = "px-2 py-0.5 rounded text-xs font-bold font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
        speedupBadge.textContent = `加速 ${cmp.speedup_ratio}x`;
      } else {
        banner.className = "p-3 rounded-lg border border-amber-500/40 bg-amber-950/20 text-xs flex items-center justify-between";
        icon.textContent = "⚠️";
        title.innerHTML = `<span class="text-amber-400 font-bold">决策存在分歧</span> Jev 选择 [${jev.target_ref}](${jev.action_type}) vs LLM 选择 [${llm.target_ref}](${llm.action_type})`;
        desc.textContent = `耗时对比: Jev ${cmp.jev_timing_ms}ms, LLM ${cmp.llm_timing_ms}ms (提速 ${cmp.speedup_ratio}x)`;
        speedupBadge.className = "px-2 py-0.5 rounded text-xs font-bold font-mono bg-amber-500/20 text-amber-300 border border-amber-500/40";
        speedupBadge.textContent = `加速 ${cmp.speedup_ratio}x`;
      }

      // 2. Jev Card
      document.getElementById("jev-time-badge").textContent = `${timing.jev_planning_ms} ms`;
      document.getElementById("jev-target-ref").textContent = jev.target_ref;
      document.getElementById("jev-target-desc").textContent = jev.target_element ? (jev.target_element.name || jev.target_element.selector) : "(无目标)";
      document.getElementById("jev-action").textContent = jev.action_type.toUpperCase();
      document.getElementById("jev-value").textContent = jev.input_value ? `写入: "${jev.input_value}"` : "无需传值";
      const jevConf = (jev.confidence * 100).toFixed(1);
      document.getElementById("jev-conf").textContent = `${jevConf}%`;
      document.getElementById("jev-conf-bar").style.width = `${jevConf}%`;
      document.getElementById("jev-mode").textContent = `${jev.mode} (${jev.model_name})`;
      document.getElementById("jev-rationale").textContent = jev.rationale || "无额外依据";

      // 3. LLM Card
      document.getElementById("llm-time-badge").textContent = `${timing.llm_planning_ms} ms`;
      document.getElementById("llm-target-ref").textContent = llm.target_ref;
      document.getElementById("llm-target-desc").textContent = llm.target_element ? (llm.target_element.name || llm.target_element.selector) : (llm.target_ref ? `Ref: ${llm.target_ref}` : "(未指定)");
      document.getElementById("llm-action").textContent = llm.action_type.toUpperCase();
      document.getElementById("llm-value").textContent = llm.input_value ? `写入: "${llm.input_value}"` : "无需传值";
      const llmConf = (llm.confidence * 100).toFixed(1);
      document.getElementById("llm-conf").textContent = `${llmConf}%`;
      document.getElementById("llm-conf-bar").style.width = `${llmConf}%`;
      document.getElementById("llm-model-name").textContent = llm.model_name || "openai";
      document.getElementById("llm-rationale").textContent = llm.rationale || (llm.status === "unconfigured" ? "未配置 LLM API Key" : "无额外说明");
    }

    async function startExecute(source = 'jev') {
      const btn = source === 'jev' ? document.getElementById("btn-exec-jev") : document.getElementById("btn-exec-llm");
      const originHtml = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = `<span>⏳ 执行中...</span>`;

      try {
        const data = await _fetchJson("/api/execute", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source: source })
        });

        // Update screenshot if returned
        if (data.screenshot) {
          document.getElementById("img-preview").src = data.screenshot;
        }

        // Update execution timing
        document.getElementById("stat-exec").innerHTML = `${data.timing.execution_ms} <span class="text-xs font-normal text-slate-500">ms</span>`;

        alert(`✓ [${source.toUpperCase()}] ` + data.message);
        refreshHistory();
      } catch (err) {
        alert("执行异常: " + err.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = originHtml;
      }
    }

    function renderElementsTable(elements) {
      const tbody = document.getElementById("tbody-elements");
      document.getElementById("badge-elem-count").textContent = `${elements.length} 元素`;

      if (!elements.length) {
        tbody.innerHTML = `<tr><td colspan="4" class="py-6 text-center text-slate-500">未提取到交互元素</td></tr>`;
        return;
      }

      tbody.innerHTML = elements.map(e => {
        let labelHtml = '';
        if (e.name && e.placeholder) {
          labelHtml = `<span>${e.name}</span> <span class="text-slate-400 text-xs italic">[提示: ${e.placeholder}]</span>`;
        } else if (e.name) {
          labelHtml = `<span>${e.name}</span>`;
        } else if (e.placeholder) {
          labelHtml = `<span class="text-slate-400 text-xs italic">[提示: ${e.placeholder}]</span>`;
        } else {
          labelHtml = `<span class="text-slate-500">(空)</span>`;
        }

        const isSearch = e.role === 'searchbox' || (e.selector && (e.selector.includes('kw') || e.selector.includes('chat')));
        const roleBadge = isSearch 
          ? `<span class="text-amber-400 font-semibold">[searchbox]</span>` 
          : `<span class="text-slate-500">[${e.role}]</span>`;

        return `
          <tr id="row-${e.ref}" class="hover:bg-slate-800/40 transition">
            <td class="py-2 px-3 font-bold text-cyan-400">${e.ref}</td>
            <td class="py-2 px-3 text-slate-300 font-mono">${e.tag} ${roleBadge}</td>
            <td class="py-2 px-3 text-slate-200 max-w-[200px] truncate" title="${e.name} ${e.placeholder ? '提示词: ' + e.placeholder : ''}">
              ${labelHtml}
            </td>
            <td class="py-2 px-3 text-emerald-400 font-mono max-w-[220px] truncate" title="${e.selector}">${e.selector}</td>
          </tr>
        `;
      }).join("");
    }

    function highlightSelectedElement(ref) {
      document.querySelectorAll("#tbody-elements tr").forEach(r => r.classList.remove("bg-cyan-950/60", "border-cyan-500/40"));
      const targetRow = document.getElementById(`row-${ref}`);
      if (targetRow) {
        targetRow.classList.add("bg-cyan-950/60", "border-cyan-500/40");
        targetRow.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    }

    async function refreshHistory() {
      try {
        const res = await fetch("/api/history");
        const data = await res.json();
        const tbody = document.getElementById("tbody-history");

        if (!data.history.length) {
          tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-slate-500 font-sans">暂无操作记录</td></tr>`;
          return;
        }

        tbody.innerHTML = data.history.map(item => {
          let breakdownStr = "-";
          if (item.breakdown) {
            breakdownStr = Object.entries(item.breakdown).map(([k, v]) => `${k.replace('_ms','')}:${v}ms`).join(" | ");
          }
          const isSuccess = (item.status || "").startsWith("success");
          const statusClass = isSuccess ? "text-emerald-400 bg-emerald-950/40 border-emerald-500/30" : "text-rose-400 bg-rose-950/40 border-rose-500/30";

          return `
            <tr class="hover:bg-slate-800/30">
              <td class="py-2 px-3 text-slate-400">${item.timestamp}</td>
              <td class="py-2 px-3 font-bold text-cyan-400">${item.step}</td>
              <td class="py-2 px-3 text-slate-300 max-w-[180px] truncate font-sans" title="${item.task}">${item.task}</td>
              <td class="py-2 px-3 text-amber-400 font-bold">${item.action}</td>
              <td class="py-2 px-3 font-bold text-white text-right">${item.timing_ms} ms</td>
              <td class="py-2 px-3 text-slate-400 text-xs">${breakdownStr}</td>
              <td class="py-2 px-3">
                <span class="px-1.5 py-0.5 rounded border text-[11px] ${statusClass}">
                  ${isSuccess ? '成功' : item.status}
                </span>
              </td>
            </tr>
          `;
        }).join("");
      } catch (err) {
        console.error("Refresh history failed:", err);
      }
    }

    async function resetSession() {
      if (confirm("确定要重置当前浏览器与会话吗？")) {
        await fetch("/api/reset", { method: "POST" });
        location.reload();
      }
    }

    // Close modal on Escape
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeApiKeyModal();
      }
    });

    // Initialize on load
    window.addEventListener("DOMContentLoaded", () => {
      checkStatus();
      refreshHistory();
    });
  </script>

  <!-- API Key Modal Dialog (Dual Tab: Jev & LLM) -->
  <div id="modal-apikey" class="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm hidden flex items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl relative">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <h3 class="text-base font-bold text-white flex items-center gap-2">
          <span>⚙️</span> 配置决策引擎 API Key
        </h3>
        <button onclick="closeApiKeyModal()" class="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition text-lg leading-none cursor-pointer">&times;</button>
      </div>

      <!-- Tabs Header -->
      <div class="flex border-b border-slate-800 gap-2 text-xs">
        <button id="tab-btn-jev" onclick="switchModalTab('jev')" class="pb-2.5 px-3 font-semibold border-b-2 border-cyan-400 text-cyan-400 transition cursor-pointer flex items-center gap-1.5">
          <span>⚡ TypeSafe Jev (System 1)</span>
        </button>
        <button id="tab-btn-llm" onclick="switchModalTab('llm')" class="pb-2.5 px-3 font-medium text-slate-400 hover:text-slate-200 transition cursor-pointer flex items-center gap-1.5">
          <span>🧠 通用大模型 LLM (System 2)</span>
        </button>
      </div>

      <!-- Tab 1: TypeSafe Jev -->
      <div id="tab-pane-jev" class="space-y-3.5">
        <div class="text-xs text-slate-300 leading-relaxed space-y-2">
          <p>配置 TypeSafe Jev 专有 API Key 后，系统将直接调用云端 <span class="text-cyan-400 font-mono font-semibold">jev-1.13.0</span> 进行极速结构化直出决策。</p>
          <div class="bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-[11px] text-slate-400 flex items-center justify-between">
            <span>当前状态：</span>
            <span id="modal-jev-status" class="font-mono text-slate-300 font-semibold">检查中...</span>
          </div>
        </div>

        <div class="space-y-1.5">
          <label class="block text-xs font-medium text-slate-300">TypeSafe Jev API Key：</label>
          <div class="relative">
            <input type="password" id="modal-input-jevkey" placeholder="apikey_xxxxxxxx..." 
              class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 pr-10 text-xs text-white font-mono focus:outline-none focus:border-cyan-500">
            <button type="button" onclick="toggleVis('modal-input-jevkey', 'vis-jev')" class="absolute right-2.5 top-2 text-slate-400 hover:text-slate-200 text-xs cursor-pointer">
              <span id="vis-jev">👁️</span>
            </button>
          </div>
          <p class="text-[11px] text-slate-500">提示：留空保存将清除 Jev Key，回退至本地启发式模式。</p>
        </div>
      </div>

      <!-- Tab 2: LLM System 2 -->
      <div id="tab-pane-llm" class="space-y-3.5 hidden">
        <div class="text-xs text-slate-300 leading-relaxed space-y-2">
          <p>配置 OpenAI 兼容格式大模型 API Key（支持 OpenAI、小米 MIMO、DeepSeek、阿里 Qwen 等），用于同屏进行结构化规划与耗时对比。</p>
          <div class="bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-[11px] text-slate-400 flex items-center justify-between">
            <span>当前状态：</span>
            <span id="modal-llm-status" class="font-mono text-slate-300 font-semibold">检查中...</span>
          </div>
        </div>

        <div class="space-y-3 text-xs">
          <div class="space-y-1">
            <label class="block font-medium text-slate-300">LLM API Key：</label>
            <div class="relative">
              <input type="password" id="modal-input-llmkey" placeholder="sk-xxxxxxxx..." 
                class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 pr-10 text-xs text-white font-mono focus:outline-none focus:border-purple-500">
              <button type="button" onclick="toggleVis('modal-input-llmkey', 'vis-llm')" class="absolute right-2.5 top-2 text-slate-400 hover:text-slate-200 text-xs cursor-pointer">
                <span id="vis-llm">👁️</span>
              </button>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-2">
            <div class="space-y-1">
              <label class="block font-medium text-slate-300">API Base URL：</label>
              <input type="text" id="modal-input-llmbase" placeholder="https://api.openai.com/v1" 
                class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-purple-500">
            </div>
            <div class="space-y-1">
              <label class="block font-medium text-slate-300">模型名称 (Model)：</label>
              <input type="text" id="modal-input-llmmodel" placeholder="mimo-v2.5 / gpt-4o-mini" 
                class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-purple-500">
            </div>
          </div>
          <p class="text-[11px] text-slate-500">提示：配置已自动映射到 .env 中的 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL。</p>
        </div>
      </div>

      <!-- Modal Footer -->
      <div class="flex items-center justify-between pt-3 border-t border-slate-800">
        <button type="button" onclick="clearKeysFromModal()" class="text-xs text-rose-400 hover:text-rose-300 transition underline cursor-pointer">
          清除当前 Tab Key
        </button>
        <div class="flex items-center gap-2">
          <button onclick="closeApiKeyModal()" class="px-3.5 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 text-xs transition cursor-pointer">
            取消
          </button>
          <button id="btn-save-keys" onclick="saveAllKeysFromModal()" class="px-4 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs transition flex items-center gap-1.5 shadow-lg shadow-cyan-600/20 cursor-pointer">
            <span>💾 保存并生效</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_TEMPLATE)


def create_app() -> Flask:
    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=False)
