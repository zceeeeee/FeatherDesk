# API 参考

本文档列出 Agentic Playwright MCP 提供的所有 MCP 工具。

## 工具列表

| 工具 | 说明 | 参数 |
|------|------|------|
| [`browse_skills`](#browse_skills) | 按关键词或 URL 查找技能 | `query`: str |
| [`get_skill`](#get_skill) | 获取技能源码和说明文档 | `skill_id`: str |
| [`run_script`](#run_script) | 在受限沙箱中执行 Python 脚本 | `script`: str, `timeout`: int |
| [`analyze_page`](#analyze_page) | 截图 + 多模态 LLM 分析页面 | `prompt`: str, `model`: str |
| [`browser_launch`](#browser_launch) | 启动 Chromium 浏览器 | `headless`: bool, `use_cloak`: bool |
| [`browser_launch_with_domain`](#browser_launch_with_domain) | 带站点 cookie 启动浏览器 | `domain`: str |
| [`auth_list`](#auth_list) | 列出所有站点的登录状态 | 无 |
| [`auth_save`](#auth_save) | 保存当前站点的 cookie | `domain`: str |
| [`auth_delete`](#auth_delete) | 删除某站点的 cookie | `domain`: str |
| [`screenshot`](#screenshot) | 截取当前页面截图 | `name`: str |
| [`ping`](#ping) | 健康检查 | 无 |

---

## LLM 配置 API

Web GUI 提供的 LLM 配置接口（非 MCP 工具）。

### GET /api/llm/status

检查 LLM 是否已配置。

**返回**：

```json
{
  "configured": true,
  "provider": "openai",
  "has_openai": true,
  "has_anthropic": false
}
```

### POST /api/llm/setup

保存 LLM 配置到 `.env` 文件。

**请求**：

```json
{
  "provider": "openai",
  "api_key": "sk-xxx",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini"
}
```

**返回**：

```json
{
  "success": true,
  "provider": "openai"
}
```

**Provider 默认值**：

| Provider | Base URL | Model |
|----------|----------|-------|
| `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` |
| `anthropic` | `https://api.anthropic.com` | `claude-haiku-4-5-20251001` |

---

## browse_skills

按关键词或 URL 查找技能库中的匹配技能。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | `str` | 是 | 搜索关键词或 URL |

### 返回值

```json
{
  "skills": [
    {
      "id": "baidu_search",
      "name": "百度搜索",
      "description": "在百度搜索关键词并获取结果",
      "triggers": ["百度", "搜索", "baidu"],
      "url_patterns": ["*.baidu.com"],
      "priority": 10
    }
  ],
  "total": 1
}
```

### 示例

```python
# 按关键词查找
result = await browse_skills("百度 搜索")

# 按 URL 查找
result = await browse_skills("https://www.baidu.com")
```

### 匹配逻辑

1. **关键词匹配**：将查询词与技能的 `triggers` 列表匹配
2. **URL 模式匹配**：将 URL 与技能的 `url_patterns` 匹配
3. **优先级排序**：匹配结果按 `priority` 降序排列
4. **返回 Top N**：默认返回前 5 个匹配结果

---

## get_skill

获取技能源码和说明文档。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `skill_id` | `str` | 是 | 技能 ID |

### 返回值

```json
{
  "id": "baidu_search",
  "name": "百度搜索",
  "description": "在百度搜索关键词并获取结果",
  "source_code": "class BaiduSearchSkill(SkillBase):\n    ...",
  "guide": "# 如何实现百度搜索\n\n## 适用场景\n...",
  "config": {
    "name": "baidu",
    "base_url": "https://www.baidu.com",
    "locators": {...}
  }
}
```

### 示例

```python
result = await get_skill("baidu_search")
print(result["source_code"])
print(result["guide"])
```

---

## run_script

在受限沙箱中执行 Python 脚本。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `script` | `str` | 是 | - | Python 脚本内容 |
| `timeout` | `int` | 否 | `30` | 执行超时时间（秒） |

### 返回值

```json
{
  "success": true,
  "output": "搜索完成\n当前 URL: https://www.baidu.com/s?wd=Python",
  "screenshots": ["page_001.png", "page_002.png"],
  "error": null,
  "execution_time": 5.23
}
```

### 脚本可用函数

```python
# 导航
goto(url: str) -> None
go_back() -> None
go_forward() -> None
reload() -> None

# 元素操作（直接选择器）
click(selector: str, *fallbacks: str) -> None
fill(selector: str, value: str) -> None

# 元素操作（域配置驱动，带自愈）
smart_click(element: str, domain: str) -> None
smart_fill(element: str, value: str, domain: str) -> None

# 组合操作
smart_login(domain: str, username: str, password: str, **kwargs) -> None
smart_search(domain: str, query: str, **kwargs) -> None
smart_fill_form(domain: str, data: dict, **kwargs) -> None

# Cookie 持久化
save_cookies(domain: str) -> str
load_cookies(domain: str) -> str

# 等待
wait(seconds: float) -> None
wait_for_navigation(timeout: int = 10) -> None
wait_for_element(selector: str, timeout: int = 10) -> None

# 页面信息
get_url() -> str
get_title() -> str
get_text() -> str
screenshot(name: str = "page.png") -> str

# 输出
print(*args, **kwargs) -> None
log(message: str) -> None
```

### 安全限制

- 禁止 `import` 语句（白名单除外）
- 禁止 `exec`, `eval`, `__import__` 等危险函数
- 禁止文件系统访问（除 screenshot 输出）
- 禁止网络访问（除浏览器操作）
- 执行超时控制（默认 30 秒）

### 示例

```python
script = """
# 导航到百度
goto("https://www.baidu.com")

# 输入搜索关键词
fill("#kw", "Python 教程")

# 点击搜索按钮
click("#su")

# 等待页面加载
wait_for_navigation()

# 截图
screenshot("result.png")

# 输出结果
print("搜索完成")
print("当前 URL:", get_url())
"""

result = await run_script(script, timeout=30)
```

---

## analyze_page

截图 + 多模态 LLM 分析页面。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `prompt` | `str` | 否 | `"描述这个页面的内容"` | 分析提示词 |
| `model` | `str` | 否 | `"claude-3-opus"` | 使用的模型 |

### 返回值

```json
{
  "analysis": "这是一个百度搜索结果页面，显示了 Python 教程的搜索结果...",
  "screenshot": "page_analysis.png",
  "model": "claude-3-opus"
}
```

### 使用场景

- 验证码识别
- 动态页面理解
- 选择器失效时的视觉定位
- 页面状态验证

### 示例

```python
# 基本使用
result = await analyze_page()

# 自定义提示词
result = await analyze_page(
    prompt="找到页面上的登录按钮并描述其位置",
    model="claude-3-opus"
)
```

### 配置要求

需要配置 API Key：

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-xxx
# 或
OPENAI_API_KEY=sk-xxx
```

---

## browser_launch

启动 Chromium 浏览器。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `headless` | `bool` | 否 | `False` | 是否使用无头模式 |
| `use_cloak` | `bool` | 否 | `False` | 是否使用 CloakBrowser |

### 返回值

```json
{
  "success": true,
  "engine": "playwright",
  "browser": "chromium",
  "headless": false
}
```

### 示例

```python
# 使用 Playwright
result = await browser_launch()

# 使用 CloakBrowser 反检测
result = await browser_launch(use_cloak=True)

# 无头模式
result = await browser_launch(headless=True)
```

### CloakBrowser 反检测

| 检测服务 | Playwright | CloakBrowser |
|---------|-----------|-------------|
| reCAPTCHA v3 | 0.1 (bot) | **0.9** (human) |
| Cloudflare Turnstile | FAIL | **PASS** |
| FingerprintJS | DETECTED | **PASS** |

启用 CloakBrowser：

```bash
pip install -e ".[stealth]"
```

---

## browser_launch_with_domain

启动浏览器并自动加载已保存的站点 cookie。如果浏览器已运行，会创建新的 context（不重启浏览器）。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domain` | `str` | 是 | 站点名（对应 `domains/{domain}.yaml`） |

### 返回值

```
Browser ready for 'baidu' (with saved auth). Current page: https://www.baidu.com
```

### 示例

```python
# 带已保存的 cookie 启动
result = await browser_launch_with_domain("baidu")

# 如果没有保存过 cookie，等同于普通启动
result = await browser_launch_with_domain("new_site")
```

---

## auth_list

列出所有站点及其登录状态。

### 返回值

```
Domain authentication status:
  ✓ baidu
  ✗ github
  ✓ google
```

### 示例

```python
result = await auth_list()
```

---

## auth_save

保存当前浏览器的 cookie / localStorage 到本地文件。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domain` | `str` | 是 | 站点名 |

### 返回值

```
Auth saved for 'baidu': C:\Users\user\.agentic-playwright\auth\baidu.json
```

### 示例

```python
# 登录后手动保存
await auth_save("github")
```

---

## auth_delete

删除某站点已保存的 cookie。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domain` | `str` | 是 | 站点名 |

### 返回值

```
Auth deleted for 'github'.
```

---

## screenshot

截取当前页面截图。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | `str` | 否 | `"page.png"` | 截图文件名 |

### 返回值

```json
{
  "success": true,
  "path": "screenshots/page.png",
  "size": {
    "width": 1920,
    "height": 1080
  }
}
```

### 示例

```python
result = await screenshot("my_page.png")
```

---

## ping

健康检查。

### 参数

无

### 返回值

```json
{
  "status": "ok",
  "version": "0.1.0",
  "uptime": 3600,
  "browser": {
    "connected": true,
    "engine": "playwright"
  }
}
```

### 示例

```python
result = await ping()
print(result["status"])  # "ok"
```

---

## 错误处理

所有工具在出错时返回统一的错误格式：

```json
{
  "success": false,
  "error": {
    "type": "TimeoutError",
    "message": "脚本执行超时 (30秒)",
    "details": {...}
  }
}
```

### 常见错误类型

| 错误类型 | 说明 | 处理建议 |
|---------|------|---------|
| `TimeoutError` | 操作超时 | 增加 timeout 参数，或检查网络 |
| `ElementNotFoundError` | 元素未找到 | 检查选择器，使用备选选择器 |
| `NavigationError` | 导航失败 | 检查 URL，增加等待时间 |
| `SecurityError` | 安全限制 | 检查脚本是否包含禁止的操作 |
| `BrowserError` | 浏览器错误 | 重新启动浏览器 |
| `LLMError` | LLM 调用失败 | 检查 API Key 配置 |

---

## 使用示例

### 完整的百度搜索流程

```python
# 1. 启动浏览器
await browser_launch()

# 2. 查找技能
skills = await browse_skills("百度 搜索")

# 3. 获取技能详情
skill = await get_skill("baidu_search")

# 4. 执行搜索脚本
script = """
goto("https://www.baidu.com")
fill("#kw", "Python 教程")
click("#su")
wait_for_navigation()
screenshot("result.png")
print("搜索完成")
"""
result = await run_script(script)

# 5. 分析结果
analysis = await analyze_page("描述搜索结果")
print(analysis["analysis"])
```

### 使用技能库

```python
# 1. 查找技能
skills = await browse_skills("登录")

# 2. 获取登录技能
skill = await get_skill("login_flow")

# 3. 参考技能生成脚本
script = f"""
# 参考 {skill['name']} 技能
goto("https://example.com/login")
fill("#username", "admin")
fill("#password", "123456")
click("#login-btn")
wait_for_navigation()
print("登录成功")
"""

# 4. 执行
result = await run_script(script)
```
