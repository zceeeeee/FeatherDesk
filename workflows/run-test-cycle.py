"""
测试循环工作流 —— 自动执行任务，失败重试，生成报告。

使用方法:
    python workflows/run-test-cycle.py              # 运行所有任务
    python workflows/run-test-cycle.py --quick      # 只运行第一批
    python workflows/run-test-cycle.py --site baidu # 只运行百度
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.browser_manager import get_browser_manager, reset_browser_manager
from src.core.script_engine import reset_script_engine
from src.core.agent_loop import AgentLoop


# ---------------------------------------------------------------------------
# 任务定义
# ---------------------------------------------------------------------------

TASKS = [
    # 搜索引擎
    {"id": "1.1", "site": "baidu", "task": "帮我在百度搜索 Python 教程", "url": "baidu.com", "search_url": "baidu.com/s?", "keywords": ["Python"], "min_output": 10, "priority": 1},
    {"id": "1.2", "site": "baidu", "task": "在百度搜索人工智能，返回前5条搜索结果的标题", "url": "baidu.com", "search_url": "baidu.com/s?", "keywords": ["人工智能"], "min_lines": 3, "priority": 2},
    {"id": "2.1", "site": "bing", "task": "在必应搜索 Python 教程", "url": "bing.com", "search_url": "bing.com/search", "keywords": ["Python"], "min_output": 10, "priority": 1},
    {"id": "3.1", "site": "sogou", "task": "在搜狗搜索 Python 教程", "url": "sogou.com", "search_url": "sogou.com/web", "keywords": ["Python"], "min_output": 10, "priority": 1},
    {"id": "4.1", "site": "so", "task": "在360搜索 Python 教程", "url": "so.com", "search_url": "so.com/s?", "keywords": ["Python"], "min_output": 10, "priority": 1},

    # 电商
    {"id": "5.1", "site": "taobao", "task": "在淘宝搜索机械键盘，返回前5个商品的名称和价格", "url": "taobao.com", "search_url": "taobao.com", "keywords": ["机械键盘"], "min_lines": 3, "priority": 2},
    {"id": "6.1", "site": "jd", "task": "在京东搜索机械键盘，返回前5个商品的名称和价格", "url": "jd.com", "search_url": "jd.com", "keywords": ["机械键盘"], "min_lines": 3, "priority": 2},
    {"id": "7.1", "site": "pdd", "task": "在拼多多搜索手机壳，返回前5个商品的名称和价格", "url": "pinduoduo.com", "search_url": "pinduoduo.com", "keywords": ["手机壳"], "min_lines": 3, "priority": 2},
    {"id": "8.1", "site": "dangdang", "task": "在当当网搜索Python编程，返回前5本书的名称和价格", "url": "dangdang.com", "search_url": "dangdang.com", "keywords": ["Python"], "min_lines": 3, "priority": 1},

    # 社交
    {"id": "9.1", "site": "weibo", "task": "打开微博热搜榜，返回前10条热搜话题", "url": "weibo.com", "search_url": "weibo.com", "keywords": ["热搜", "榜"], "min_lines": 5, "priority": 2},
    {"id": "10.1", "site": "zhihu", "task": "在知乎搜索Python怎么学，返回前3个问题的标题", "url": "zhihu.com", "search_url": "zhihu.com/search", "keywords": ["Python"], "min_lines": 3, "priority": 2},
    {"id": "11.1", "site": "douban", "task": "在豆瓣搜索肖申克的救赎，返回电影的评分和评价人数", "url": "douban.com", "search_url": "douban.com", "keywords": ["肖申克"], "min_output": 20, "priority": 2},

    # 视频/资讯
    {"id": "12.1", "site": "bilibili", "task": "在B站搜索Python教程，返回前5个视频的标题和播放量", "url": "bilibili.com", "search_url": "bilibili.com", "keywords": ["Python"], "min_lines": 3, "priority": 2},
    {"id": "13.1", "site": "toutiao", "task": "在今日头条搜索人工智能，返回前5条新闻的标题和来源", "url": "toutiao.com", "search_url": "toutiao.com/search", "keywords": ["人工智能"], "min_lines": 3, "priority": 1},

    # 技术/知识
    {"id": "14.1", "site": "csdn", "task": "在CSDN搜索Python爬虫，返回前5篇文章的标题和作者", "url": "csdn.net", "search_url": "csdn.net/so/search", "keywords": ["Python"], "min_lines": 3, "priority": 1},
    {"id": "15.1", "site": "gitee", "task": "在Gitee搜索Python，返回前5个仓库的名称、Stars和描述", "url": "gitee.com", "search_url": "gitee.com", "keywords": ["Python"], "min_lines": 3, "priority": 1},
    {"id": "16.1", "site": "baike", "task": "在百度百科查询人工智能，返回词条的简介", "url": "baike.baidu.com", "search_url": "baike.baidu.com", "keywords": ["人工智能"], "min_output": 50, "priority": 1},

    # 文档
    {"id": "17.1", "site": "wenku", "task": "在百度文库搜索Python教程，返回前5个文档的标题和页数", "url": "wenku.baidu.com", "search_url": "wenku.baidu.com", "keywords": ["Python"], "min_lines": 3, "priority": 2},

    # 工具
    {"id": "20.1", "site": "weather", "task": "查询北京今天的天气，返回温度、天气状况、风力", "url": "weather.com.cn", "search_url": "weather.com.cn", "keywords": ["北京"], "min_output": 20, "priority": 1},
]


# ---------------------------------------------------------------------------
# 测试循环
# ---------------------------------------------------------------------------

MAX_RETRIES = 5


def run_test_cycle(tasks: list[dict], max_retries: int = MAX_RETRIES) -> dict:
    """执行测试循环。

    Args:
        tasks: 任务列表
        max_retries: 最大重试次数

    Returns:
        测试报告
    """
    results = []
    skipped = []
    total = len(tasks)

    print(f"\n{'='*60}")
    print(f"测试循环开始")
    print(f"总任务数: {total}")
    print(f"最大重试: {max_retries}")
    print(f"{'='*60}\n")

    for i, task in enumerate(tasks, 1):
        print(f"\n[{i}/{total}] 任务 {task['id']}: {task['task']}")
        print(f"  网站: {task['site']} | 预期 URL: {task['url']}")

        passed = False
        attempts = 0

        while not passed and attempts < max_retries:
            attempts += 1
            print(f"  尝试 {attempts}/{max_retries}...")

            # 重置状态
            reset_browser_manager()
            reset_script_engine()

            try:
                # 启动浏览器
                bm = get_browser_manager()
                bm.launch(headless=True)

                # 执行任务
                agent = AgentLoop(max_steps=5)
                result = agent.run(task['task'])

                # 验证结果（按 test-spec.md 严格规则）
                output = result.output or ''
                url = result.final_url or ''
                checks = []

                # 1. 执行状态
                exec_ok = result.success
                checks.append(('执行', exec_ok))

                # 2. URL 匹配（必须包含 search_url，不只是域名）
                search_url = task.get('search_url', task['url'])
                url_ok = search_url in url
                checks.append(('URL', url_ok))

                # 3. 关键词匹配（输出必须包含搜索关键词）
                keywords = task.get('keywords', [])
                kw_ok = all(kw in output for kw in keywords) if keywords else True
                checks.append(('关键词', kw_ok))

                # 4. 输出长度
                min_output = task.get('min_output', 0)
                len_ok = len(output) >= min_output if min_output > 0 else True
                checks.append(('长度', len_ok))

                # 5. 输出行数
                min_lines = task.get('min_lines', 0)
                lines = [l for l in output.split('\n') if l.strip()]
                lines_ok = len(lines) >= min_lines if min_lines > 0 else True
                checks.append(('行数', lines_ok))

                # 综合判定：所有检查都通过才算 PASS
                success = all(ok for _, ok in checks)
                check_detail = ', '.join(f'{name}={"OK" if ok else "FAIL"}' for name, ok in checks)

                if success:
                    passed = True
                    results.append({
                        'id': task['id'],
                        'site': task['site'],
                        'task': task['task'],
                        'status': 'PASS',
                        'attempts': attempts,
                        'url': url,
                        'output_len': len(output),
                        'checks': check_detail,
                    })
                    print(f"  结果: PASS ({check_detail})")
                else:
                    print(f"  结果: FAIL ({check_detail})")
                    print(f"    URL: {url[:60]}")
                    print(f"    期望URL包含: {search_url}")
                    print(f"    输出长度: {len(output)}, 行数: {len(lines)}")

                # 关闭浏览器
                bm.close()

            except Exception as e:
                print(f"  结果: ERROR ({e})")
                try:
                    reset_browser_manager()
                except:
                    pass

        if not passed:
            skipped.append({
                'id': task['id'],
                'site': task['site'],
                'task': task['task'],
                'reason': f'失败 {max_retries} 次后跳过',
            })
            print(f"  最终: SKIPPED (超过最大重试次数)")

    # 生成报告
    passed_count = len(results)
    skipped_count = len(skipped)
    pass_rate = round(passed_count / total * 100, 1) if total > 0 else 0

    report = {
        'timestamp': time.time(),
        'total': total,
        'passed': passed_count,
        'skipped': skipped_count,
        'pass_rate': pass_rate,
        'results': results,
        'skipped': skipped,
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
            print(f"  {r['id']}: {r['task']} ({r['attempts']} 次尝试)")

    if skipped:
        print(f"\n跳过的任务:")
        for s in skipped:
            print(f"  {s['id']}: {s['task']} ({s['reason']})")

    print(f"{'='*60}")

    return report


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description='测试循环工作流')
    parser.add_argument('--quick', action='store_true', help='只运行第一批任务')
    parser.add_argument('--site', help='只运行指定网站的任务')
    parser.add_argument('--max-retries', type=int, default=MAX_RETRIES, help='最大重试次数')
    parser.add_argument('--report', default='test_cycle_report.json', help='报告输出路径')

    args = parser.parse_args()

    # 过滤任务
    tasks = TASKS

    if args.quick:
        tasks = [t for t in tasks if t['priority'] == 1]
    elif args.site:
        tasks = [t for t in tasks if t['site'] == args.site]

    if not tasks:
        print('没有匹配的任务')
        sys.exit(1)

    # 运行测试循环
    report = run_test_cycle(tasks, max_retries=args.max_retries)

    # 保存报告
    with open(args.report, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f'\n报告已保存: {args.report}')

    # 返回退出码
    sys.exit(0 if report['skipped'] == 0 else 1)


if __name__ == '__main__':
    main()
