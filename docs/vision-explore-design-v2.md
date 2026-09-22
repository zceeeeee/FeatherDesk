# Explore 模式视觉模型集成设计 v2.0

> 版本：2.0 | 更新：2026-07-20
> 变更：合入 OpenClaw 视觉架构启发，新增视觉模型复用策略、防注入机制、主模型视觉直通

---

## 一、背景与目标

### 现状

Explore 模式当前完全基于 ARIA 文本树工作：
1. `SnapshotGenerator` 通过 JS 注入提取页面 ARIA 语义树
2. LLM 收到 ARIA JSON，规划动作序列
3. `ExploreExecutor` 用 `data-explore-ref` 属性定位元素执行

**已有的视觉基础设施：**
- `VisionModule`（`src/core/vision.py`）：独立的截图+多模态 LLM 分析模块
- 支持 Anthropic/OpenAI/MiMo/DeepSeek 等视觉模型
- 当前仅在 `_try_heal()` 中作为脚本执行失败的回退

**架构债务：**
- `VisionModule` 和 `LLMClient` 完全独立，代码逻辑重复（各自独立的 HTTP 调用、provider 检测、API key 解析）
- 视觉配置（`config_manager.py` vision 节）和 LLM 配置（`.env` / `LLMConfig`）各自为政
- 主模型如果支持视觉（如 GPT-4o、Claude Sonnet），仍然绕道 VisionModule 再调一次，浪费一次 API 调用

### 问题场景

以下情况 ARIA 快照无法有效工作：
- **Canvas/WebGL 渲染**：游戏、数据可视化、白板工具 → ARIA 无交互元素
- **非常规 UI 框架**：大量 CSS 自定义组件，无标准 ARIA role → deep_scan 也检测不到
- **反检测页面**：需要视觉确认真实渲染状态
- **复杂布局**：ARIA 树丢失空间关系，LLM 难以理解页面结构

### 目标

为 Explore 模式引入视觉能力作为**智能补充**，而非替代 ARIA：
- 当 ARIA 信息不足时，自动触发视觉分析
- 截图 + ARIA 双通道信息融合，提升 LLM 规划质量
- 用坐标操作（`click_at` / `hover_at`）处理视觉发现的非标准元素

### OpenClaw 启发（v2.0 新增）

OpenClaw 的浏览器工具采用**双通道观察**架构：
- `browser snapshot` → UI 结构树 + ref ID（用于交互）
- `browser screenshot` → 页面像素（用于视觉理解）

核心设计理念：
1. **平台级视觉能力**：视觉模型配置复用 `tools.media.image`，浏览器工具是消费者而非独立系统
2. **主模型视觉直通**：主模型支持视觉时，截图直接返回给主模型读取，不走额外视觉模型
3. **自动降级**：主模型无视觉时，自动走视觉模型转文字；都不可用时返回原始图片
4. **防注入保护**：视觉模型返回的文字经过 `wrapExternalContent` 包装，防止 prompt 注入
5. **ref + 坐标并存**：ref 用于结构化交互，`click-coords` 用于坐标点击

---

## 二、整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                       ExploreAgent                            │
│                                                               │
│  snapshot() ──► plan_actions() ──► execute()                  │
│       │              │                  │                      │
│       ▼              ▼                  ▼                      │
│  ARIA 快照     LLM 规划动作      ExploreExecutor               │
│       │              ▲                  │                      │
│       │              │                  │                      │
│       │    ┌─────────┴──────────┐       │                      │
│       │    │  Vision 融合层(新)  │       │                      │
│       │    │                    │       │                      │
│       │    │  ARIA 充足 → 纯文本 │       │                      │
│       │    │  ARIA 不足 → 截图+  │       │                      │
│       │    │    ARIA 融合 prompt │       │                      │
│       │    └────────┬───────────┘       │                      │
│       │             │                   │                      │
│       │    ┌────────▼───────────┐       │                      │
│       │    │  视觉模型路由(新)   │       │                      │
│       │    │                    │       │                      │
│       │    │  主模型有视觉 → 直通│       │                      │
│       │    │  主模型无视觉 →    │       │                      │
│       │    │    VisionModule    │       │                      │
│       │    │  都不可用 → 跳过   │       │                      │
│       │    └────────────────────┘       │                      │
│       │              ▲                  │                      │
│       └──────────────┘                  │                      │
│           LLMClient / VisionModule      │                      │
│           (统一视觉入口)                 │                      │
└──────────────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **ARIA 优先，视觉兜底**：默认用 ARIA，只在信息不足时调用视觉
2. **渐进式升级**：标准快照 → 深度扫描 → 视觉分析，逐级升级
3. **最小侵入**：不改变现有 ARIA 流程，视觉作为附加信息层
4. **成本可控**：视觉调用有额外 token 消耗，通过条件触发避免滥用
5. **主模型优先**（v2.0）：主模型支持视觉时直接用，避免重复调用
6. **防注入保护**（v2.0）：视觉返回内容需经过安全包装

