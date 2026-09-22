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
from .jev_client import JevDecision, JevPlanner

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
    api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    masked_key = ""
    if api_key:
        masked_key = api_key[:12] + "..." + api_key[-8:] if len(api_key) > 20 else "***"
    return jsonify({
        "status": "ready",
        "has_api_key": bool(api_key),
        "masked_key": masked_key,
        "mode": "cloud_api (jev-1.13.0)" if api_key else "heuristic_fallback",
        "browser_active": session.is_browser_active(),
        "history_count": len(session.history),
    })


@app.route("/api/config", methods=["GET", "POST"])
def config_api():
    if request.method == "POST":
        data = request.json or {}
        new_key = data.get("api_key", "").strip()
        if new_key:
            os.environ["TYPESAFE_API_KEY"] = new_key
            try:
                lines = []
                if _env_path.is_file():
                    lines = _env_path.read_text(encoding="utf-8").splitlines()
                new_lines = [l for l in lines if not l.startswith("TYPESAFE_API_KEY=")]
                new_lines.append(f"TYPESAFE_API_KEY={new_key}")
                _env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            except Exception as e:
                print("Failed to persist key to .env:", e)
            masked = new_key[:12] + "..." + new_key[-8:] if len(new_key) > 20 else "***"
            return jsonify({"success": True, "message": "API Key 已成功配置并保存", "configured": True, "masked_key": masked})
        else:
            os.environ.pop("TYPESAFE_API_KEY", None)
            try:
                if _env_path.is_file():
                    lines = _env_path.read_text(encoding="utf-8").splitlines()
                    new_lines = [l for l in lines if not l.startswith("TYPESAFE_API_KEY=")]
                    _env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            except Exception as e:
                print("Failed to remove key from .env:", e)
            return jsonify({"success": True, "message": "已清除 API Key，系统已切换至本地启发式模拟模式", "configured": False, "masked_key": ""})
    else:
        api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
        masked = api_key[:12] + "..." + api_key[-8:] if len(api_key) > 20 else ("***" if api_key else "")
        return jsonify({"configured": bool(api_key), "masked_key": masked})


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
        planner = JevPlanner()
        decision = planner.plan(
            task=task,
            page_url=url,
            page_title=page_title,
            elements=session.current_elements,
        )
        jev_ms = (time.perf_counter() - t_start) * 1000
        session.current_decision = decision

        timing_data = {
            "jev_planning_ms": round(jev_ms, 2),
        }

        session.history.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "step": "JEV_PLAN",
            "task": task,
            "url": url,
            "target": f"{decision.target_ref} ({decision.target_element.selector if decision.target_element else ''})",
            "action": decision.action_type.upper(),
            "timing_ms": round(jev_ms, 2),
            "breakdown": timing_data,
            "confidence": decision.confidence,
            "mode": decision.mode,
            "status": "success",
        })

        return jsonify({
            "success": True,
            "decision": decision.model_dump(),
            "timing": timing_data,
        })
    except Exception as e:
        jev_ms = (time.perf_counter() - t_start) * 1000
        session.history.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "step": "JEV_PLAN",
            "task": task,
            "url": url,
            "target": "N/A",
            "action": "ERROR",
            "timing_ms": round(jev_ms, 2),
            "status": f"failed: {str(e)}",
        })
        return jsonify({"error": f"Jev 模型决策失败: {str(e)}"}), 500


