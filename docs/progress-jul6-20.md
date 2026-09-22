# 项目进度报告：2026.07.06 ~ 2026.07.20

> 本文档整合了 Agentic Playwright Harness 项目从 7 月 6 日到 7 月 20 日的全部开发进展，涵盖功能实现、架构演进与技术细节。

---

## 📊 总体数据

| 指标 | 数值 |
|------|------|
| 提交总数 | ~80+ commits |
| 文件变更 | **157 files**, +26,334 / -1,681 行 |
| 合并 PR | #55 ~ #93（约 39 个 PR） |
| 新增核心目录 | `src/core/explore/`、`src/desktop/`、`desktop/src/` |
| Python 后端变更 | +10,016 / -1,642 行（42 files） |
| Electron 前端变更 | +3,438 行（28 files，全新） |

---

## 目录

1. [Explore 模式 ](#1-explore-模式)
2. [Desktop 应用（FeatherDesk）— 全新 Electron GUI](#2-desktop-应用featherdesk--全新-electron-gui)
3. [命令路由架构 — 召回 + 精排](#3-命令路由架构--召回--精排)
4. [MiMo 推理模型适配](#4-mimo-推理模型适配)
5. [微信桌面自动化](#5-微信桌面自动化)
6. [WPS 文档导出增强](#6-wps-文档导出增强)
7. [经验系统集成 — 记忆架构与自进化](#7-经验系统集成)
8. [取消机制](#8-取消机制)
9. [API 连通性测试](#9-api-连通性测试)
10. [其他改进与 Bug 修复](#10-其他改进与-bug-修复)
11. [附录：完整 PR 列表](#11-附录完整-pr-列表)

---

## 1. Explore 模式

Explore 模式是这 15 天的**核心工程**，经历了 5 个阶段、20+ 次提交的迭代，最终形成了一套完整的自主网页探索系统。

### 1.1 最终架构

```
src/core/explore/
├── agent.py            # 探索编排器 — 主循环状态机 (~1383 行)
├── executor.py         # 动作执行器 — 22 种原子操作 (~747 行)
├── snapshot.py         # 快照引擎 — ARIA 语义树提取 (~808 行)
├── experience.py       # 经验管理 — 失败记忆 + 技能升级 (~213 行)
├── vision_router.py    # 视觉回退 — Canvas/WebGL 场景兜底 (~230 行)
├── ref_generator.py    # 引用生成器
└── models.py           # 数据模型 — 17 个 Pydantic 模型 (~326 行)
```

**总代码量：~3,700+ 行 Python**

### 1.2 核心模块详解

#### 1.2.1 ExploreAgent — 探索编排器（`agent.py`）

ExploreAgent 是整个 Explore 模式的大脑，实现了一个 **OBSERVE → PLAN → ACT** 循环状态机。

**入口策略（三级解析）：**

| 优先级 | 策略           | 实现                                                       |
| --- | ------------ | -------------------------------------------------------- |
| 1   | 硬编码入口表       | `_ENTRYPOINTS` 字典，覆盖 12 个已知站点（GitHub、B站、淘宝、知乎等）          |
| 2   | LLM 解析目标 URL | `_resolve_initial_entry_url_via_llm()` — 让 LLM 推断用户想去的网站 |
| 3   | Bing 搜索降级    | `_resolve_entry_url_via_search()` — 搜索 + LLM 选择最佳结果      |

**主循环逻辑：**

```python
# 简化后的核心循环
while step < max_steps:
    snapshot_result = self.snapshot(step)          # 1. ARIA 快照
    action_batch = self.plan_actions(task)          # 2. LLM 规划动作
    execution = self.execute(step, executor)        # 3. 执行动作

    if execution.status == "done":
        self.save_experience(step)                  # 4. 保存成功经验
        return "done"
    elif execution.status == "stuck":               # 5. 循环/熔断检测
        return ask_user_for_help()
```

**鲁棒性机制：**

- **循环检测**：`_check_loop_detection()` 计算页面签名（URL + 排序后的交互元素 refs），连续 2 轮相同页面即判定循环
- **熔断器**：`_check_circuit_breaker()` 按动作类型统计连续失败，同一类型连续 3 次触发熔断
- **操作历史注入**：最近 10 步操作记录注入 LLM prompt，避免重复犯错
- **失败经验降级**：失败时自动降低已有相似经验的 confidence 值

#### 1.2.2 ExploreExecutor — 动作执行器（`executor.py`）

执行器负责将 LLM 规划的动作批量转化为 Playwright 操作。

**支持的 22 种原子动作：**

| 类别 | 动作 |
|------|------|
| 点击 | `click`, `double_click`, `click_at`（坐标点击）, `hover`, `hover_at` |
| 输入 | `fill`（直接设值）, `type`（逐字符输入）, `keyboard`（快捷键） |
| 导航 | `goto`, `back`, `forward`, `scroll` |
| 交互 | `select`, `check`, `uncheck`, `drag`, `upload`, `dialog` |
| 控制 | `wait`, `screenshot`, `snapshot`, `evaluate`（JS 逃生舱） |
| 探索 | `request_deep_scan`, `complete`, `pause_for_input`（用户交互入口） |

**关键机制：**

- **Ref 校验**：每个元素通过 `data-explore-ref` 属性定位，执行前校验 ref 是否过期
- **版本一致性**：ActionBatch 必须携带 snapshot version，防止在过期快照上操作
- **视觉坐标转换**：`_normalize_visual_actions()` 将 Vision 模型返回的 `v1`/`v2` 引用转换为 `click_at(x, y)` 坐标动作，带有 confidence 阈值和敏感操作拦截
- **暂停等待用户**：`pause_for_input` 支持简单提问（`value`）和结构化表单（`fields`）两种模式

#### 1.2.3 SnapshotGenerator — 快照引擎（`snapshot.py`）

负责从 Playwright 页面提取 ARIA 语义树，生成可供 LLM 理解的页面快照。

**两种提取模式：**

| 模式 | 方法 | 说明 |
|------|------|------|
| 自定义 JS | `_extract_via_custom_js()` | 注入 ~180 行 JS，遍历 DOM 计算 CSS 路径、推断 ARIA role、获取 accessible name。支持 Shadow DOM 穿透 |
| 原生 API | `_extract_via_native()` | 使用 Playwright `aria_snapshot(mode='ai')`，解析 YAML 输出。目前禁用（缺少 CSS selector） |

**深度扫描**：`force_deep_scan()` 使用更激进的 JS（150 个元素上限 vs 标准 50 个），额外检测 tabindex、onclick 处理器、常见 CSS 类模式（search, chat, editor, dropdown 等）。

**Ref 同步**：`_sync_refs_to_dom()` 为每个 ARIA 节点设置 `data-explore-ref` 属性到真实 DOM 元素上，使 executor 能通过 ref 定位元素。

#### 1.2.4 VisionRouter — 视觉回退（`vision_router.py`）

当 ARIA 快照质量不足时（Canvas/WebGL 内容），通过视觉模型补充。

**工作流程：**

1. `inspect_surface(page)` — 廉价 DOM 检查：统计 canvas、WebGL、iframe 数量和可见 canvas 面积比
2. `aria_quality(snapshot)` — 评分 ARIA 质量（0-1）：交互元素数量 + 名称覆盖率
3. `should_enhance(snapshot)` — 判断是否需要视觉增强
4. `enhance(page, snapshot, task)` — 截图 → 发送给 VisionModule → 归一化坐标为 `VisualTarget`

**安全设计：** 视觉目标被明确定义为"不可信感知数据"，坐标是视口相对的，绝不直接执行。executor 在转换时会做 confidence 阈值检查和敏感操作拦截。

**预算控制：** 每任务 5 次、每导航周期 2 次调用上限。

#### 1.2.5 ExperienceManager — 经验管理（`experience.py`）

**经验生命周期：**

```
探索成功 → save(ExploreExperience)
                ↓
下次类似任务 → find_similar() (Jaccard 相似度, 阈值 0.8)
                ↓
confidence >= 0.8 且 3+ 次成功 → try_upgrade_to_skill() → 自动生成 Python 脚本
                ↓
失败 → update_confidence(-0.15) → confidence < 0.3 → deprecated
```

#### 1.2.6 数据模型（`models.py`）

核心 Pydantic 模型：

| 模型                        | 说明                                                                   |
| ------------------------- | -------------------------------------------------------------------- |
| `ActionType` (enum, 22 值) | 所有支持的动作类型                                                            |
| `AriaNode`                | 递归 ARIA 树节点：role, name, ref, tag, selector, children                 |
| `SnapshotResponse`        | 完整快照：version, nodes, interactive_count, aria_quality, visual_targets |
| `Action`                  | 单个原子动作，含 ref/value/url/x/y/dialog_action/delay/intent/reasoning      |
| `ActionBatch`             | 动作批次 + task_complete + need_vision                                   |
| `ExploreExperience`       | 经验条目：actions, element_map, confidence, success/fail counts           |
| `ExploreConfig`           | 30+ 配置字段                                                             |

### 1.3 LoginGuard — 登录守卫（`login_guard.py`，~383 行）

独立于 Explore 的通用登录检测模块。

**检测逻辑：**
1. 注入 ~80 行 JS 扫描页面中的登录关键词（"登录"、"sign in"、"login"、"register" 等）
2. 向上遍历 DOM 查找模态容器（role=dialog, aria-modal, fixed/absolute 定位, 登录相关 CSS 类）
3. 检测到登录弹窗后进入等待循环（1s 轮询，默认 300s 超时）
4. 等待条件：登录弹窗消失 + 浏览器 storage 指纹变化（cookies/localStorage）

**多语言支持**：中英文登录关键词全覆盖。

**频率限制**：500ms 内不重复检测，跳过非交互操作（scroll/wait/screenshot）。

**注意**：Explore 模式下 LoginGuard 被**禁用**（`enabled=False`），因为 Explore 有自己的 `pause_for_input` 机制处理登录。

### 1.4 开发时间线

| 阶段 | 日期 | 关键提交 | 内容 |
|------|------|----------|------|
| **Phase 1** | 7/6-7/8 | `8bdc368`, `1058775`, `2fbb9c2` | 基础搭建：aria_snapshot 引擎、LoginGuard 多语言、搜索跳过 |
| **Phase 2** | 7/8-7/10 | `166ccf5`, `512de9f`, `2eb2b4d` | 入口解析：Bing 搜索降级、规则兜底、已到站跳过 |
| **Phase 3** | 7/10-7/13 | `aec96b5`, `df35d15`, `a263ad3` | 架构重构：Agent 拆分、9 种新动作、深度扫描、多步操作 |
| **Phase 4** | 7/13-7/18 | `181a40b`, `9bb4609`, `ccd4ffb` | 鲁棒性：失败记忆、循环检测、熔断器、SPA 等待、snapshot 回退 |
| **Phase 5** | 7/14-7/18 | `9b1fd4c`, `737c541`, `52b903f` | 经验系统、URL 导航、Vision 回退 |

---

## 2. Desktop 应用（FeatherDesk）— 全新 Electron GUI

从零构建了一个完整的桌面客户端，代码量 +3,438 行（前端）+ 后端 API 服务。

### 2.1 技术栈

| 层级 | 技术 |
|------|------|
| 桌面框架 | Electron |
| 前端 | React + TypeScript + Vite |
| 状态管理 | Zustand |
| 后端通信 | HTTP REST + WebSocket |
| 持久化 | 本地 JSON 文件 + safeStorage 加密 |

### 2.2 双窗口架构

```
┌─────────────────────────────────────────────────┐
│                Electron Main Process              │
│                  (electron/main.ts)               │
│                                                   │
│  ┌──────────────┐    ┌───────────────────────┐   │
│  │  petWindow    │    │  dashboardWindow       │   │
│  │  80x80 透明   │    │  1000x720              │   │
│  │  无边框浮动   │    │  完整控制面板           │   │
│  │              │    │                        │   │
│  │ PetCircle    │    │  DashboardPage         │   │
│  │   ↓ 展开     │    │  ├─ ChatPanel          │   │
│  │ ChatPanel    │    │  ├─ HistoryView        │   │
│  │              │    │  ├─ SettingsView       │   │
│  │              │    │  ├─ AppearanceSettings │   │
│  │              │    │  ├─ SkillsView         │   │
│  │              │    │  ├─ LogsView           │   │
│  │              │    │  └─ AboutView          │   │
│  └──────────────┘    └───────────────────────┘   │
│                                                   │
│  ┌──────────────────────────────────────────────┐│
│  │  Python Backend (子进程)                      ││
│  │  python -m src.desktop.api                   ││
│  │  随机端口 + Bearer Token 认证                 ││
│  └──────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

两个窗口加载同一个 `index.html`，通过 `?view=pet|dashboard` 查询参数区分渲染内容。

### 2.3 核心模块

#### 2.3.1 Electron 主进程（`electron/main.ts`，693 行）

**职责：**

- **窗口管理**：petWindow（紧凑 80x80 浮动宠物，透明无边框）和 dashboardWindow（1000x720 控制面板）
- **宠物展开/收起**：pet window 在紧凑圆圈和完整聊天面板之间切换，智能锚点定位（根据屏幕象限决定展开方向）
- **后端进程管理**：spawn Python 后端（`python -m src.desktop.api`），注入随机端口和 auth token，支持重启
- **系统托盘**：中文托盘菜单（显示/展开/控制台/置顶/重启/隐藏/退出）
- **IPC 处理器**（~25 个）：宠物位置/展开、后端配置/重启、对话状态、设置 CRUD、外观偏好、外部链接、退出
- **持久化**：`userFile()` 读写 JSON 文件（宠物位置、窗口大小、设置、UI 偏好），API 密钥通过 `safeStorage` 加密
- **外观系统**：委托 `appearance.js` 模块，广播偏好变更到所有渲染窗口

#### 2.3.2 状态管理（`agentStore.ts`，605 行）

Zustand store，13 个状态字段 + 17 个 actions。

**状态字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `visualState` | `AgentVisualState` | 宠物/UI 状态：idle, running, waiting_confirmation, success, error |
| `currentConversationId` | `string/null` | 当前对话 |
| `messages` | `ChatMessage[]` | 当前对话消息 |
| `confirmations` | `ConfirmationRequest[]` | 待处理确认请求 |
| `conversations` | `Conversation[]` | 所有对话列表 |
| `backendConnected` | `boolean` | WebSocket 连接状态 |
| `runtime` | `RuntimeInfo/null` | 后端运行时信息（model, provider） |
| `logs` | `string[]` | 后端日志流（上限 500） |

**关键设计模式：**

- **乐观更新**：`sendMessage` 和 `cancelCurrentTask` 立即插入乐观消息
- **任务替代追踪**：`supersededTaskIds` set（上限 2000）忽略旧任务的事件
- **去重**：`dedupe()` 按任务锚定时间排序，`seenEvents` set 防止 WebSocket 事件重复
- **错误自动恢复**：error 状态 10 秒后自动回到 idle
- **资源清理**：切换对话时取消活跃任务、关闭浏览器

#### 2.3.3 桌面宠物系统

**PetCircle**（69 行）— 紧凑窗口根组件：
- 指针拖拽（5px 阈值防误触）
- 点击展开聊天面板
- 右键菜单

**PetAvatar**（76 行）— 宠物视觉组件：
- 两种渲染模式：经典 CSS 动画 / 动画图片（支持皮肤切换）
- 状态感知：idle、running、waiting_confirmation（发光效果）、success、error
- 图片加载失败自动降级到 CSS 渲染

**皮肤注册表**（`skinRegistry.ts`）：支持 classic、animated-cat、maltese 等皮肤

#### 2.3.4 外观设置（`AppearanceSettings.tsx`，357 行）

- 宠物皮肤选择器（单选 + 实时预览）
- 经典调色板（4 种内置颜色 + 重置）
- 自定义调色板 + 排版编辑器（4 色拾取器 + 字号滑块 + 字体颜色）
- 实时预览面板
- 对比度验证（低于 3:1 阻止保存，低于 4.5:1 警告）
- 调色板历史（最多 5 个自定义方案）

#### 2.3.5 API 层（`api.ts`，46 行）

```typescript
// 通信架构
apiRequest<T>(path, init)  → HTTP  → http://127.0.0.1:{port}  → Python Backend
eventSocket()              → WS    → ws://127.0.0.1:{port}    → 实时事件流
desktopSettings            → IPC   → window.desktopAgent      → Electron 主进程
```

所有通信走 localhost 到 spawned Python 后端。端口和 token 从 Electron 主进程获取。

### 2.4 关键技术问题解决

| 问题 | 解决方案 | 提交 |
|------|----------|------|
| 窗口拖拽不同步 | 原生移动与 Renderer 合成帧不一致，通过 `useWindowResize` hook 修复 | `24ca559` |
| IPC 安全 | `dashboard:open` handler 避免返回 `BrowserWindow` 对象 | `b988e0d` |
| GIF 命名错误 | 修正皮肤资源文件名 | `c16b084` |
| 历史对话重复 | `dedupe()` 按任务锚定时间排序去重 | `651ecfd` |
| 微信任务误开 Chromium | 任务类型判断跳过浏览器启动 | `651ecfd` |

---

## 3. 命令路由架构 — 召回 + 精排

### 3.1 架构演进

7 月 13 日的 `d75e69a` 提交将命令解析从**硬编码关键词门控**重构为**召回 + 精排**两阶段架构。

**Before（旧架构）：**
```
用户输入 → keyword_filter 硬匹配 → 命中/未命中（二元判定）
```

**After（新架构）：**
```
用户输入 → _recall_candidates() → 候选打分 → 阈值判定 → LLM 精排（可选）
```

### 3.2 SkillRouter 路由流程（`skill_router.py`，1555 行）

**Stage 1 — 候选召回（`_recall_candidates`）：** 零成本关键词/正则打分

| 打分项 | 权重 | 说明 |
|--------|------|------|
| `trigger_patterns`（正则） | 命中 = 0.95 直接返回 | 最高优先级 |
| `triggers`（子串） | 0.4 + 0.15/匹配（上限 3） | 多触发词叠加 |
| 示例 token 重叠 | 0.15 × 重叠率 | 与示例的相似度 |
| 描述关键词命中 | 0.1 × 命中率 | 兜底打分 |

**Stage 2 — 阈值判定：**

| 得分区间 | 行为 |
|----------|------|
| ≥ 0.8 且领先 > 0.1 | 直接命中，不走 LLM |
| 0.6 ~ 0.8 或多候选 | **LLM 精排** |
| < 0.6 | 丢弃 |

**Stage 3 — LLM 精排（`_llm_rank`）：** 发送候选 + 任务给 LLM，返回 `skill_id` / `"explore"` / `"None"`。使用 `response_format: json_object` 结构化输出。

### 3.3 AgentLoop 路由级联（`agent_loop.py`，2206 行）

`_do_plan()` 方法实现了 10 级路由级联：

```
PLAN 阶段路由决策：

  [0]   Explore 刚完成入口导航？ ──────────────────────→ 直接 EXPLORE
  [0.5] 已有 ARIA 快照？ ─────────────────────────────→ ExploreAgent.plan_actions()
  [0.6] Explore 模式已激活？ ─────────────────────────→ 跳过匹配，EXPLORE
  [1]   SkillRouter.route(task)
        ├─ 关键词直接命中 → ACT（执行脚本）
        └─ LLM 返回 "explore" → EXPLORE
  [2]   任务含显式 URL？ → 导航后重新 OBSERVE
  [3]   有高置信度经验（>0.7）？ → ACT（回放经验）
  [4]   推断目标站点 → 导航后重新 OBSERVE
  [5]   ScriptGenerator 简单任务 → ACT
  [6]   最终兜底 → EXPLORE 模式
```

### 3.4 MCP 工具列表（`server.py`，631 行）

| 类别 | 工具 |
|------|------|
| 基础 | `ping`, `browser_launch`, `screenshot` |
| 脚本 | `browse_skills`, `get_skill`, `run_script`, `analyze_page`, `run_task` |
| 认证 | `auth_list`, `auth_save`, `auth_delete`, `browser_launch_with_domain` |
| 面板 | `panel_toggle`, `panel_read`, `panel_log`, `panel_set_title`, `panel_prompt`, `panel_set_fields` |

核心入口是 `run_task`（第 311 行），委托给 `agent_loop.run_task()`，触发完整的 OBSERVE/PLAN/ACT/EXPLORE 循环。

### 3.5 ScriptEngine（`script_engine.py`，606 行）

沙箱化 Python 执行引擎：

- **安全限制**：`_SAFE_BUILTINS` 白名单，禁用 `import`/`open`/`exec`
- **注入函数**：`goto`, `click`, `fill`, `screenshot`, `mouse_click`, `hover`, `panel_log`, `panel_prompt` 等
- **登录守卫**：所有浏览器操作包裹 `GenericLoginGuard`，自动检测登录页面
- **LLM 集成**：`llm_generate_text` 可在脚本中调用 LLM 生成内容

---

## 4. MiMo 推理模型适配

针对小米 MiMo 推理模型做了 **6 次迭代修复**，核心问题是其响应格式与标准 OpenAI API 不兼容。

### 4.1 问题链

```
MiMo 模型行为：
  content 字段 ← 推理链（chain-of-thought）
  reasoning_content 字段 ← 实际答案

标准 OpenAI 行为：
  content 字段 ← 实际答案
  reasoning_content 字段 ← 不存在
```

这导致所有 JSON 解析（skill 路由、意图解析、动作规划）全部失败。

### 4.2 修复路径

| # | 提交 | 问题 | 方案 | 持久性 |
|---|------|------|------|--------|
| 1 | `dc2275c` | content 为空 | 降级读 reasoning_content | 过渡 |
| 2 | `dc34955` | 两字段都有内容 | 智能选择（看哪个像最终答案） | 过渡 |
| 3 | `a13af51` | 推理文本嵌套 JSON | 正则提取最后一个 `{...}` 块 | 过渡 |
| 4 | `189b827` | 根因：thinking mode | `chat_template_kwargs: {enable_thinking: false}` | **废弃** |
| 5 | `2faa30c` | 需要结构化输出 | `response_format: {type: json_object}` | **最终方案** |
| 6 | `613ab46` | 全局禁用 thinking | 所有 API 调用加 `enable_thinking: false` | 补充 |

### 4.3 最终方案（`llm_client.py`）

```python
# MiMo 特殊处理
def _is_mimo(model: str) -> bool:
    return "mimo" in model.lower()

# MiMo 调用差异：
# - 不传 temperature/top_p（不支持）
# - 使用 max_completion_tokens 代替 max_tokens
# - 支持 thinking: {type: "enabled"} 开启推理链
# - 视觉模块标记：mimo-v2.5-pro 是纯文本模型，不能用于视觉
```

`chat_json_with_retry`（`llm_utils.py`）处理 JSON 解析失败时用显式 "return strict JSON" prompt 重试，对推理模型尤为重要。

---

## 5. 微信桌面自动化

### 5.1 架构概览（`src/layer_1/wechat_client.py`，3119 行）

基于 `pywinauto` + 图像模板匹配的 Windows 原生微信自动化（非 Playwright）。

```
PywinautoWechatAutomation (~1950 行，主控类)
├── WeChatWindowManager (行 774) — 窗口生命周期管理
├── ElementLocator (行 980) — UI 元素定位（图像匹配 + 无障碍）
├── ScreenImageLocator (行 287) — 模板匹配引擎
└── 文件发送流程 (FileSendPhase 状态机)
```

### 5.2 功能清单

| 功能 | 说明 | 关键提交 |
|------|------|----------|
| 消息发送 | 私信、群消息、回车发送 | `75e7e84` |
| 文件发送 | 通过微信发送文件给联系人 | `2dd90bc` |
| 公众号关注 | 自动化关注流程（颜色识别修复按钮点击） | `ad03fcf` |
| 窗口控制 | 调整窗口大小和位置 | `718ca62` |
| 公众号消息 | 向公众号发送消息 | `b03fe0a` |

### 5.3 技术亮点

- **颜色识别修复**：关注按钮在不同状态下颜色不同，通过像素颜色判断按钮是否已按下，避免重复点击
- **文件发送状态机**：`FileSendPhase` 枚举追踪文件发送进度，支持断点续传和错误恢复
- **窗口控制**：通过 pywinauto 调整微信窗口大小和位置，解决拖动导致的界面不同步问题

### 5.4 失败尝试：wx CLI

尝试通过 `wx` CLI 工具读取微信聊天历史记录，但因 `session.db` 加密问题无法解密（`73d3c86`），最终放弃并删除（`c2f8408`）。

---

## 6. WPS 文档导出增强

### 6.1 功能演进

| 提交 | 内容 |
|------|------|
| `8457667` | 引导式 Markdown 格式化输出，适配 WPS |
| `dbd79b0` | 支持下划线和字体颜色 |

### 6.2 技术实现（`src/layer_1/wps_writer.py`，809 行）

- **COM 自动化**：通过 `win32com` 控制 WPS Writer 或 Microsoft Word
- **富文本支持**：`_type_rich_paragraph()` 支持粗体/斜体/下划线/颜色/标题
- **Markdown 渲染**：`_render_markdown()` 将 Markdown 转为 Word 标题样式
- **图片插入**：`_insert_image()` 支持图片嵌入
- **导出格式**：DOCX 和 PDF 双格式导出

---

## 7. 经验系统集成

经验系统是项目的**自进化核心**，实现了"用得越多，系统越聪明"的设计理念。系统包含两层经验管理器、三种经验类型、以及完整的记忆-回忆-升级生命周期。

### 7.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      经验系统总体架构                              │
│                                                                   │
│  ┌──────────────────────────┐    ┌────────────────────────────┐  │
│  │  通用经验管理器            │    │  Explore 经验管理器          │  │
│  │  src/core/experience.py   │    │  src/core/explore/          │  │
│  │  (~350 行)                │    │  experience.py (~213 行)     │  │
│  │                          │    │                            │  │
│  │  ┌─────────────────────┐ │    │  ┌──────────────────────┐  │  │
│  │  │ 选择器经验            │ │    │  │ Explore 经验          │  │  │
│  │  │ SelectorExperience   │ │    │  │ ExploreExperience     │  │  │
│  │  ├─────────────────────┤ │    │  ├──────────────────────┤  │  │
│  │  │ 脚本记录              │ │    │  │ 自动技能升级          │  │  │
│  │  │ ScriptRecord         │ │    │  │ Skill (auto-gen)      │  │  │
│  │  ├─────────────────────┤ │    │  ├──────────────────────┤  │  │
│  │  │ 站点知识              │ │    │  │ 相似度匹配            │  │  │
│  │  │ SiteKnowledge        │ │    │  │ Jaccard + site + len  │  │  │
│  │  └─────────────────────┘ │    │  └──────────────────────┘  │  │
│  └──────────────────────────┘    └────────────────────────────┘  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  持久化层                                                      ││
│  │  ├── workspace/scripts/        脚本文件 (.py) + index.json     ││
│  │  ├── workspace/selectors/      按站点分文件 (.json)            ││
│  │  ├── workspace/knowledge/      按站点分文件 (.json)            ││
│  │  └── data/explore_experiences/ Explore 经验 (.json)           ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  运行时记忆（内存，不持久化）                                    ││
│  │  ├── _action_history: list[ActionRecord]  最近 10 步操作       ││
│  │  ├── _circuit_breakers: dict[str, int]    动作类型→连续失败    ││
│  │  ├── _last_page_signature: str            页面签名（循环检测）  ││
│  │  └── _consecutive_same_page: int          连续相同页面计数     ││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 三层经验类型详解

#### 7.2.1 选择器经验（SelectorExperience）

**存储位置**：`workspace/selectors/{site}.json`

**数据模型**：
```python
@dataclass
class SelectorExperience:
    selector: str       # CSS 选择器，如 "#search-bar-input"
    site: str           # 站点标识，如 "zhuanlan"
    element: str        # 元素描述
    success_count: int  # 成功次数
    fail_count: int     # 失败次数
    last_success: float # 最后成功时间戳
    last_fail: float    # 最后失败时间戳

    @property
    def reliability(self) -> float:
        """可靠性评分 (0.0 - 1.0)"""
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.5
```

**工作流程**：

```
do_click(page, selector_list)
    │
    ├─ 1. _reorder_by_experience(selector_list, page_url)
    │     从 ExperienceManager 查询该站点+元素的所有选择器经验
    │     按 reliability 降序排列，最可靠的排在最前面
    │
    ├─ 2. 按排列顺序逐一尝试选择器
    │
    ├─ 3a. 成功 → record_selector_success(site, element, selector)
    │       success_count++, last_success = now
    │
    └─ 3b. 失败 → record_selector_failure(site, element, selector)
            fail_count++, last_fail = now
```

**实际存储示例**（`workspace/selectors/zhuanlan.json`）：
```json
{
  "site": "zhuanlan",
  "experiences": [
    {
      "selector": "textarea.Input.i7cW1UcwT6ThdhTakqFm",
      "site": "zhuanlan",
      "success_count": 5,
      "fail_count": 0
    },
    {
      "selector": "button.Button--primary",
      "site": "zhuanlan",
      "success_count": 5,
      "fail_count": 0
    }
  ]
}
```

**核心价值**：同一个页面元素可能有多个可用选择器（ID、class、属性、文本等），通过历史成功率自动选择最稳定的选择器，避免因页面更新导致的 flaky 问题。

#### 7.2.2 Explore 经验（ExploreExperience）

**存储位置**：`data/explore_experiences/{id}.json`

**数据模型**（Pydantic BaseModel）：
```python
class ExploreExperience(BaseModel):
    id: str                          # "explore_{site}_{sha1_hash[:12]}"
    task: str                        # "在虎牙搜索超级小桀"
    site: str                        # "huya"
    url_pattern: str                 # "https://www.huya.com/*"
    actions: list[Action]            # 完整动作序列
    action_count: int                # 动作数量
    element_map: dict[str, ElementInfo]  # ref → 元素信息映射
    snapshot_roles: list[str]        # 快照 ARIA roles（用于相似度匹配）
    snapshot_names: list[str]        # 快照 accessible names
    success_count: int = 1           # 成功次数
    fail_count: int = 0              # 失败次数
    confidence: float = 0.7          # 置信度 (0.1 - 0.95)
    last_used: datetime              # 最后使用时间
    created_at: datetime             # 创建时间
    status: str = "active"           # "active" | "deprecated"
```

**生命周期**：

```
                    ┌─────────────────────────────────────────┐
                    │         Explore 经验生命周期               │
                    └─────────────────────────────────────────┘

    Explore 成功 ──→ save(ExploreExperience)
         │               │
         │               ├─ find_similar(task, site) 检查是否已有相似经验
         │               │    相似度 > 0.8 → update_confidence(success=True)
         │               │    相似度 ≤ 0.8 → 创建新经验条目
         │               │
         │               └─ 持久化到 data/explore_experiences/{id}.json
         │
         ▼
    下次类似任务 ──→ find_experience(task, url)
         │               │
         │               ├─ 提取 site（从 URL hostname）
         │               ├─ 遍历该 site 下所有 active 经验
         │               └─ _calculate_similarity() > 0.8 → 命中
         │
         ▼
    confidence > 0.7 ──→ prepare_experience_actions()
         │               │
         │               ├─ 从经验中提取 action 序列
         │               ├─ 通过 element_map 获取每个 action 的 selector
         │               ├─ 在当前页面快照中查找匹配的元素（by selector/role+name）
         │               └─ remap ref：旧 ref → 当前页面 ref
         │
         ▼
    执行回放 ──→ ACT 状态，执行 remapped actions
         │
         ├─ 成功 → confidence += 0.05（上限 0.95）
         │         success_count++
         │         try_upgrade_to_skill() 检查是否可升级
         │
         └─ 失败 → confidence -= 0.15（下限 0.1）
                   fail_count++
                   confidence < 0.3 → status = "deprecated"
```

**相似度计算**（`_calculate_similarity`）：
```python
def _calculate_similarity(self, task, site, existing) -> float:
    # 字符集 Jaccard 相似度 × 0.4
    task_sim = len(set(task) & set(existing.task)) / len(set(task) | set(existing.task))
    score = task_sim * 0.4
    # 站点匹配 × 0.3
    if site == existing.site:
        score += 0.3
    # 长度差异 × 0.3
    score += (1.0 - abs(len(task) - len(existing.task)) / max(len(task), len(existing.task))) * 0.3
    return score
```

**实际存储示例**（`data/explore_experiences/explore_huya_be69356ac62b.json`）：
```json
{
  "id": "explore_huya_be69356ac62b",
  "task": "在虎牙搜索超级小桀",
  "site": "huya",
  "url_pattern": "https://www.huya.com/*",
  "actions": [
    {"action": "fill", "ref": "e9", "value": "超级小桀", "intent": "在搜索框中输入搜索关键词"},
    {"action": "keyboard", "value": "Enter", "condition": "networkidle", "intent": "提交搜索"},
    {"action": "complete", "value": "已在虎牙搜索超级小桀"}
  ],
  "element_map": {
    "e9": {"selector": "#search-bar-input", "role": "textbox", "name": "主播、频道、游戏", "tag": "input"}
  },
  "success_count": 3,
  "fail_count": 2,
  "confidence": 0.5,
  "status": "active"
}
```

#### 7.2.3 站点知识（SiteKnowledge）

**存储位置**：`workspace/knowledge/{site}.json`

**数据模型**：
```python
@dataclass
class SiteKnowledge:
    site: str                              # 站点标识
    url: str = ""                          # 站点 URL
    selectors: dict[str, list[str]] = {}   # 元素 → 可用选择器列表
    gotchas: list[str] = []                # 踩坑记录（登录模式、验证码等）
    patterns: list[str] = []               # 操作模式（如 "搜索框在右上角"）
    last_updated: float = 0.0              # 最后更新时间
```

**沉淀时机**：
- Explore 模式中 `pause_for_input` 遇到登录/验证码时，自动将面板文本沉淀为 `gotcha`
- 代码路径：`agent.py` → `_maybe_record_site_knowledge(panel_text)` → `ExperienceManager.add_knowledge(site, gotcha=panel_text)`

**注入方式**：站点知识注入 LLM prompt，辅助规划器理解站点特性。

### 7.3 自动技能升级（Experience → Skill）

当 Explore 经验达到升级阈值时，自动生成可复用的 Python 脚本。

**升级条件**：
| 条件 | 阈值 | 配置项 |
|------|------|--------|
| 成功次数 | ≥ 3 | `EXPERIENCE_UPGRADE_THRESHOLD` |
| 置信度 | ≥ 0.8 | `EXPERIENCE_CONFIDENCE_THRESHOLD` |
| 失败率 | ≤ 20% | 硬编码 |

**生成的脚本示例**：
```python
"""自动从 Explore 经验生成: 在虎牙搜索超级小桀"""

from src.layer_1.actions import do_click, do_fill


def run(page, keyword):
    """在虎牙搜索超级小桀"""
    do_click(page, ["#search-bar-input"])
    do_fill(page, ["#search-bar-input"], keyword)
```

**参数提取逻辑**：
- 如果 `fill` 的值出现在任务文本中 → 提取为参数（如 "搜索 **超级小桀**"）
- 如果值是邮箱格式 → 参数名 `username`
- 如果值是手机号格式 → 参数名 `password`（登录场景）或 `input_value`
- 其他 → `input_value`

**Skill 模型**：
```python
class Skill(BaseModel):
    id: str                    # "auto/huya_a1b2c3d4"
    name: str                  # 原始任务描述
    triggers: list[str]        # ["在虎牙搜索超级小桀", "搜索"]
    url_patterns: list[str]    # ["https://www.huya.com/*"]
    source_code: str           # 自动生成的 Python 脚本
    from_explore: bool = True
    auto_generated: bool = True
    confidence: float = 0.9
```

### 7.4 运行时记忆（短期记忆，不持久化）

运行时记忆是 Explore 模式在单次任务执行期间维护的状态，用于循环检测和失败避免。

#### 7.4.1 操作历史（ActionHistory）

```python
# agent.py 中的运行时状态
self._action_history: list[ActionRecord] = []  # 最近 10 步操作记录
self._max_history: int = 10

class ActionRecord(BaseModel):
    action: str          # "click", "fill", "keyboard" 等
    ref: Optional[str]   # 元素 ref
    value: Optional[str] # 填充值或按键
    url: Optional[str]   # 导航 URL
    success: bool        # 是否成功
    error: Optional[str] # 失败原因
    step_number: int     # 所在步骤编号
```

**注入方式**：操作历史格式化后注入 LLM 规划器 prompt：
```
最近操作历史（从旧到新）:
  - fill ref=e9 value=超级小桀 → 成功
  - keyboard value=Enter → 成功
  - click ref=e15 → 失败: Element not found
```

这让 LLM 规划器知道哪些操作已尝试过，避免重复提议相同操作。

#### 7.4.2 循环检测（Loop Detection）

```python
def _compute_page_signature(self, snapshot) -> str:
    """计算页面签名：url + 排序后的交互元素 refs"""
    refs = sorted(n.ref for n in self._iter_snapshot_nodes(snapshot.nodes) if n.ref)
    return f"{snapshot.url}|{','.join(refs)}"

def _check_loop_detection(self, snapshot) -> bool:
    """连续 2 轮相同页面签名 → 判定为循环"""
    sig = self._compute_page_signature(snapshot)
    if sig == self._last_page_signature:
        self._consecutive_same_page += 1
    else:
        self._consecutive_same_page = 0
    self._last_page_signature = sig
    return self._consecutive_same_page >= 2
```

**触发后的处理**：在 LLM prompt 中注入警告：
```
⚠️ 循环检测：当前页面与上一轮完全相同，说明之前的操作没有产生效果。
请换一种策略，不要重复之前的操作。
```

#### 7.4.3 熔断器（Circuit Breaker）

```python
self._circuit_breakers: dict[str, int] = {}  # 动作类型 → 连续失败次数
self._blocker_threshold: int = 3

def _check_circuit_breaker(self, action_type: str, success: bool) -> bool:
    """同一类型动作连续失败 3 次 → 触发熔断"""
    if success:
        self._circuit_breakers.pop(action_type, None)  # 成功重置计数
        return False
    count = self._circuit_breakers.get(action_type, 0) + 1
    self._circuit_breakers[action_type] = count
    return count >= self._blocker_threshold
```

**触发后的处理**：返回 `"stuck"` 状态，通过 `pause_for_input` 询问用户：
- 继续尝试
- 手动操作
- 放弃任务

### 7.5 短期记忆与长期记忆的协作

```
┌─────────────────────────────────────────────────────────────────┐
│                    记忆系统的分层架构                               │
│                                                                   │
│  ┌─ 短期记忆（运行时，单次任务）─────────────────────────────────┐ │
│  │                                                              │ │
│  │  _action_history ──→ 注入 LLM prompt（避免重复操作）         │ │
│  │  _last_page_signature ──→ 循环检测（连续 2 轮相同 → 警告）    │ │
│  │  _circuit_breakers ──→ 熔断器（连续 3 次失败 → 询问用户）    │ │
│  │  _consecutive_empty_snapshots ──→ 空快照计数（→ deep scan）  │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                          │                                        │
│                          │ 任务结束时                              │
│                          ▼                                        │
│  ┌─ 长期记忆（持久化，跨任务）─────────────────────────────────┐ │
│  │                                                              │ │
│  │  SelectorExperience ──→ 按可靠性重排选择器（跨任务共享）      │ │
│  │  ExploreExperience ──→ 经验回放（confidence 衰减机制）       │ │
│  │  SiteKnowledge ──→ 站点特性注入 LLM prompt                   │ │
│  │  ScriptRecord ──→ 成功脚本复用                               │ │
│  │  Skill (auto-gen) ──→ 高置信度经验自动升级为可复用技能        │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                          │                                        │
│                          │ 经验失败时                              │
│                          ▼                                        │
│  ┌─ 记忆衰减 ─────────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  Explore 成功 → confidence += 0.05（上限 0.95）              │ │
│  │  Explore 失败 → confidence -= 0.15（下限 0.1）               │ │
│  │  confidence < 0.3 → status = "deprecated"（自动淘汰）        │ │
│  │  选择器失败 → fail_count++（reliability 下降，排序后移）      │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 7.6 数据流：从探索到记忆

完整的数据流路径（以"在虎牙搜索超级小桀"为例）：

```
用户: "在虎牙搜索超级小桀"
    │
    ▼
AgentLoop._do_plan()
    ├─ SkillRouter: 无匹配（虎牙没有预置 skill）
    ├─ ExploreExperience.find_similar(): 无匹配（首次）
    └─ 进入 EXPLORE 模式
         │
         ▼
    ExploreAgent.run()
         │
         ├─ 1. bootstrap → 导航到 huya.com
         │
         ├─ 2. snapshot() → ARIA 快照（发现搜索框 e9）
         │
         ├─ 3. plan_actions() → LLM 规划:
         │     [fill(e9, "超级小桀"), keyboard(Enter), complete()]
         │
         ├─ 4. execute() → 执行成功
         │     ├─ ActionRecord(fill, e9, 成功) → _action_history
         │     ├─ ActionRecord(keyboard, Enter, 成功) → _action_history
         │     └─ SelectorExperience(#search-bar-input, 成功) → workspace/selectors/
         │
         ├─ 5. save_experience() → 创建 ExploreExperience
         │     └─ data/explore_experiences/explore_huya_{hash}.json
         │
         └─ 返回 "done"
              │
              ▼
         下次用户说 "在虎牙搜索 XXX"
              │
              ├─ find_experience() → 命中 explore_huya_{hash}
              ├─ confidence 0.7 > 0.7 → 准备回放
              ├─ prepare_experience_actions() → remap refs
              └─ ACT 状态 → 直接执行，无需 LLM 规划
```

### 7.7 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `EXPERIENCE_STORAGE_DIR` | `data/explore_experiences` | Explore 经验存储目录 |
| `EXPERIENCE_UPGRADE_THRESHOLD` | 3 | 经验升级为 Skill 的最小成功次数 |
| `EXPERIENCE_CONFIDENCE_THRESHOLD` | 0.8 | 经验升级为 Skill 的最小置信度 |
| `EXPERIENCE_SAVE_THRESHOLD` | 2 | 保存经验的最小动作数 |
| `EXPERIENCE_DEPRECATED_THRESHOLD` | 0.3 | 低于此置信度自动废弃 |

---

## 8. 取消机制

### 8.1 后端实现（`70cc0fc`）

```python
class TaskCancelledError(Exception):
    """用户取消任务时抛出"""

def _raise_if_cancelled():
    """在关键路径检查取消状态"""
    if cancel_requested:
        raise TaskCancelledError()
```

**传播路径：**
```
AgentLoop.run_task()
  → ScriptEngine.execute()     ← cancel_check 注入
  → ExploreAgent.run()         ← cancel_check 注入
    → ExploreExecutor.execute() ← cancel_check 注入
```

### 8.2 前端实现（`c264b92`, `3f50847`, `7cc6738`）

**乐观取消模式：**
1. 用户点击停止按钮
2. **立即**在 UI 显示"任务已取消"消息（不等后端响应）
3. Fire-and-forget POST 到 `/api/cancel` 端点
4. 后端实际取消任务，WebSocket 推送确认

```typescript
// agentStore.ts
cancelCurrentTask: () => {
    // 1. 立即显示取消消息（乐观）
    set(state => ({
        messages: [...state.messages, {
            type: 'system',
            content: '任务已取消',
            created_at: new Date().toISOString()
        }],
        visualState: 'idle'
    }));
    // 2. Fire-and-forget API 调用
    apiRequest(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
}
```

---

## 9. API 连通性测试

### 9.1 功能（PR #90, #91）

在设置页面添加 API 连接测试功能，验证 LLM API 是否可达。

### 9.2 实现

| 层级 | 文件 | 说明 |
|------|------|------|
| 后端 | `src/desktop/task_service.py` | 连通性测试端点 |
| 前端状态 | `src/utils/apiConnectionTestState.ts` | 测试状态管理（reducer 模式） |
| UI | `DashboardPage.tsx` SettingsView | 测试按钮 + 状态指示 |

---

## 10. 其他改进与 Bug 修复

### 10.1 品牌资产

- `cd847e2`：FeatherDesk 品牌资产 — SVG logo、品牌常量、应用 ID
- `1c58dcf`：Windows 应用图标和托盘图标统一

### 10.2 全角标点修复

- `3d16497`：删除 `_FULLWIDTH_MAP` 翻译表，避免中文弯引号 `""` 转成 ASCII `"` 破坏 f-string 语法

### 10.3 命令解析优化

- `b84b0a4`：入口解析成功导航后跳过 SkillRouter（节省 ~38 秒 LLM 调用）
- `2ceaaef`：AI 辅助参数确认

### 10.4 登录流程改进

- `40d14a6`：分阶段认证提示
- `c1b530f`：登录凭据保存确认改为非阻塞模式

### 10.5 知乎自动化增强

- `75b2569`, `ff829af`：知乎操作 URL 从面板获取、选择未按下的赞同按钮
- `b6b1d22`：知乎自动化流程改进
- `3fc3454`：知乎文章和评论流程改进

### 10.6 SPA 页面处理

- `9bb4609`：bootstrap 导航后等待 networkidle，`page.evaluate()` 加 15s 线程级超时
- `ccd4ffb`：回退 snapshot 超时（PR #78），改为循环预防机制

### 10.7 错误状态管理

- `9ae3ef2`：错误状态 10 秒后自动结束，回到 idle

---

## 11. 附录：完整 PR 列表

| PR | 标题 | 关键词 |
|----|------|--------|
| #55 | 删除不重要的tests&完善explore功能 | explore |
| #56 | feat(explore): 原生 aria_snapshot + LoginGuard 多语言 + 搜索引擎拦截 | explore, snapshot |
| #57 | fix: LLM 集成修复 + 三级入口解析 + 性能优化 | routing, mimo |
| #58 | 微信完善 | wechat |
| #59 | feat(explore): 扩展动作类型，统一用户交互 | explore, actions |
| #60 | feat: add AI-assisted parameter confirmation | routing |
| #62 | explore完善 | explore |
| #63 | refactor: split explore mode agent | explore, refactor |
| #64 | 完善微信桌面自动化 | wechat |
| #65 | feat: Explore 模式深度扫描、多步操作、思考模式支持 | explore |
| #66 | 知乎配图支持 | zhihu |
| #67 | fix: 删除 _FULLWIDTH_MAP 避免弯引号转义破坏 f-string 语法 | bugfix |
| #69 | 微信控制窗口大小位置并通过颜色点击关注按钮 | wechat |
| #70 | feat: improve zhihu article and comment flows | zhihu |
| #71 | feat: add desktop pet interaction panel | desktop |
| #72 | 登录逻辑修改 | auth |
| #73 | 新增皮肤背景字体等设置与鼠标调窗口大小，拖动问题已修复 | desktop |
| #74 | 前端小瑕疵和一些运行时bug，以及体验修复 | desktop, bugfix |
| #75 | refactor: 命令解析改为召回+精排架构 | routing, refactor |
| #76 | feat: explore 模式增加失败记忆、循环检测与熔断机制 | explore, robustness |
| #77 | 新增功能微信发送文件和wx cli查看聊天历史记录 | wechat |
| #78 | fix: explore 模式 SPA 等待与 evaluate 超时防护 | explore, bugfix |
| #79 | 删除wx cli并且添加logo | wechat, brand |
| #80 | feat(未测试): 接入通用经验系统 — 选择器经验 + 站点知识 | experience |
| #81 | feat: add guided WPS markdown export formatting | wps |
| #82 | 不阻塞登录信息保存确认 | auth |
| #83 | Implement explicit URL navigation for explore feature | explore |
| #84 | fix: revert snapshot timeout (PR #78) and add explore loop prevention | explore, bugfix |
| #86 | 图标修改 | brand |
| #87 | 错误状态10秒结束 | desktop |
| #88 | feat: support underline and font colors in WPS markdown | wps |
| #90 | Add API connectivity testing features and documentation | api, desktop |
| #91 | feat: 取消机制 + mimo 模型适配 | cancel, mimo |
| #92 | Add API connectivity testing features and documentation | api |
| #93 | feat: add guarded vision fallback to Explore | explore, vision |

---

## 架构演进总结

```
                    7月6日                              7月20日
                ─────────────                      ─────────────

          server.py (MCP tools)              server.py (MCP tools, +路由)
          agent_loop.py (单体)               agent_loop.py (10级路由级联)
                                             ┌─ SkillRouter (召回+精排)
                                             │
                                             ├─ core/explore/ (7个模块, ~3700行)
                                             │   agent/executor/snapshot
                                             │   experience/vision_router
                                             │   ref_generator/models
                                             │
                                             ├─ core/login_guard.py (多语言)
                                             │
                                             ├─ desktop/ (Electron 应用, 全新)
                                             │   agentStore + Pet + Chat
                                             │   Appearance + Dashboard
                                             │
                                             ├─ layer_1/wechat_client.py (+2500行)
                                             │   pywinauto 自动化
                                             │
                                             └─ layer_1/wps_writer.py (+280行)
                                                 COM 自动化 + Markdown
```

**一句话总结**：这 15 天完成了 Explore 模式从原型到生产级的完整演进（含 7 模块、失败记忆、循环熔断、视觉回退），从零构建了 FeatherDesk 桌面客户端（双窗口 + 宠物 + 状态管理），重构了命令路由为召回+精排架构，适配了 MiMo 推理模型，扩展了微信/WPS 自动化能力，并加入了乐观取消和 API 连通性测试等基础设施。