---

## 三、新增原子操作：hover_at

### 3.1 背景

现有 Explore 动作中，坐标类操作只有 `click_at`。但视觉场景中大量元素需要先 hover 才能触发：
- Tooltip 提示框
- 下拉菜单触发器
- 悬浮展开的二级导航
- Canvas 中的热点区域高亮

视觉模型发现这类元素后，无法通过 ref 执行 hover（没有 DOM 节点），也无法通过 `evaluate` 可靠模拟 hover 事件。需要新增 `hover_at` 原子操作。

### 3.2 变更点

**models.py — ActionType 新增枚举值：**
```python
class ActionType(str, Enum):
    # ... 现有 22 种 ...
    HOVER_AT = "hover_at"
```

**executor.py — 新增执行逻辑：**
```python
elif action.action == ActionType.HOVER_AT:
    self._hover_at(action.x or 0, action.y or 0)

def _hover_at(self, x: int, y: int) -> None:
    self._page.mouse.move(x, y)
    self._page.wait_for_timeout(300)  # 等待 hover 效果渲染
```

**agent.py — plan_actions prompt 规则新增：**
```
23. hover_at 需要 x, y 视口坐标（用于无 ref 元素的悬浮操作，
    如触发 tooltip、展开下拉菜单）。hover_at 后可接其他操作等待浮层出现。
24. 对 v 前缀元素（视觉发现），必须使用 click_at 或 hover_at，
    不要使用 click 或 hover（这些元素没有 DOM ref）。
```

### 3.3 坐标操作家族总览

| 动作 | 坐标字段 | 用途 | 状态 |
|------|---------|------|------|
| `click_at` | x, y | 坐标点击 | ✅ 已有 |
| `hover_at` | x, y | 坐标悬浮 | 🆕 本次新增 |
| `double_click_at` | x, y | 坐标双击 | ⏳ 后续扩展 |
| `drag_at` | x, y + value | 坐标拖拽 | ⏳ 后续扩展 |

---

## 四、视觉触发策略

视觉触发采用**三层机制**：启发式数量判断 → 启发式质量判断 → LLM 自评估。前两层在快照阶段自动触发，第三层在规划阶段由模型自主决策。

### 4.1 第一层：启发式-数量触发（快照阶段，自动）

在 `ExploreAgent.snapshot()` 中，ARIA 快照完成后立即判断：

| 条件 | 说明 | 优先级 |
|------|------|--------|
| `interactive_count == 0` | ARIA 完全检测不到交互元素 | 高 |
| `interactive_count < threshold` 且 `deep_scanned == True` | 深度扫描后仍不足 | 高 |
| `_consecutive_empty_snapshots >= 2` | 连续多轮空快照 | 高 |
| Canvas/Video 元素占比高 | 页面可能是 Canvas 渲染 | 中 |

### 4.2 第二层：启发式-质量触发（快照阶段，自动）

ARIA 元素数量充足但质量差时同样触发：

| 条件 | 说明 | 检测方式 |
|------|------|---------|
| **空名称比例过高** | `button ""`, `link ""` 超过 50% 的元素没有有效 accessible name | 遍历快照节点统计 |
| **连续操作失败但元素充足** | 元素数量够但连续 N 次操作失败，说明 ARIA 信息误导了 LLM | `_action_history` 中最近 3 步连续失败 且 `interactive_count >= threshold` |
| **循环检测触发** | 页面签名重复但操作未生效，LLM 基于 ARIA 看不出该怎么换策略 | `_consecutive_same_page >= 2` |