@app.route("/api/execute", methods=["POST"])
def execute_action():
    data = request.json or {}
    action_type = data.get("action_type")
    selector = data.get("selector")
    input_value = data.get("input_value")

    # If parameters not passed explicitly, use current Jev decision
    if not action_type and session.current_decision:
        action_type = session.current_decision.action_type
        if session.current_decision.target_element:
            selector = session.current_decision.target_element.selector
        input_value = session.current_decision.input_value

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
    jev_count = sum(1 for item in session.history if item["step"] == "JEV_PLAN")
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

    <!-- Mode Badge & Quick Status -->
    <div class="flex items-center gap-2.5 text-xs">
      <div id="badge-api" class="px-3 py-1 rounded-full border border-slate-700 bg-slate-800 text-slate-400 flex items-center gap-1.5 cursor-pointer" onclick="openApiKeyModal()" title="点击查看或修改 API Key">
        <span class="w-2 h-2 rounded-full bg-slate-500" id="badge-api-dot"></span>
        <span id="badge-api-text">检查中...</span>
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

    <!-- Top KPI Cards: Timing Summary -->
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
      <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5">
        <div class="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Jev 决策时延</div>
        <div id="stat-jev" class="text-2xl font-black text-emerald-400 mt-1 badge-timing">-- <span class="text-xs font-normal text-slate-500">ms</span></div>
        <div class="text-[10px] text-slate-500 mt-0.5">Choice/Noul 结构化直出</div>
      </div>
      <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5">
        <div class="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">动作执行耗时</div>
        <div id="stat-exec" class="text-2xl font-black text-amber-400 mt-1 badge-timing">-- <span class="text-xs font-normal text-slate-500">ms</span></div>
        <div class="text-[10px] text-slate-500 mt-0.5">Playwright 原语与等待</div>
      </div>
      <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5 col-span-2 md:col-span-1">
        <div class="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">全闭环链路耗时</div>
        <div id="stat-total" class="text-2xl font-black text-purple-400 mt-1 badge-timing">-- <span class="text-xs font-normal text-slate-500">ms</span></div>
        <div class="text-[10px] text-slate-500 mt-0.5">端到端任务操作总用时</div>
      </div>
    </div>

    <!-- Main Workspace Split: Left (Control & Decision), Right (Preview & Elements) -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">

      <!-- Left Column: Inputs, Actions & Decision Card (5 Cols) -->
      <div class="lg:col-span-5 space-y-6">

        <!-- Dedicated API Key Configuration Card -->
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <div class="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-sm shadow-inner">
                🔑
              </div>
              <div>
                <h3 class="text-xs font-bold text-white uppercase tracking-wider">TypeSafe Jev API Key</h3>
                <div class="text-[11px] text-slate-400 mt-0.5" id="card-api-status-desc">正在检测密钥状态...</div>
              </div>
            </div>
            <button onclick="openApiKeyModal()" class="px-3 py-1.5 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-400 border border-cyan-500/30 text-xs font-medium transition flex items-center gap-1.5 shadow-sm active:scale-95 cursor-pointer">
              <span>⚙️ 配置 / 更换 Key</span>
            </button>
          </div>
          <!-- Quick Inline Preview -->
          <div class="text-xs font-mono px-3 py-2 rounded-lg bg-slate-950 border border-slate-800/80 flex items-center justify-between">
            <span class="text-slate-400">当前密钥：</span>
            <span id="card-api-key-val" class="text-slate-300">检测中...</span>
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

            <div class="grid grid-cols-2 gap-2">
              <button id="btn-decide" onclick="startDecide()" disabled class="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium py-2 px-3 rounded-lg text-xs flex items-center justify-center gap-1.5 transition">
                <span>🧠 步骤 2: Jev 智能决策</span>
              </button>
              <button id="btn-execute" onclick="startExecute()" disabled class="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium py-2 px-3 rounded-lg text-xs flex items-center justify-center gap-1.5 transition">
                <span>⚡ 步骤 3: 在线执行动作</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Jev Decision Card -->
        <div id="card-decision" class="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3 hidden">
          <div class="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <h3 class="text-sm font-bold text-white flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
              Jev 决策结果输出
            </h3>
            <span id="decision-time-badge" class="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded badge-timing">
              0.0 ms
            </span>
          </div>

          <div class="grid grid-cols-2 gap-3 pt-1">
            <div class="bg-slate-950 p-3 rounded-lg border border-slate-800/80">
              <div class="text-[11px] text-slate-400">目标元素 (Target Ref)</div>
              <div id="res-target-ref" class="text-xl font-bold text-cyan-400 mt-0.5">--</div>
              <div id="res-target-desc" class="text-[11px] text-slate-400 mt-1 truncate">--</div>
            </div>

            <div class="bg-slate-950 p-3 rounded-lg border border-slate-800/80">
              <div class="text-[11px] text-slate-400">拟执行元操作 (Action)</div>
              <div id="res-action" class="text-xl font-bold text-amber-400 mt-0.5">--</div>
              <div id="res-value" class="text-[11px] text-emerald-400 mt-1 truncate">参数: (无)</div>
            </div>
          </div>

          <div class="space-y-1.5 pt-1 text-xs">
            <div class="flex justify-between items-center text-slate-300">
              <span>决策置信度 (Confidence):</span>
              <span id="res-conf" class="font-bold text-emerald-400 badge-timing">--%</span>
            </div>
            <div class="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden">
              <div id="res-conf-bar" class="bg-emerald-500 h-full transition-all duration-500" style="width: 0%"></div>
            </div>
            <div class="flex justify-between text-[11px] text-slate-500 pt-1">
              <span>引擎: <span id="res-mode" class="text-slate-400 font-mono">--</span></span>
              <span>候选元素: <span id="res-candidates-cnt" class="text-slate-400 font-mono">0</span></span>
            </div>
          </div>

          <div class="bg-slate-950/60 p-2.5 rounded border border-slate-800/60 text-[11px] text-slate-400 leading-relaxed">
            <span class="font-semibold text-slate-300">推理依据: </span>
            <span id="res-rationale">--</span>
          </div>
        </div>

      </div>

      <!-- Right Column: Live Screenshot & Elements Table (7 Cols) -->
      <div class="lg:col-span-7 space-y-6">

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
    let currentDecision = null;

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
        const badge = document.getElementById("badge-api");
        const dot = document.getElementById("badge-api-dot");
        const text = document.getElementById("badge-api-text");
        
        const cardDesc = document.getElementById("card-api-status-desc");
        const cardVal = document.getElementById("card-api-key-val");

        if (data.has_api_key) {
          badge.className = "px-3 py-1 rounded-full border border-emerald-500/40 bg-emerald-950/30 text-emerald-400 flex items-center gap-1.5 cursor-pointer";
          if (dot) dot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-pulse";
          text.textContent = `云端 Jev (${data.masked_key || '已连接'})`;

          if (cardDesc) cardDesc.innerHTML = `<span class="text-emerald-400 font-medium">● 云端 Jev-1.13.0 模型已就绪</span>`;
          if (cardVal) cardVal.innerHTML = `<span class="text-emerald-400 font-mono">${data.masked_key}</span>`;
        } else {
          badge.className = "px-3 py-1 rounded-full border border-amber-500/40 bg-amber-950/30 text-amber-400 flex items-center gap-1.5 cursor-pointer";
          if (dot) dot.className = "w-2 h-2 rounded-full bg-amber-400";
          text.textContent = "本地启发式模拟模式 (未设 KEY)";

          if (cardDesc) cardDesc.innerHTML = `<span class="text-amber-400 font-medium">● 本地启发式回退模式 (未配 Key)</span>`;
          if (cardVal) cardVal.innerHTML = `<span class="text-slate-500 font-mono">未配置 (可点击右上角配置)</span>`;
        }
      } catch (err) {
        console.error("Status check failed:", err);
      }
    }

    async function openApiKeyModal() {
      try {
        const res = await fetch("/api/config");
        const data = await res.json();
        const statusEl = document.getElementById("modal-current-status");
        if (data.configured) {
          statusEl.innerHTML = `<span class="text-emerald-400 font-mono">已配置 (${data.masked_key})</span>`;
        } else {
          statusEl.innerHTML = `<span class="text-amber-400 font-mono">未配置 (启发式回退模式)</span>`;
        }
      } catch (e) {
        console.error("Failed to get config:", e);
      }
      const input = document.getElementById("modal-input-apikey");
      input.value = "";
      input.type = "password";
      document.getElementById("btn-toggle-vis").textContent = "👁️";
      document.getElementById("modal-apikey").classList.remove("hidden");
      setTimeout(() => input.focus(), 50);
    }

    function closeApiKeyModal() {
      document.getElementById("modal-apikey").classList.add("hidden");
    }

    function toggleApiKeyVisibility() {
      const input = document.getElementById("modal-input-apikey");
      const icon = document.getElementById("btn-toggle-vis");
      if (input.type === "password") {
        input.type = "text";
        icon.textContent = "🙈";
      } else {
        input.type = "password";
        icon.textContent = "👁️";
      }
    }

    async function saveApiKeyFromModal() {
      const input = document.getElementById("modal-input-apikey");
      const key = input.value.trim();
      const btn = document.getElementById("btn-save-apikey");
      btn.disabled = true;
      btn.innerHTML = `<span>⏳ 保存中...</span>`;

      try {
        const res = await fetch("/api/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ api_key: key })
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

    async function clearApiKeyFromModal() {
      if (confirm("确定要清除当前配置的 API Key 吗？系统将切换为本地启发式回退模式。")) {
        try {
          const res = await fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: "" })
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

    function configureApiKey() {
      openApiKeyModal();
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
        document.getElementById("btn-execute").disabled = true;
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
      btnDecide.innerHTML = `<span>⏳ Jev 推理中...</span>`;

      try {
        const data = await _fetchJson("/api/decide", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task, url })
        });

        currentDecision = data.decision;
        renderDecisionCard(currentDecision, data.timing);

        // Update Jev Timing stat
        document.getElementById("stat-jev").innerHTML = `${data.timing.jev_planning_ms} <span class="text-xs font-normal text-slate-500">ms</span>`;

        // Highlight element in table
        highlightSelectedElement(currentDecision.target_ref);

        document.getElementById("btn-execute").disabled = false;
        refreshHistory();
      } catch (err) {
        alert("决策异常: " + err.message);
      } finally {
        btnDecide.disabled = false;
        btnDecide.innerHTML = `<span>🧠 步骤 2: Jev 智能决策</span>`;
      }
    }

    async function startExecute() {
      const btnExecute = document.getElementById("btn-execute");
      btnExecute.disabled = true;
      btnExecute.innerHTML = `<span>⏳ 正在执行原语...</span>`;

      try {
        const data = await _fetchJson("/api/execute", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });

        // Update screenshot if returned
        if (data.screenshot) {
          document.getElementById("img-preview").src = data.screenshot;
        }

        // Update execution timing
        document.getElementById("stat-exec").innerHTML = `${data.timing.execution_ms} <span class="text-xs font-normal text-slate-500">ms</span>`;

        alert("执行成功: " + data.message);
        refreshHistory();
      } catch (err) {
        alert("执行异常: " + err.message);
      } finally {
        btnExecute.disabled = false;
        btnExecute.innerHTML = `<span>⚡ 步骤 3: 在线执行动作</span>`;
      }
    }

    function renderElementsTable(elements) {
      const tbody = document.getElementById("tbody-elements");
      document.getElementById("badge-elem-count").textContent = `${elements.length} 元素`;

      if (!elements.length) {
        tbody.innerHTML = `<tr><td colspan="4" class="py-6 text-center text-slate-500">未提取到交互元素</td></tr>`;
        return;
      }

      tbody.innerHTML = elements.map(e => `
        <tr id="row-${e.ref}" class="hover:bg-slate-800/40 transition">
          <td class="py-2 px-3 font-bold text-cyan-400">${e.ref}</td>
          <td class="py-2 px-3 text-slate-300 font-mono">${e.tag} <span class="text-slate-500">[${e.role}]</span></td>
          <td class="py-2 px-3 text-slate-200 max-w-[200px] truncate" title="${e.name || e.placeholder || ''}">${e.name || e.placeholder || '<span class="text-slate-500">(空)</span>'}</td>
          <td class="py-2 px-3 text-emerald-400 font-mono max-w-[220px] truncate" title="${e.selector}">${e.selector}</td>
        </tr>
      `).join("");
    }

    function highlightSelectedElement(ref) {
      document.querySelectorAll("#tbody-elements tr").forEach(r => r.classList.remove("bg-cyan-950/60", "border-cyan-500/40"));
      const targetRow = document.getElementById(`row-${ref}`);
      if (targetRow) {
        targetRow.classList.add("bg-cyan-950/60", "border-cyan-500/40");
        targetRow.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    }

    function renderDecisionCard(dec, timing) {
      const card = document.getElementById("card-decision");
      card.classList.remove("hidden");

      document.getElementById("decision-time-badge").textContent = `${timing.jev_planning_ms} ms`;
      document.getElementById("res-target-ref").textContent = dec.target_ref;
      document.getElementById("res-target-desc").textContent = dec.target_element ? (dec.target_element.name || dec.target_element.selector) : "(无目标)";
      document.getElementById("res-action").textContent = dec.action_type.toUpperCase();
      document.getElementById("res-value").textContent = dec.input_value ? `写入: "${dec.input_value}"` : "无需传值";
      
      const confPct = (dec.confidence * 100).toFixed(1);
      document.getElementById("res-conf").textContent = `${confPct}%`;
      document.getElementById("res-conf-bar").style.width = `${confPct}%`;

      document.getElementById("res-mode").textContent = `${dec.mode} (${dec.model_name})`;
      document.getElementById("res-candidates-cnt").textContent = currentElements.length;
      document.getElementById("res-rationale").textContent = dec.rationale || "无额外说明";
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
          const isSuccess = item.status === "success";
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

  <!-- API Key Modal Dialog -->
  <div id="modal-apikey" class="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm hidden flex items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl relative">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <h3 class="text-base font-bold text-white flex items-center gap-2">
          <span>🔑</span> 配置 TypeSafe Jev API Key
        </h3>
        <button onclick="closeApiKeyModal()" class="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition text-lg leading-none cursor-pointer">&times;</button>
      </div>

      <div class="text-xs text-slate-300 leading-relaxed space-y-2">
        <p>配置 API Key 后，系统将直接调用云端 <span class="text-cyan-400 font-mono font-semibold">jev-1.13.0</span> 大模型进行智能元素决策与规划。配置会自动保存在本地 <code class="text-slate-400 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">.env</code> 中。</p>
        <div class="bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-[11px] text-slate-400 flex items-center justify-between">
          <span>当前状态：</span>
          <span id="modal-current-status" class="font-mono text-slate-300 font-semibold">检查中...</span>
        </div>
      </div>

      <div class="space-y-1.5">
        <label class="block text-xs font-medium text-slate-300">请输入 API Key：</label>
        <div class="relative">
          <input type="password" id="modal-input-apikey" placeholder="apikey_xxxxxxxx..." 
            class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 pr-10 text-sm text-white font-mono focus:outline-none focus:border-cyan-500"
            onkeydown="if(event.key==='Enter') saveApiKeyFromModal()">
          <button type="button" onclick="toggleApiKeyVisibility()" class="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-200 text-sm p-0.5 cursor-pointer" title="切换显示/隐藏">
            <span id="btn-toggle-vis">👁️</span>
          </button>
        </div>
        <p class="text-[11px] text-slate-500">提示：留空并保存将清除当前配置的 Key，回退至本地启发式模式。</p>
      </div>

      <div class="flex items-center justify-between pt-2 border-t border-slate-800">
        <button type="button" onclick="clearApiKeyFromModal()" class="text-xs text-rose-400 hover:text-rose-300 transition underline cursor-pointer">
          清除现有 Key
        </button>
        <div class="flex items-center gap-2">
          <button onclick="closeApiKeyModal()" class="px-4 py-2 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 text-xs transition cursor-pointer">
            取消
          </button>
          <button id="btn-save-apikey" onclick="saveApiKeyFromModal()" class="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs transition flex items-center gap-1.5 shadow-lg shadow-cyan-600/20 cursor-pointer">
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
