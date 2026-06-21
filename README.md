# Agentic Playwright MCP

让 AI Agent 写 Python 脚本来控制浏览器的 MCP Server 框架。

基于 Playwright，支持可选的 [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) 反检测引擎。

## 核心理念

**AI 不是逐个调用工具，而是编写 Python 脚本。**

```
用户意图 → AI 查找技能 → AI 参考范例生成脚本 → 脚本引擎执行 → 浏览器操作
   ↳ 若未命中 → 检索通用模板 → 生成临时脚本 → 沙箱执行
   ↳ 若失败 → 自愈机制尝试 → 视觉 fallback → 记录新经验
```

## 框架能力（已实现）

| 模块 | 说明 | 状态 |
|------|------|------|
| **Agent 循环** | OBSERVE→PLAN→ACT 自主执行 | ✅ |
| **脚本引擎** | 受限沙箱执行 AI 生成的 Python 脚本 | ✅ |
| **脚本生成器** | 智能任务意图解析，支持 10+ 种任务类型 | ✅ |
| **控件层** | `smart_login`, `smart_search` 等 15 个高级函数 | ✅ |
| **技能库** | 16 个技能（12 站点 + 4 通用模板） | ✅ |
| **视觉模块** | 截图 + 多模态 LLM 理解页面 | ✅ |
| **自愈机制** | 选择器自动降级 + 优先级提升 | ✅ |
| **错误恢复** | 弹窗处理、超时重试、页面刷新 | ✅ |
| **脚本持久化** | 保存/加载/搜索脚本，记录使用统计 | ✅ |
| **事件钩子** | EventBus + 7 种标准事件 | ✅ |
| **插件系统** | SkillBase 抽象类 + skills.yaml 声明式配置 | ✅ |
| **Web GUI** | 浏览器可视化操作界面 | ✅ |
| **Python SDK** | `from src.sdk import AgentLoop` | ✅ |
| **CLI** | `browser-agent serve/run/doctor/gui` | ✅ |
| **CloakBrowser** | 反检测浏览器引擎集成 | ✅ |

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/zceeeeee/agentic-playwright-mcp.git
cd agentic-playwright-mcp

# 2. 安装
pip install -e .
playwright install chromium

# 3. 启动 GUI
browser-agent gui --port 8081
```

打开浏览器访问 **http://localhost:8081**

## 使用方式

### 方式一：Web GUI（推荐）

```bash
browser-agent gui --port 8081
```

在网页中输入任务，点击执行，实时查看结果。

### 方式二：CLI

```bash
# 启动 MCP 服务（给 Claude Desktop 用）
browser-agent serve

# 单次执行任务
browser-agent run "帮我在百度搜索 Python 教程" --max-steps 5

# 检查环境
browser-agent doctor
```

### 方式三：Python SDK

```python
from src.sdk import AgentLoop

with AgentLoop(headless=True) as agent:
    result = agent.run("帮我在百度搜索 Python 教程")
    print(result.output)
```

### 方式四：MCP 工具（Claude Desktop）

```json
{
  "mcpServers": {
    "browser": {
      "command": "browser-agent",
      "args": ["serve"]
    }
  }
}
```

## MCP 工具列表（8 个）

| 工具 | 说明 |
|------|------|
| `run_task` | 自然语言驱动的自主 Agent 循环 |
| `browse_skills` | 按关键词或 URL 查找技能库 |
| `get_skill` | 获取技能源码和说明文档 |
| `run_script` | 在受限沙箱中执行 Python 脚本 |
| `analyze_page` | 截图 + 多模态 LLM 分析页面（需 API Key） |
| `browser_launch` | 启动 Chromium 浏览器 |
| `screenshot` | 截取当前页面截图 |
| `ping` | 健康检查 |

## 已适配站点（12 个）

| 站点 | 任务类型 |
|------|---------|
| 百度搜索 | 搜索关键词 |
| Google 搜索 | 搜索关键词 |
| Bing 搜索 | 搜索关键词 |
| GitHub 登录 | 登录账号 |
| GitHub 搜索 | 搜索仓库/代码 |
| GitHub 仓库 | 查看仓库列表 |
| Amazon | 搜索商品 |
| Gmail | 查看收件箱 |
| Outlook | 查看收件箱 |
| YouTube | 搜索视频 |
| 微博 | 搜索 |
| 知乎 | 搜索 |

## 通用模板（4 个）

| 模板 | 说明 |
|------|------|
| `login_flow` | 通用登录流程 |
| `search_flow` | 通用搜索流程 |
| `form_fill` | 通用表单填写 |
| `pagination` | 通用分页翻页 |

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  用户界面层                                                │
│  Web GUI │ CLI │ Python SDK │ MCP (Claude Desktop)       │
└──────┬──────────┬──────────┬────────────┬───────────────┘
       │          │          │            │
       ▼          ▼          ▼            ▼
┌─────────────────────────────────────────────────────────┐
│  MCP 协议层（8 个工具）                                    │
│  run_task │ browse_skills │ run_script │ analyze_page   │
└─────────────────────────┬───────────────────────────────┘
                          │
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
┌─────────────┐  ┌──────────────┐  ┌─────────────────┐
│ Agent 引擎   │  │  技能库       │  │  视觉引擎        │
│             │  │              │  │                 │
│ • 循环控制   │  │ • 16 个技能   │  │ • 截图分析       │
│ • 脚本生成   │  │ • 插件系统   │  │ • 元素定位       │
│ • 错误恢复   │  │ • 自动发现   │  │ • 页面理解       │
│ • 脚本持久化 │  │              │  │                 │
└──────┬──────┘  └──────┬───────┘  └────────┬────────┘
       │                │                   │
       ▼                ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│  执行引擎层                                                │
│  脚本沙箱 │ 控件函数 │ 原语操作 │ 域配置 │ 自愈机制        │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  浏览器层                                                  │
│  Playwright（默认） │ CloakBrowser（反检测）               │
└─────────────────────────────────────────────────────────┘
```