```python
def _check_snapshot_quality(self, snapshot) -> bool:
    """检查 ARIA 快照质量，返回 True 表示质量差需要视觉辅助。"""
    nodes = list(self._iter_snapshot_nodes(snapshot.nodes))
    interactive = [n for n in nodes if n.ref]
    if not interactive:
        return True

    # 空名称比例过高
    empty_name_count = sum(1 for n in interactive if not n.name or n.name.strip() == "")
    if len(interactive) > 0 and empty_name_count / len(interactive) > 0.5:
        logger.warning("快照质量差: %.0f%% 元素无有效名称", empty_name_count / len(interactive) * 100)
        return True

    # 连续操作失败但元素充足
    recent = self._action_history[-3:]
    if len(recent) >= 3 and all(not r.success for r in recent) and len(interactive) >= self._config.min_interactive_threshold:
        logger.warning("快照质量差: 连续 %d 步操作失败但有 %d 个交互元素", len(recent), len(interactive))
        return True

    # 循环检测
    if self._consecutive_same_page >= 2:
        logger.warning("快照质量差: 页面循环 %d 次", self._consecutive_same_page)
        return True

    return False
```

### 4.3 第三层：LLM 自评估触发（规划阶段，模型自主判断）

前两层是系统自动判断，但有些情况只有 LLM 规划时才能感知：
- ARIA 树结构复杂，LLM 不确定该操作哪个元素
- 元素名看起来都对，但 LLM 无法确定哪个是目标任务
- 页面看起来需要视觉确认布局关系

**机制**：在 `ActionBatch` 模型中新增 `need_vision` 字段，LLM 规划时可以主动请求视觉辅助。

```python
class ActionBatch(BaseModel):
    actions: list[Action]
    task_complete: bool = False
    completion_summary: str | None = None
    need_vision: bool = Field(
        False,
        description="LLM 判断当前页面需要视觉辅助才能准确规划"
    )
    vision_reason: str = Field(
        "",
        description="为什么需要视觉辅助（调试用）"
    )
```

**plan_actions 中的处理流程**：

```python
def plan_actions(self, task):
    # 1. 正常规划
    batch = self._call_llm_for_plan(task, snapshot)

    # 2. 如果 LLM 请求视觉辅助，且尚未增强过
    if batch.need_vision and not getattr(snapshot, 'vision_enhanced', False):
        logger.info("LLM 请求视觉辅助: %s", batch.vision_reason)
        enhanced = self._enhance_with_vision(page, snapshot)
        self._last_snapshot = enhanced

        # 3. 用增强后的快照重新规划
        batch = self._call_llm_for_plan(task, enhanced)

    return batch
```

### 4.4 触发优先级与互斥

```
快照阶段:
  第一层(数量) ──触发──► 截图 + 视觉分析 + 融合 ──► 规划
  第二层(质量) ──触发──► 截图 + 视觉分析 + 融合 ──► 规划
  都不触发 ──────────────────────────────────────► 规划

规划阶段:
  LLM 输出 need_vision=true ──► 截图 + 视觉分析 + 融合 ──► 重新规划
  LLM 输出 need_vision=false ──► 正常执行
```

**互斥规则**：
- 快照阶段已触发视觉增强（`vision_enhanced=True`）→ 规划阶段不再触发 LLM 自评估
- LLM 自评估最多触发一次 → 避免循环请求
- 每轮视觉调用总数 ≤ 3 次（`_max_vision_calls_per_page`）

### 4.5 不触发条件（节省成本）

- 视觉能力不可用（主模型无视觉 且 VisionModule 未配置）
- `EXPLORE_VISION_ENABLED=false`

---

## 五、视觉模型路由（v2.0 核心变更）

### 5.1 设计思路

借鉴 OpenClaw 的平台级视觉能力设计，新增统一的视觉调用入口 `ExploreVisionRouter`，根据主模型能力自动选择调用路径：

```
截图 + prompt
    │
    ├─ 主模型支持视觉？ ──是──► 直接用主模型（LLMClient.chat_with_image）
    │                              零额外 API 调用
    │
    └─ 否 ──► VisionModule 可用？ ──是──► VisionModule.analyze_screenshot()
    │                                       额外一次 API 调用
    │
    └─ 否 ──► 跳过视觉增强，回退到纯 ARIA
```

