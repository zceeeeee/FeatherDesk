"""
Interactive Jev Page Element Decision Runner.

Provides step-by-step interactive workflow:
1. Natural language task & URL input with confirmation.
2. Automated scanning of interactive elements with clean tabular display.
3. User confirmation before sending state to Jev model.
4. Jev System 1 structured decision display (target element, atomic action, confidence).
5. Optional execution of the decided action in the live browser.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.sync_api import sync_playwright
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .element_scanner import ElementScanner, ScannedElement
from .jev_client import JevDecision, JevPlanner

console = Console(highlight=False)


def print_banner(api_key_present: bool) -> None:
    status_text = (
        "[bold green][OK] 已检测到 TYPESAFE_API_KEY (在线 Jev System 1 模式)[/bold green]"
        if api_key_present
        else "[bold yellow][!] 未检测到 TYPESAFE_API_KEY (已自动启用本地启发式模拟决策模式)[/bold yellow]"
    )
    console.print(
        Panel(
            f"[bold cyan]Jev 网页元素检测与动作决策原型系统[/bold cyan]\n"
            f"[dim]参考项目 ARIA 交互抽取机制 + TypeSafe Jev System 1 极速动作判断[/dim]\n\n"
            f"运行状态: {status_text}\n"
            f"API 说明: 可在系统环境变量设置 [cyan]TYPESAFE_API_KEY[/cyan] 以直连云端 Jev 模型",
            title="[bold magenta]TypeSafe Jev + Playwright Harness[/bold magenta]",
            border_style="cyan",
        )
    )


def prompt_user(prompt_text: str, default: str = "") -> str:
    """Read line with default support."""
    if default:
        display = f"{prompt_text} [dim](默认: {default})[/dim]: "
    else:
        display = f"{prompt_text}: "
    val = console.input(display).strip()
    return val if val else default


def confirm_step(prompt_text: str, auto_confirm: bool = False) -> bool:
    """Prompt user for confirmation (y/n)."""
    if auto_confirm:
        console.print(f"[dim]{prompt_text} -> [自动确认][/dim]")
        return True
    res = console.input(f"[bold yellow]{prompt_text} [Y/n]: [/bold yellow]").strip().lower()
    return res in ("", "y", "yes", "1")


def display_scanned_elements(elements: list[ScannedElement]) -> None:
    """Render scanned elements in a rich table."""
    table = Table(title="[SCAN] 页面交互元素扫描结果 (ARIA 抽取与标号)", border_style="blue", show_header=True, header_style="bold bright_white")
    table.add_column("标号 (Ref)", style="bold cyan", justify="center", min_width=10)
    table.add_column("标签与角色", style="magenta", min_width=16)
    table.add_column("文本内容 / 占位符", style="white", min_width=26)
    table.add_column("选择器 (Selector)", style="green", min_width=24)
    table.add_column("视口坐标", style="dim", min_width=14)

    for el in elements:
        text_or_placeholder = el.name or el.placeholder or el.value or "(无直接文本)"
        if len(text_or_placeholder) > 34:
            text_or_placeholder = text_or_placeholder[:33] + "..."
        
        sel_display = el.selector
        if len(sel_display) > 32:
            sel_display = sel_display[:31] + "..."

        bbox_str = f"{el.bbox.get('x', 0)},{el.bbox.get('y', 0)} ({el.bbox.get('width', 0)}x{el.bbox.get('height', 0)})"

        table.add_row(
            el.ref,
            f"{el.tag} [{el.role}]",
            text_or_placeholder,
            sel_display,
            bbox_str,
        )

    console.print(table)
    console.print(f"[dim]共抽取到 [bold green]{len(elements)}[/bold green] 个候选交互元素[/dim]\n")


def display_jev_decision(decision: JevDecision) -> None:
    """Display Jev's output structured card."""
    conf_color = "green" if decision.confidence >= 0.8 else ("yellow" if decision.confidence >= 0.5 else "red")
    
    lines = [
        f"[TARGET] [bold]目标元素 (Target Element):[/bold] [bold cyan]{decision.target_ref}[/bold cyan]",
    ]
    if decision.target_element:
        el = decision.target_element
        lines.append(f"   * 角色与标签: [magenta]<{el.tag} role='{el.role}'>[/magenta]")
        lines.append(f"   * 元素描述: [white]{el.name or el.placeholder or '(空)'}[/white]")
        lines.append(f"   * 定位选择器: [green]{el.selector}[/green]")
    
    lines.append(f"\n[ACTION] [bold]拟执行元操作 (Action Type):[/bold] [bold yellow]{decision.action_type.upper()}[/bold yellow]")
    if decision.input_value:
        lines.append(f"   * 写入参数值 (Input Value): [bold green]\"{decision.input_value}\"[/bold green]")

    lines.append(f"\n[CONFIDENCE] [bold]决策置信度 (Confidence):[/bold] [{conf_color}]{decision.confidence * 100:.1f}%[/{conf_color}]")
    if decision.probabilities:
        prob_strs = [f"{k}: {v*100:.1f}%" for k, v in decision.probabilities.items()]
        lines.append(f"   * 候选概率分布: [dim]{', '.join(prob_strs)}[/dim]")

    lines.append(f"\n[MODEL] [bold]决策引擎模式:[/bold] [dim]{decision.mode} ({decision.model_name})[/dim]")
    lines.append(f"[REASON] [bold]推理说明:[/bold] [dim]{decision.rationale}[/dim]")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold green]Jev System 1 决策输出[/bold green]",
            border_style="green",
        )
    )


