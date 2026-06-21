"""
视觉验证测试循环 —— 使用 mimo-v2.5 视觉模型验证任务结果。

流程:
1. 执行任务
2. 截图
3. 发送给视觉模型验证
4. 如果验证失败，分析原因并调整脚本
5. 重试直到通过或达到最大次数
6. 保存测试报告

使用方法:
    python workflows/vision-verified-cycle.py
    python workflows/vision-verified-cycle.py --site baidu
    python workflows/vision-verified-cycle.py --task 1.1
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.browser_manager import get_browser_manager, reset_browser_manager
from src.core.script_engine import get_script_engine, reset_script_engine
from src.core.script_generator import ScriptGenerator
from src.layer_2.controls import get_controls_exports
from src.core.agent_loop import AgentLoop


# ---------------------------------------------------------------------------
# 视觉模型配置
# ---------------------------------------------------------------------------

VISION_API_BASE = "https://token-plan-cn.xiaomimimo.com/v1"
VISION_API_KEY = os.getenv("VISION_API_KEY", "")
VISION_MODEL = "mimo-v2.5"


# ---------------------------------------------------------------------------
# 任务定义 — 16 个已通过验证的网站，每个 2-3 个任务
# ---------------------------------------------------------------------------

@dataclass
class Task:
    id: str
    site: str
    description: str
    expected_behavior: str  # 视觉模型验证的预期行为
    search_url: str = ""
    keywords: list[str] = field(default_factory=list)
    max_retries: int = 5


TASKS = [
    # === 1. 百度搜索 ===
    Task("1.1", "baidu", "帮我在百度搜索 Python 教程",
         "页面显示百度搜索结果，包含Python教程相关的链接和标题",
         search_url="baidu.com/s?", keywords=["Python"]),
    Task("1.2", "baidu", "在百度搜索人工智能，返回前5条搜索结果的标题",
         "页面显示百度搜索结果，输出包含5条标题",
         search_url="baidu.com/s?", keywords=["人工智能"]),

    # === 2. 搜狗搜索 ===
    Task("2.1", "sogou", "在搜狗搜索 Python 教程",
         "页面显示搜狗搜索结果，包含Python教程相关的链接",
         search_url="sogou.com", keywords=["Python"]),

    # === 3. 淘宝 ===
    Task("3.1", "taobao", "在淘宝搜索机械键盘，返回前5个商品的名称和价格",
         "页面显示淘宝搜索结果，包含机械键盘商品列表和价格",
         search_url="taobao.com", keywords=["机械键盘"]),

    # === 4. 京东 ===
    Task("4.1", "jd", "在京东搜索机械键盘，返回前5个商品的名称和价格",
         "页面显示京东搜索结果，包含机械键盘商品列表和价格",
         search_url="jd.com", keywords=["机械键盘"]),

    # === 5. 拼多多 ===
    Task("5.1", "pdd", "在拼多多搜索手机壳，返回前5个商品的名称和价格",
         "页面显示拼多多搜索结果，包含手机壳商品列表",
         search_url="pinduoduo.com", keywords=["手机壳"]),

    # === 6. 当当网 ===
    Task("6.1", "dangdang", "在当当网搜索Python编程，返回前5本书的名称和价格",
         "页面显示当当网搜索结果，包含Python编程书籍列表",
         search_url="dangdang.com", keywords=["Python"]),

    # === 7. 知乎 ===
    Task("7.1", "zhihu", "在知乎搜索Python怎么学，返回前3个问题的标题",
         "页面显示知乎搜索结果，包含Python学习相关的问题",
         search_url="zhihu.com", keywords=["Python"]),

    # === 8. 豆瓣 ===
    Task("8.1", "douban", "在豆瓣搜索肖申克的救赎，返回电影的评分",
         "页面显示豆瓣搜索结果，包含肖申克的救赎电影信息和评分",
         search_url="douban.com", keywords=["肖申克"]),

    # === 9. B站 ===
    Task("9.1", "bilibili", "在B站搜索Python教程，返回前5个视频的标题",
         "页面显示B站搜索结果，包含Python教程视频列表",
         search_url="bilibili.com", keywords=["Python"]),

    # === 10. 今日头条 ===
    Task("10.1", "toutiao", "在今日头条搜索人工智能，返回前5条新闻的标题",
         "页面显示今日头条搜索结果，包含人工智能相关新闻",
         search_url="toutiao.com", keywords=["人工智能"]),

    # === 11. CSDN ===
    Task("11.1", "csdn", "在CSDN搜索Python爬虫，返回前5篇文章的标题",
         "页面显示CSDN搜索结果，包含Python爬虫技术文章",
         search_url="csdn.net", keywords=["Python"]),

    # === 12. Gitee ===
    Task("12.1", "gitee", "在Gitee搜索Python，返回前5个仓库的名称",
         "页面显示Gitee搜索结果，包含Python仓库列表",
         search_url="gitee.com", keywords=["Python"]),

    # === 13. 百度百科 ===
    Task("13.1", "baike", "在百度百科查询人工智能，返回词条的简介",
         "页面显示百度百科人工智能词条，包含简介内容",
         search_url="baike.baidu.com", keywords=["人工智能"]),

    # === 14. 百度文库 ===
    Task("14.1", "wenku", "在百度文库搜索Python教程，返回前5个文档的标题",
         "页面显示百度文库搜索结果，包含Python教程文档",
         search_url="wenku.baidu.com", keywords=["Python"]),

    # === 15. 天气网 ===
    Task("15.1", "weather", "查询北京今天的天气，返回温度和天气状况",
         "页面显示北京天气信息，包含温度、天气状况等",
         search_url="weather.com.cn", keywords=["北京"]),

    # === 16. 微博热搜 ===
    Task("16.1", "weibo", "打开微博热搜榜，返回前10条热搜话题",
         "页面显示微博热搜榜，包含热门话题列表",
         search_url="weibo.com", keywords=["热搜"]),
]


# ---------------------------------------------------------------------------
# 视觉模型验证
# ---------------------------------------------------------------------------


def verify_with_vision(screenshot_path: str, expected: str) -> dict:
    """用视觉模型验证截图是否符合预期。

    Args:
        screenshot_path: 截图文件路径
        expected: 预期行为描述

    Returns:
        dict: {passed: bool, reason: str, details: str}
    """
    # 读取截图并编码
    with open(screenshot_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    prompt = f"""你是一个网页测试验证专家。请分析这张截图，判断是否符合预期。