### 5.2 主模型视觉直通

在 `LLMClient` 中新增 `chat_with_image()` 方法：

```python
def chat_with_image(
    self,
    prompt: str,
    screenshot_bytes: bytes,
    *,
    system_prompt: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """带图片的多模态对话。主模型支持视觉时使用。"""
    cfg = self._config
    if cfg.provider == "anthropic":
        return self._call_anthropic_with_image(prompt, screenshot_bytes, system_prompt, temperature, max_tokens)
    return self._call_openai_with_image(prompt, screenshot_bytes, system_prompt, temperature, max_tokens)
```

OpenAI 兼容格式：
```python
{
    "role": "user",
    "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
        {"type": "text", "text": prompt},
    ]
}
```

Anthropic 格式：
```python
{
    "role": "user",
    "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64_image}},
        {"type": "text", "text": prompt},
    ]
}
```

### 5.3 主模型视觉能力检测

```python
# LLMConfig 中新增
@property
def supports_vision(self) -> bool:
    """判断当前模型是否支持视觉输入。"""
    model = self.model.lower()
    vision_keywords = ("gpt-4o", "gpt-4-turbo", "claude-3", "claude-sonnet-4",
                       "claude-opus", "gemini", "mimo-v2", "qwen-vl", "doubao")
    return any(kw in model for kw in vision_keywords)
```

### 5.4 ExploreVisionRouter

新增统一路由类（放在 `src/core/explore/vision_router.py`）：

```python
class ExploreVisionRouter:
    """Explore 模式视觉调用统一路由。"""

    def __init__(self, llm_client: LLMClient | None = None):
        self._llm = llm_client
        self._vision: VisionModule | None = None
        self._vision_call_count: int = 0
        self._max_vision_calls_per_page: int = 3

    def analyze(
        self,
        screenshot_bytes: bytes,
        prompt: str,
    ) -> PageAnalysis | None:
        """根据主模型能力选择视觉调用路径。"""
        # 频率限制
        if self._vision_call_count >= self._max_vision_calls_per_page:
            logger.warning("视觉调用已达上限 (%d)，跳过", self._max_vision_calls_per_page)
            return None

        # 路径 1：主模型支持视觉 → 直通
        if self._llm and self._llm.config.supports_vision:
            try:
                raw = self._llm.chat_with_image(prompt, screenshot_bytes)
                self._vision_call_count += 1
                return self._parse_vision_response(raw)
            except Exception as exc:
                logger.warning("主模型视觉调用失败，降级到 VisionModule: %s", exc)

        # 路径 2：VisionModule
        vision = self._get_vision_module()
        if vision:
            try:
                result = vision.analyze_screenshot(screenshot_bytes, prompt)
                self._vision_call_count += 1
                return result
            except Exception as exc:
                logger.warning("VisionModule 调用失败: %s", exc)

        # 路径 3：都不可用
        logger.info("视觉能力不可用，跳过视觉增强")
        return None

    def reset_page_counter(self) -> None:
        """每轮新快照时重置计数。"""
        self._vision_call_count = 0

    def _get_vision_module(self) -> VisionModule | None:
        if self._vision is None:
            try:
                self._vision = get_vision_module()
            except Exception:
                self._vision = None
        return self._vision
```

### 5.5 调用路径对比

| 路径 | 条件 | 额外 API 调用 | 延迟 | 适用场景 |
|------|------|-------------|------|---------|
| 主模型直通 | 主模型支持视觉 | 0 次（复用当前调用） | 无额外 | GPT-4o / Claude Sonnet 等 |
| VisionModule | 主模型无视觉 + VisionModule 配置 | 1 次 | 2-5 秒 | MiMo / DeepSeek 等纯文本模型 |
| 跳过 | 都不可用 | 0 次 | 0 | 无视觉配置 |

---

## 六、防注入保护（v2.0 新增）

借鉴 OpenClaw 的 `wrapExternalContent` 机制，视觉模型返回的内容需要经过安全处理：

