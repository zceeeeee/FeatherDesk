# 快速开始

本指南将在 5 分钟内带你从零开始运行 Agentic Playwright MCP。

## 前置条件

- Python 3.11+
- Git
- （可选）Claude Desktop 或其他支持 MCP 的客户端

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/agentic-playwright-mcp.git
cd agentic-playwright-mcp
```

### 2. 安装依赖

```bash
# 一键安装：Python 依赖 + Playwright Chromium 浏览器
make dev
```

!!! tip "国内加速"
    如果 Playwright 浏览器下载慢，可以设置镜像：
    ```bash
    export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
    make dev
    ```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# LLM Provider: "openai" (默认) | "anthropic"
LLM_PROVIDER=openai

# OpenAI 兼容 API（支持 DeepSeek、本地模型等）
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# 或 Anthropic
# ANTHROPIC_API_KEY=sk-ant-xxx
# ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# 可选：浏览器引擎
# USE_CLOAKBROWSER=false    # true = CloakBrowser 反检测引擎
# BROWSER_HEADLESS=false    # true = 无头模式（无窗口）

# 可选：日志配置
# LOG_LEVEL=INFO            # DEBUG, INFO, WARNING, ERROR
# LOG_FORMAT=text           # json 或 text
```

!!! tip "首次启动自动引导"
    如果没有配置 API Key，`browser-agent gui` 和 Web GUI 都会自动弹出引导界面，让你选择 Provider 并输入 API Key。配置会自动保存到 `.env` 文件。

## 启动服务

```bash
# 方式一：使用 Makefile
make run

# 方式二：直接运行
agentic-playwright-mcp

# 方式三：使用 CLI
browser-agent serve
```

服务启动后，MCP Server 会在 stdio 模式下等待客户端连接。

## 配置 Claude Desktop

在 Claude Desktop 的配置文件中添加 MCP Server：

=== "macOS"

    编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

    ```json
    {
      "mcpServers": {
        "agentic-playwright-mcp": {
          "command": "agentic-playwright-mcp",
          "env": {
            "ANTHROPIC_API_KEY": "sk-ant-xxx"
          }
        }
      }
    }
    ```

=== "Windows"

    编辑 `%APPDATA%\Claude\claude_desktop_config.json`：

    ```json
    {
      "mcpServers": {
        "agentic-playwright-mcp": {
          "command": "agentic-playwright-mcp",
          "env": {
            "ANTHROPIC_API_KEY": "sk-ant-xxx"
          }
        }
      }
    }
    ```

## 第一次对话

重启 Claude Desktop 后，你可以直接对话：

```
用户: 帮我在百度搜索 Python 教程

AI:
  1. 调用 browse_skills(query="百度 搜索")
  2. 获取 baidu_search.py 的源码
  3. 参考源码，生成脚本并执行
  4. 返回搜索结果
```

## 使用 CLI 单次执行

如果你只想快速测试一个任务，可以使用 CLI 的 `run` 命令：

```bash
# 执行单次任务
browser-agent run "帮我在百度搜索 Python 教程" --max-steps 5

# 无头模式
browser-agent run "截图当前页面" --headless

# 使用 CloakBrowser 反检测
browser-agent run "访问某网站" --cloak
```

## 检查环境

使用 `doctor` 命令检查环境是否配置正确：

```bash
browser-agent doctor
```

输出示例：

```
环境检查结果：
  Python 版本: 3.11.0 ✓
  Playwright: 已安装 ✓
  Chromium: 已安装 ✓
  .env 文件: 已存在 ✓
  API Key: 已配置 ✓
```

## 下一步

- [架构概览](architecture.md) — 了解系统分层设计
- [技能库](skills.md) — 学习如何创建自定义技能
- [API 参考](api.md) — 查看完整的 MCP 工具文档