预期行为: {expected}

请严格按以下 JSON 格式返回:
{{
  "passed": true/false,
  "reason": "通过或失败的简短原因",
  "details": "详细分析（页面内容、是否找到预期元素等）"
}}

注意:
- 只返回 JSON，不要返回其他内容
- 如果页面显示了预期内容，passed 为 true
- 如果页面是空白、错误页、或不符合预期，passed 为 false
- 检查页面是否有搜索结果、商品列表、文章列表等具体内容"""

    try:
        response = httpx.post(
            f"{VISION_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {VISION_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_data}",
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                "max_tokens": 1000,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content", "") or msg.get("reasoning_content", "")

        # 解析 JSON
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(content[json_start:json_end])
            return {
                "passed": result.get("passed", False),
                "reason": result.get("reason", ""),
                "details": result.get("details", ""),
            }

        return {"passed": False, "reason": "无法解析视觉模型返回", "details": content}

    except Exception as e:
        return {"passed": False, "reason": f"视觉模型调用失败: {e}", "details": ""}


# ---------------------------------------------------------------------------
# 脚本调整
# ---------------------------------------------------------------------------


def adjust_script(task: Task, current_script: str, failure_reason: str) -> str:
    """根据失败原因调整脚本。"""
    gen = ScriptGenerator()
    keyword = task.keywords[0] if task.keywords else ""

    if "搜索框" in failure_reason or "输入" in failure_reason:
        cfg = gen.SEARCH_ENGINES.get(task.site, {})
        if cfg:
            url, inp, btn = cfg["url"], cfg["input"], cfg["submit"]
            lines = ['goto("' + url + '")', 'wait_for_navigation()', 'fill("' + inp + '", "' + keyword + '")', 'wait_for_navigation()']
            return chr(10).join(lines)

    if "按钮" in failure_reason or "click" in failure_reason.lower():
        cfg = gen.SEARCH_ENGINES.get(task.site, {})
        if cfg:
            url, inp = cfg["url"], cfg["input"]
            lines = ['goto("' + url + '")', 'wait_for_navigation()', 'fill("' + inp + '", "' + keyword + '")', 'page.keyboard.press("Enter")', 'wait_for_navigation()']
            return chr(10).join(lines)

    if "加载" in failure_reason or "timeout" in failure_reason.lower():
        return current_script.replace("wait_for_navigation()", "wait_for_navigation(timeout=15000)" + chr(10) + "wait(2)")

    new_script = gen.generate(task.description)
    return new_script if new_script else current_script
def run_test_cycle(tasks: list[Task], max_retries: int = 5) -> dict:
    """执行视觉验证测试循环。"""
    results = []
    skipped = []
    total = len(tasks)

    print(f"\n{'='*60}")
    print(f"视觉验证测试循环")
    print(f"总任务数: {total}")
    print(f"最大重试: {max_retries}")
    print(f"视觉模型: {VISION_MODEL}")
    print(f"{'='*60}\n")

    gen = ScriptGenerator()

    for i, task in enumerate(tasks, 1):
        print(f"\n[{i}/{total}] 任务 {task.id}: {task.description}")
        print(f"  网站: {task.site} | 预期: {task.expected_behavior[:50]}...")

        passed = False
        attempts = 0
        last_script = ""
        last_reason = ""

        while not passed and attempts < max_retries:
            attempts += 1
            print(f"\n  尝试 {attempts}/{max_retries}...")

            # 重置状态
            reset_browser_manager()
            reset_script_engine()

            try:
                # 1. 生成脚本
                if attempts == 1:
                    script = gen.generate(task.description)
                else:
                    # 根据失败原因调整脚本
                    script = adjust_script(task, last_script, last_reason)

                if not script:
                    print(f"    无法生成脚本")
                    last_reason = "无法生成脚本"
                    continue

                last_script = script
                print(f"    脚本: {script[:80]}...")

                # 2. 启动浏览器并执行
                bm = get_browser_manager()
                bm.launch(headless=True)

                engine = get_script_engine()
                engine.register_functions(get_controls_exports())

                # 构建完整脚本（带关键词调用）
                if task.keywords and "run(" not in script:
                    keyword = task.keywords[0]
                    full_script = f'{script}\n\n# 自动调用\nrun("{keyword}")' if "def run" in script else script
                else:
                    full_script = script

                result = engine.execute(full_script)
                print(f"    执行: {'成功' if result.success else '失败'}")
                print(f"    URL: {bm.get_page().url}")

                # 3. 截图
                screenshot_path = f"logs/test_{task.id}_{attempts}.png"
                os.makedirs("logs", exist_ok=True)
                bm.get_page().screenshot(path=screenshot_path, full_page=True)
                print(f"    截图: {screenshot_path}")

                # 4. 视觉验证
                print(f"    正在调用视觉模型验证...")
                vision_result = verify_with_vision(screenshot_path, task.expected_behavior)
                print(f"    视觉验证: {'PASS' if vision_result['passed'] else 'FAIL'}")
                print(f"    原因: {vision_result['reason']}")

                if vision_result["passed"]:
                    passed = True
                    results.append({
                        "id": task.id,
                        "site": task.site,
                        "task": task.description,
                        "status": "PASS",
                        "attempts": attempts,
                        "url": bm.get_page().url,
                        "vision_reason": vision_result["reason"],
                        "vision_details": vision_result["details"],
                        "screenshot": screenshot_path,
                        "script": script,
                    })
                    print(f"    最终: PASS")
                else:
                    last_reason = vision_result["reason"]
                    print(f"    最终: FAIL - {vision_result['reason']}")

                # 关闭浏览器
                bm.close()

            except Exception as e:
                print(f"    异常: {e}")
                last_reason = str(e)
                try:
                    reset_browser_manager()
                except:
                    pass

        if not passed:
            skipped.append({
                "id": task.id,
                "site": task.site,
                "task": task.description,
                "reason": f"失败 {max_retries} 次: {last_reason}",
            })
            print(f"\n  最终: SKIPPED")

    # 生成报告
    passed_count = len(results)
    skipped_count = len(skipped)
    pass_rate = round(passed_count / total * 100, 1) if total > 0 else 0

    report = {
        "timestamp": time.time(),
        "vision_model": VISION_MODEL,
        "total": total,
        "passed": passed_count,
        "skipped": skipped_count,
        "pass_rate": pass_rate,
        "results": results,
        "skipped": skipped,
    }

    # 打印报告
    print(f"\n{'='*60}")
    print(f"测试报告")
    print(f"{'='*60}")
    print(f"总任务数: {total}")
    print(f"通过: {passed_count}")
    print(f"跳过: {skipped_count}")
    print(f"通过率: {pass_rate}%")

    if results:
        print(f"\n通过的任务:")
        for r in results:
            print(f"  {r['id']}: {r['site']:10s} ({r['attempts']}次) {r['vision_reason']}")

    if skipped:
        print(f"\n跳过的任务:")
        for s in skipped:
            print(f"  {s['id']}: {s['site']:10s} - {s['reason'][:50]}")

    print(f"{'='*60}")

    return report


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="视觉验证测试循环")
    parser.add_argument("--site", help="只运行指定网站的任务")
    parser.add_argument("--task", help="运行指定任务 (如 1.1)")
    parser.add_argument("--max-retries", type=int, default=5, help="最大重试次数")
    parser.add_argument("--report", default="vision_test_report.json", help="报告输出路径")

    args = parser.parse_args()

    # 过滤任务
    tasks = TASKS
    if args.site:
        tasks = [t for t in tasks if t.site == args.site]
    if args.task:
        tasks = [t for t in tasks if t.id == args.task]

    if not tasks:
        print("没有匹配的任务")
        sys.exit(1)

    # 运行测试循环
    report = run_test_cycle(tasks, max_retries=args.max_retries)

    # 保存报告
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n报告已保存: {args.report}")

    # 返回退出码
    sys.exit(0 if report["skipped"] == 0 else 1)


if __name__ == "__main__":
    main()