```python
def _sanitize_vision_output(self, text: str) -> str:
    """清理视觉模型返回内容，防止 prompt 注入。

    视觉模型返回的文本可能包含：
    - 恶意指令（如"忽略之前的指令"）
    - HTML/JS 代码
    - 超长文本攻击
    """
    # 1. 截断过长内容
    max_len = 2000
    if len(text) > max_len:
        text = text[:max_len] + "...(截断)"

    # 2. 移除潜在注入模式
    injection_patterns = [
        r"ignore\s+(previous|above|all)\s+(instructions?|prompts?)",
        r"忽略(之前|上面|所有)的(指令|提示)",
        r"system\s*:\s*",
        r"assistant\s*:\s*",
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, "[已过滤]", text, flags=re.IGNORECASE)

    # 3. 包装为可信来源标记
    return f"[视觉模型分析结果]\n{text}\n[/视觉模型分析结果]"
```

---

## 七、视觉分析与快照融合

### 7.1 分析流程

```
视口截图(full_page=False)
  → ExploreVisionRouter.analyze(screenshot_bytes, prompt)
      ├─ 主模型有视觉 → LLMClient.chat_with_image() → 解析
      └─ 主模型无视觉 → VisionModule.analyze_screenshot() → 解析
  → PageAnalysis(elements + visual_hints)
  → 防注入清洗
  → 过滤 confidence < 0.5 的元素
  → 生成 v-ref 合成节点 + 坐标映射
  → 注入 SnapshotResponse
```

### 7.2 视觉 Prompt 设计

针对 Explore 场景的专用 prompt：

```python
def _build_vision_prompt(self, snapshot, task) -> str:
    return f"""分析这张网页截图，补充 ARIA 快照未检测到的可交互元素。

当前任务: {task}
页面 URL: {snapshot.url}
ARIA 检测到的交互元素: {snapshot.interactive_count} 个

请特别关注:
1. ARIA 未检测到的按钮、输入框、链接（特别是自定义 CSS 组件）
2. Canvas/图表中的可点击区域
3. 弹窗、浮层、下拉菜单等可能被遮挡的元素
4. 元素的视觉位置和空间关系

返回 JSON:
{{
  "page_description": "页面整体描述",
  "elements": [
    {{
      "description": "元素描述",
      "role": "button|link|textbox|...",
      "x": 100,
      "y": 200,
      "width": 80,
      "height": 30,
      "suggested_ref_name": "搜索框",
      "confidence": 0.9
    }}
  ],
  "visual_hints": "对规划有帮助的视觉提示（如布局、层级关系）"
}}"""
```

### 7.3 VisionModule 扩展

在 `src/core/vision.py` 中新增 `analyze_screenshot()` 方法：

```python
def analyze_screenshot(
    self,
    screenshot_bytes: bytes,
    prompt: str,
) -> PageAnalysis:
    """分析已有的截图数据（不自行截图）。"""
    b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")
    raw_response = self._call_llm(prompt, b64_image)
    return self._parse_response(raw_response)
```

### 7.4 LLMClient 扩展

在 `src/core/llm_client.py` 中新增多模态调用方法：

```python
def chat_with_image(
    self,
    prompt: str,
    screenshot_bytes: bytes,
    *,
    system_prompt: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """带图片的多模态对话。"""
    self._check_available()
    cfg = self._config
    temp = temperature if temperature is not None else cfg.temperature
    tokens = max_tokens if max_tokens is not None else cfg.max_tokens

    if cfg.provider == "anthropic":
        return self._call_anthropic_with_image(prompt, screenshot_bytes, system_prompt, temp, tokens)
    return self._call_openai_with_image(prompt, screenshot_bytes, system_prompt, temp, tokens)
```

---

## 八、快照融合策略

### 8.1 元素注入

```python
def _merge_vision_into_snapshot(self, snapshot, analysis):
    """将视觉分析结果融合到 ARIA 快照中。"""
    synthetic_nodes = []
    for elem in analysis.elements:
        if elem.confidence < 0.5:
            continue
        ref = f"v{len(synthetic_nodes) + 1}"
        node = AriaNode(
            role=elem.role or "button",
            name=elem.description or elem.suggested_ref_name or "",
            ref=ref,
            tag=None,
            selector=None,
            placeholder=None,
            disabled=False,
            context="[视觉发现]",
            children=[],
        )
        synthetic_nodes.append(node)
        self._vision_element_coords[ref] = (elem.x, elem.y, elem.width, elem.height)

    snapshot.nodes.extend(synthetic_nodes)
    snapshot.interactive_count += len(synthetic_nodes)
    snapshot.vision_enhanced = True
    snapshot.visual_hints = self._sanitize_vision_output(analysis.visual_hints or "")
    return snapshot
```