## 插件化技能

添加新技能只需两步：

1. 在 `skills.yaml` 中声明元信息
2. 在 `src/skill_library/domains/` 中放置 `.py` 文件

```yaml
# src/skill_library/skills.yaml
skills:
  - id: domain/my_site
    name: 我的网站
    type: domain
    triggers: ["我的网站", "mysite"]
    url_patterns: ["mysite.com"]
    description: 我的网站适配器
```

```python
# src/skill_library/domains/my_site.py
def run(keyword: str):
    """在我的网站搜索关键词。"""
    goto("https://www.mysite.com")
    fill("#search", keyword)
    click("#search-btn")
    wait_for_navigation()
```

## 脚本引擎可用函数

```python
# 导航
goto("https://example.com")
go_back()
reload()

# 元素操作（支持多个备选选择器）
click("#button", ".fallback-btn")
fill("#input", "hello")

# 域配置驱动（带自愈）
smart_click("search_button", domain="baidu")
smart_fill("search_input", "Python 教程", domain="baidu")

# 组合操作
smart_login("github", "user", "pass")
smart_search("baidu", "Python 教程")
smart_fill_form("example", {"name": "张三", "email": "test@test.com"})

# 等待
wait_for_navigation(timeout=10)
wait_for_element("#result", timeout=10)
wait(2.0)

# 页面信息
url = get_url()
title = get_title()
text = get_text()
screenshot("page.png")
```

## CloakBrowser 反检测引擎

```bash
pip install -e ".[stealth]"
USE_CLOAKBROWSER=true browser-agent gui
```

| 检测服务 | Playwright | CloakBrowser |
|---------|-----------|-------------|
| reCAPTCHA v3 | 0.1 (bot) | **0.9** (human) |
| Cloudflare Turnstile | FAIL | **PASS** |
| FingerprintJS | DETECTED | **PASS** |

## 项目结构

```
agentic-playwright-mcp/
├── src/
│   ├── server.py                     # MCP 入口（8 个工具）
│   ├── cli.py                        # CLI (serve/run/doctor/gui)
│   ├── sdk.py                        # Python SDK
│   ├── config.py                     # 配置加载
│   ├── logging.py                    # 结构化日志
│   ├── core/
│   │   ├── agent_loop.py             # Agent 循环引擎
│   │   ├── script_engine.py          # 脚本执行引擎
│   │   ├── script_generator.py       # 任务意图解析 + 脚本生成
│   │   ├── script_store.py           # 脚本持久化存储
│   │   ├── browser_manager.py        # 双引擎浏览器管理
│   │   ├── event_bus.py              # 事件钩子系统
│   │   ├── recovery.py               # 错误恢复管理器
│   │   └── vision.py                 # 视觉模块
│   ├── gui/
│   │   └── app.py                    # Web GUI
│   ├── layer_1/actions.py            # 原子操作
│   ├── layer_2/controls.py           # 高级控件函数
│   ├── layer_3/                      # 域配置 + 自愈
│   └── skill_library/                # 标准脚本库
│       ├── skill_base.py             # SkillBase 抽象类
│       ├── skills.yaml               # 声明式配置
│       ├── registry.py               # 技能注册
│       ├── domains/                  # 12 个站点适配器
│       ├── interactions/             # 4 个通用模板
│       └── guides/                   # 说明文档
├── domains/                          # 站点选择器配置
├── tests/                            # 558 个测试，全部通过
├── docs/                             # MkDocs 文档
├── examples/                         # 示例脚本
└── Makefile                          # 快捷命令
```

## 开发

```bash
make dev      # 安装依赖
make test     # 跑测试（558 个）
make lint     # 代码检查
make format   # 自动修复
make clean    # 清理缓存
make docs     # 启动文档服务器
```

## 统计

| 指标 | 数值 |
|------|------|
| Python 源文件 | 46 个 |
| 测试文件 | 22 个 |
| 测试用例 | 558 个，全部通过 |
| MCP 工具 | 8 个 |
| CLI 命令 | 4 个 |
| 技能库 | 16 个（12 站点 + 4 模板） |
| 控件函数 | 15 个 |

## License

MIT