def run_demo(
    task: Optional[str] = None,
    url: Optional[str] = None,
    headless: bool = False,
    auto_confirm: bool = False,
    execute_action: bool = False,
) -> None:
    """Main demo flow execution."""
    api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    print_banner(bool(api_key))

    # Step 1: Gather Inputs
    if not task:
        task = prompt_user("请输入自然语言的任务要求", default="在百度搜索框输入 python 并点击搜索")
    else:
        console.print(f"[bold]任务要求:[/bold] [cyan]{task}[/cyan]")

    if not url:
        url = prompt_user("请输入目标网页地址", default="https://www.baidu.com")
    else:
        console.print(f"[bold]网页地址:[/bold] [cyan]{url}[/cyan]")

    console.print()
    if not confirm_step("确认执行任务并启动浏览器扫描？", auto_confirm=auto_confirm):
        console.print("[red]用户已取消操作。[/red]")
        return

    # Step 2: Launch Browser & Scan
    console.print(f"\n[cyan][+] 正在启动 Playwright (Headless={headless})...[/cyan]")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            console.print(f"[cyan][+] 正在导航至: {url} ...[/cyan]")
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1000)
            page_title = page.title()
            console.print(f"[green][OK] 页面加载成功: {page_title} (URL: {page.url})[/green]\n")

            console.print("[cyan][+] 正在提取页面 ARIA 交互元素并分配标号...[/cyan]")
            scanner = ElementScanner(max_elements=35)
            elements = scanner.scan_sync(page)

            if not elements:
                console.print("[bold red]未能在页面中发现可交互的候选元素！[/bold red]")
                return

            # Display Scanned Elements Table
            display_scanned_elements(elements)

            # Step 3: User Confirmation for Jev Decision
            if not confirm_step("确认后，让 Jev 模型判断要选择的元素和要执行的动作操作？", auto_confirm=auto_confirm):
                console.print("[yellow]已暂停，未调用 Jev 模型。[/yellow]")
                return

            # Step 4: Call Jev Planner
            console.print("\n[magenta][Jev] 正在请求 Jev 模型进行极速动作规划与元素匹配...[/magenta]")
            start_time = time.time()
            planner = JevPlanner(api_key=api_key)
            decision = planner.plan(
                task=task,
                page_url=page.url,
                page_title=page_title,
                elements=elements,
            )
            elapsed_ms = (time.time() - start_time) * 1000
            console.print(f"[dim]Jev 判定耗时: [bold]{elapsed_ms:.1f} ms[/bold][/dim]\n")

            # Display Decision
            display_jev_decision(decision)

            # Step 5: Optional Live Execution
            should_run = execute_action or confirm_step(
                f"是否在当前页面实际执行该操作 [{decision.action_type.upper()}] 到 [{decision.target_ref}]？",
                auto_confirm=auto_confirm,
            )

            if should_run and decision.target_element:
                target_sel = decision.target_element.selector
                console.print(f"\n[cyan][EXEC] 正在执行 Playwright 原语: {decision.action_type} -> '{target_sel}' ...[/cyan]")
                try:
                    if decision.action_type == "fill":
                        val_to_fill = decision.input_value or "test"
                        page.fill(target_sel, val_to_fill, timeout=5000)
                        console.print(f"[bold green][OK] 成功在 {target_sel} 填入文本: \"{val_to_fill}\"[/bold green]")
                        page.wait_for_timeout(1000)
                    elif decision.action_type == "click":
                        page.click(target_sel, timeout=5000)
                        console.print(f"[bold green][OK] 成功点击元素: {target_sel}[/bold green]")
                        page.wait_for_timeout(1500)
                    elif decision.action_type == "press":
                        page.press(target_sel, "Enter", timeout=5000)
                        console.print(f"[bold green][OK] 成功在 {target_sel} 按下 Enter[/bold green]")
                        page.wait_for_timeout(1500)
                    else:
                        console.print(f"[yellow]动作 {decision.action_type} 暂不需自动执行。[/yellow]")

                    console.print(f"[bold green][DONE] 操作完成！当前页面 URL: {page.url}[/bold green]")
                except Exception as ex:
                    console.print(f"[red]执行操作异常: {ex}[/red]")

            console.print("\n[dim]浏览器会话即将关闭...[/dim]")
            time.sleep(1)

        finally:
            browser.close()
            console.print("[green][OK] 流程执行完毕，浏览器已安全释放。[/green]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev Model Web Element Decision Runner")
    parser.add_argument("--task", type=str, default=None, help="Natural language task description")
    parser.add_argument("--url", type=str, default=None, help="Target website URL")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--auto-confirm", action="store_true", help="Automatically confirm all prompts without waiting for user input")
    parser.add_argument("--execute", action="store_true", help="Automatically execute the predicted action in browser")
    args = parser.parse_args()

    run_demo(
        task=args.task,
        url=args.url,
        headless=args.headless,
        auto_confirm=args.auto_confirm,
        execute_action=args.execute,
    )


if __name__ == "__main__":
    main()