### 8.2 Ref 命名约定

| 前缀 | 来源 | 定位方式 | 示例 |
|------|------|---------|------|
| `e` | ARIA 快照 | `data-explore-ref` → CSS selector | `e1`, `e12` |
| `v` | 视觉分析 | 坐标映射 → `click_at` / `hover_at` | `v1`, `v3` |

---

## 九、执行器适配

### 9.1 v-ref 坐标操作分发

```python
def _execute_action(self, action, snapshot):
    ref = action.ref

    # 视觉元素 → 坐标操作
    if ref and ref.startswith("v"):
        coords = self._vision_coords.get(ref)
        if not coords:
            raise ExploreError(f"视觉元素 {ref} 坐标未找到", ErrorCode.REF_EXPIRED, ref)
        x, y, w, h = coords
        cx, cy = x + w // 2, y + h // 2

        if action.action in (ActionType.CLICK_AT, ActionType.CLICK):
            self._click_at(cx, cy)
        elif action.action in (ActionType.HOVER_AT, ActionType.HOVER):
            self._hover_at(cx, cy)
        else:
            raise ExploreError(
                f"视觉元素 {ref} 不支持 {action.action} 操作",
                ErrorCode.INVALID_FORMAT, ref
            )
        return

    # 正常 ARIA ref 元素执行（原有逻辑）
    ...
```

### 9.2 自动转换

LLM 对 v-ref 误用 `click`（而非 `click_at`）时，执行器自动转换，不报错。

---

## 十、plan_actions 增强

### 10.1 完整流程

```python
def plan_actions(self, task):
    snapshot = self._last_snapshot

    # 1. 构建基础 prompt（含视觉上下文注入，如有）
    prompt = self._build_prompt_with_vision_context(task, snapshot)

    # 2. 调用 LLM 规划
    data = chat_json_with_retry(self._llm_parser._client, prompt, schema=schema, ...)
    data = self.normalize_action_batch_data(data)
    batch = ActionBatch.model_validate(data)

    # 3. LLM 自评估：请求视觉辅助
    if batch.need_vision and not getattr(snapshot, 'vision_enhanced', False):
        logger.info("LLM 请求视觉辅助: %s", batch.vision_reason)
        page = self._get_browser_manager().get_page()
        enhanced = self._enhance_with_vision(page, snapshot)
        self._last_snapshot = enhanced

        # 用增强后的快照重新规划
        prompt = self._build_prompt_with_vision_context(task, enhanced)
        data = chat_json_with_retry(self._llm_parser._client, prompt, schema=schema, ...)
        data = self.normalize_action_batch_data(data)
        batch = ActionBatch.model_validate(data)

    # 4. 后续正常处理
    for action in batch.actions:
        if action.ref and not action.snapshot_v:
            action.snapshot_v = snapshot.version
    self._last_snapshot = None
    return batch
```

### 10.2 视觉上下文注入

```python
def _build_prompt_with_vision_context(self, task, snapshot):
    prompt = self._build_base_prompt(task, snapshot)

    if getattr(snapshot, 'vision_enhanced', False):
        prompt += (
            "\n\n⚠️ 本快照经过视觉增强。带有 [视觉发现] 标记的元素 "
            "使用 'v' 前缀 ref（如 v1, v2）。\n"
            "对 v 前缀元素：使用 click_at 或 hover_at（需要 x, y 坐标），"
            "不要使用 click 或 hover（无 DOM ref）。\n"
            f"视觉提示: {getattr(snapshot, 'visual_hints', '')}\n"
        )
        for ref, (x, y, w, h) in self._vision_element_coords.items():
            center_x, center_y = x + w // 2, y + h // 2
            prompt += f"  {ref}: 中心坐标 ({center_x}, {center_y})\n"

    return prompt
```

### 10.3 新增规划规则

```
23. hover_at 需要 x, y 视口坐标，用于无 ref 元素的悬浮操作。
24. 对 v 前缀元素（视觉发现），必须使用 click_at 或 hover_at。
25. 如果你无法从 ARIA 快照中确定该操作哪个元素（如元素名全为空、
    看不出页面布局、不确定哪个是目标），设置 need_vision=true，
    并在 vision_reason 中说明原因。系统会自动截图并用视觉模型辅助分析。
    不要在不确定的情况下盲目操作。
```

---

## 十一、模型扩展

### SnapshotResponse

```python
class SnapshotResponse(BaseModel):
    # ... 现有字段 ...
    vision_enhanced: bool = Field(False, description="是否经过视觉增强")
    visual_hints: str = Field("", description="视觉模型提供的提示信息")
```

### ExploreConfig

```python
class ExploreConfig(BaseModel):
    # ... 现有字段 ...
    vision_enabled: bool = Field(True, description="是否启用视觉增强")
    vision_threshold: int = Field(5, description="触发视觉分析的交互元素阈值")
    vision_max_elements: int = Field(20, description="视觉分析最大元素数")
```

### LLMConfig

```python
class LLMConfig(BaseModel):
    # ... 现有字段 ...

    @property
    def supports_vision(self) -> bool:
        """判断当前模型是否支持视觉输入。"""
        model = self.model.lower()
        vision_keywords = ("gpt-4o", "gpt-4-turbo", "claude-3", "claude-sonnet-4",
                           "claude-opus", "gemini", "mimo-v2", "qwen-vl", "doubao")
        return any(kw in model for kw in vision_keywords)
```

---

## 十二、配置项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `EXPLORE_VISION_ENABLED` | `true` | 是否启用视觉增强 |
| `EXPLORE_VISION_THRESHOLD` | `5` | 交互元素低于此值触发 |
| `EXPLORE_VISION_MAX_ELEMENTS` | `20` | 视觉分析最大元素数 |

视觉模型本身复用现有配置体系（`VISION_*` / `OPENAI_*` / `ANTHROPIC_*`），不新增环境变量。

---

## 十三、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/core/explore/models.py` | 修改 | ActionType 新增 `HOVER_AT`；SnapshotResponse 新增视觉字段；ExploreConfig 新增 vision 配置；ActionBatch 新增 `need_vision`/`vision_reason` |
| `src/core/explore/agent.py` | 修改 | 核心：三层触发判断(`_should_use_vision` + `_check_snapshot_quality` + `need_vision`) + 快照增强 + prompt 注入 + 防注入清洗 + LLM 自评估重规划 |
| `src/core/explore/executor.py` | 修改 | 新增 `_hover_at()`；v-ref 坐标分发 + 自动转换 |
| `src/core/explore/vision_router.py` | **新增** | ExploreVisionRouter：主模型直通 / VisionModule / 跳过 三路路由 |
| `src/core/vision.py` | 小改 | 新增 `analyze_screenshot(screenshot_bytes, prompt)` |
| `src/core/llm_client.py` | 修改 | 新增 `chat_with_image()` 多模态调用；新增 `supports_vision` 属性 |
| `.env.example` | 修改 | 新增 `EXPLORE_VISION_*` |
| `tests/test_explore/test_vision.py` | 新增 | 视觉增强测试 |
| `tests/test_explore/test_hover_at.py` | 新增 | hover_at 测试 |
| `tests/test_explore/test_vision_router.py` | 新增 | 路由逻辑测试 |

---

## 十四、数据流

### 正常路径（ARIA 充足，零额外成本）
```
页面 → ARIA 快照(50+ 交互元素)
  → 第一层/第二层: 数量充足 + 质量合格，跳过视觉
  → LLM 规划(纯 ARIA 文本)
  → need_vision=false → 执行(ref 元素)
  → 循环
```

### 路径 A：启发式触发（快照阶段）
```
页面 → ARIA 快照
  → 第一层: interactive_count==0 / 连续空快照 / Canvas
  → 或 第二层: 空名>50% / 连续失败 / 循环检测
  → 触发视觉增强
  → ExploreVisionRouter → 截图 + 分析 → 融合快照
  → LLM 规划(含视觉上下文)
  → 执行(e-ref → DOM / v-ref → 坐标)
  → 循环
```

### 路径 B：LLM 自评估触发（规划阶段）
```
页面 → ARIA 快照(数量充足 + 质量合格)
  → 第一层/第二层: 不触发
  → LLM 规划(纯 ARIA)
  → need_vision=true, vision_reason="元素名都为空，不确定目标"
  → 暂停执行
  → ExploreVisionRouter → 截图 + 分析 → 融合快照
  → LLM 重新规划(含视觉上下文)
  → 执行
  → 循环
```

### 路径 C：主模型视觉直通（零额外 API 调用）
```
触发视觉 → 主模型支持视觉 → 截图随 prompt 一起发送
  → LLM 同时看到 ARIA 树 + 截图 → 直接规划
  → 执行
```

### 深度扫描 + 视觉双重兜底
```
页面 → ARIA 快照(不足)
  → 深度扫描 → 仍不足
  → 视觉分析 → 融合
  → LLM 规划 → 执行
```

---

## 十五、成本控制策略

1. **条件触发**：只在 ARIA 信息不足时调用视觉，正常站点零额外成本
2. **主模型直通**：主模型有视觉时零额外 API 调用（最理想路径）
3. **视口截图**：`full_page=False`，只截当前视口
4. **Token 预算**：视觉分析的 `max_tokens` 限制为 2048
5. **频率限制**：同一页面连续视觉调用 ≤ 3 次
6. **置信度过滤**：`confidence < 0.5` 丢弃
7. **配置开关**：`EXPLORE_VISION_ENABLED=false` 完全关闭

---

## 十六、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 视觉模型返回不准确的坐标 | 点击错位 | 置信度过滤 + 降级 pause_for_input |
| 视觉调用增加延迟 | 每次多 2-5 秒 | 主模型直通零延迟；VisionModule 仅在必要时调用 |
| Token 成本增加 | 每次视觉调用 ~1000-2000 token | 主模型直通复用调用；视口截图 + 元素数量限制 |
| v-ref 坐标在页面变化后失效 | 后续步骤点击失败 | 每轮重新快照，视觉坐标仅当轮有效 |
| 与现有 _try_heal 冲突 | 重复视觉调用 | vision_enhanced 标记，heal 跳过 |
| LLM 对 v-ref 误用 click | ref 查找失败 | 执行器自动转换 v-ref 的 click/hover |
| 视觉模型返回恶意内容 | prompt 注入 | _sanitize_vision_output 清洗 + 包装标记 |
| LLM 滥用 need_vision | 每轮都请求视觉，成本失控 | `vision_enhanced` 标记防止二次触发；每页 ≤ 3 次 |
| 质量检测误判 | 空名比例计算偏差 | 阈值 50% 可配置；结合多种质量信号综合判断 |

---

## 十七、与 v1.0 的差异总结

| 维度 | v1.0 | v2.0 |
|------|------|------|
| 触发机制 | 仅数量不足触发 | 三层：数量 → 质量 → LLM 自评估 |
| 视觉调用 | 始终走 VisionModule | 主模型有视觉时直通，无额外 API 调用 |
| 架构 | ExploreAgent 直接调 VisionModule | 新增 ExploreVisionRouter 统一路由 |
| LLMClient | 纯文本，无视觉支持 | 新增 `chat_with_image()` + `supports_vision` |
| 安全 | 无防注入 | 视觉输出经过 `_sanitize_vision_output` 清洗 |
| 模型自主性 | 纯系统决策 | LLM 可通过 `need_vision` 主动请求视觉 |
| 成本 | 每次视觉增强 1 次额外 API | 主模型直通时 0 次额外 API |
| 配置 | Explore 独立视觉配置 | 复用平台级视觉配置体系 |

---

## 十八、后续扩展（不在本次范围内）

1. **SoM 注解**：截图前注入 CSS 标注交互元素（参考 UI-TARS），提升视觉模型准确度
2. **视觉模型直接规划**：绕过 ARIA，直接用视觉模型输出 ActionBatch
3. **视觉经验持久化**：将视觉发现的元素信息保存到经验库
4. **多图历史**：维护滑动窗口截图历史，支持视觉模型理解操作序列
5. **double_click_at / drag_at**：扩展坐标操作家族
6. **VisionModule 与 LLMClient 统一**：消除代码重复，合并为统一的多模态客户端
