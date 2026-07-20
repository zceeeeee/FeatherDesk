# Explore 模式视觉模型集成设计 v2.1（审查修订版）

> 版本：2.1
> 修订日期：2026-07-20
> 基于：`vision-explore-design-v2.md`
> 状态：建议按阶段实施，Phase 0 和 Phase 1 完成前不启用自动坐标点击

---

## 一、审查结论

v2.0 的总体方向正确：继续以 ARIA/ref 为主通道，在信息不足时引入截图，并为没有 DOM ref 的目标提供坐标操作。但是原方案存在若干会影响正确性、安全性和实施进度的问题，必须先修正。

### 1.1 必须修正的问题（P0）

1. **“主模型视觉直通等于零额外 API 调用”只在融合规划时成立。**
   - 若先调用 `chat_with_image()` 生成 `PageAnalysis`，再调用文本模型规划，仍然是两次 API 调用。
   - 若 LLM 先文本自评估，再请求视觉并重新规划，至少增加一次调用；使用独立视觉模型时通常增加两次。
   - 因此必须区分“主模型融合规划”和“独立视觉分析”两条路径。

2. **视觉能力不能只靠模型名关键词推断。**
   - `"mimo-v2" in model` 会把文本模型 `mimo-v2.5-pro` 错判为视觉模型。
   - OpenAI 兼容服务可使用任意模型别名，单靠名称无法可靠判断能力。
   - 应采用显式配置优先、已知能力表其次、未知模型保守判定为不支持。

3. **视觉坐标缺少跨模块传递契约。**
   - v2.0 将坐标保存在 `ExploreAgent._vision_element_coords`，但执行发生在 `ExploreExecutor`。
   - 当前 `update_snapshot()` 只接收 `SnapshotResponse`，Executor 无法取得 Agent 私有坐标。
   - 坐标目标必须成为快照中的结构化字段，或通过明确的 `update_visual_targets()` 接口传入 Executor。

4. **坐标系没有定义。**
   - 模型返回的是截图像素，而 Playwright 鼠标操作使用 CSS 视口坐标。
   - DPR、浏览器缩放、截图缩放、滚动位置和裁剪都会导致直接点击偏移。
   - 必须保存截图元数据并进行坐标归一化、转换、边界校验和新鲜度校验。

5. **正则删除注入语句不能构成安全边界。**
   - 页面中的恶意文字在视觉模型推理阶段已经可能影响输出，事后替换几个关键词无法撤销影响。
   - 视觉输出必须被视为不可信数据，只能通过严格 schema 进入规划器，且执行器继续做动作白名单、域名限制和敏感动作确认。

6. **触发顺序与“渐进式升级”冲突。**
   - v2.0 一处规定 `interactive_count == 0` 立即视觉，另一处又规定先 deep scan。
   - 修订为统一状态机：标准快照不足时先 deep scan；deep scan 仍不足才触发视觉。仅 Canvas/WebGL 明确信号可跳过 deep scan。

7. **计数器语义冲突。**
   - `_max_vision_calls_per_page` 不能在“每轮新快照”时重置，否则实际上没有每页上限。
   - 应按任务、导航代次和页面签名分别计数，并在真正导航后重置页面计数。

### 1.2 当前代码接口偏差（P1）

- `LLMConfig` 当前是 `dataclass`，不是 Pydantic `BaseModel`。
- `LLMClient` 当前公开 `model`，没有公开 `config`；Router 不应直接访问不存在的 `llm.config`。
- `VisionModule` 当前入口是 `analyze_page()`，没有 `analyze_screenshot()`。
- 当前 `PageAnalysis` 只有 `summary`、`elements`、`suggested_actions` 和 `raw_response`；`ElementInfo` 没有 `role`，也没有 `visual_hints`。
- 当前 Action 校验会在执行前检查 `click_at` 的 `x/y`。若计划支持 `click(ref="v1")` 自动转换，必须在现有校验之前完成规范化。
- 当前 Executor 的 `_valid_refs` 来源于快照节点。v-ref 即使被加入节点，也仍需同步坐标映射，否则只能通过 ref 校验，无法实际定位。

### 1.3 建议补齐的问题（P2）

- 截图隐私策略、敏感页面禁用规则和日志脱敏。
- 截图或页面在分析期间发生导航时的取消机制。
- 视觉输出 JSON 校验、坐标越界、NaN、重复框和置信度校准。
- 视觉调用超时、重试、熔断、缓存和可观测性。
- 灰度开关、回滚策略和量化验收指标。

---

## 二、目标与非目标

### 2.1 目标

1. ARIA/ref 仍是默认、首选且最可靠的交互通道。
2. 标准快照和 deep scan 都不足时，自动使用视觉补充页面理解。
3. 支持 Canvas、自定义绘制控件和 hover 后出现的交互目标。
4. 所有视觉坐标只在生成它的快照版本内有效。
5. 控制视觉调用次数、延迟、token 和隐私风险。
6. 不改变已有 Skill 命中和脚本执行流程，只增强 Explore 路径。

### 2.2 非目标

1. 本期不实现纯视觉端到端 Agent。
2. 本期不让视觉模型直接生成或执行 JavaScript。
3. 本期不保存原始截图到经验库。
4. 本期不实现跨页面复用视觉坐标。
5. 本期不默认允许支付、授权、删除、提交隐私信息等敏感坐标操作。

---

## 三、现状基线

当前 Explore 相关代码主要位于：

- `src/core/explore/models.py`
- `src/core/explore/snapshot.py`
- `src/core/explore/agent.py`
- `src/core/explore/executor.py`
- `src/core/vision.py`
- `src/core/llm_client.py`

已确认的现有能力：

- `ActionType` 已有 `HOVER`、`CLICK_AT`、`REQUEST_DEEP_SCAN` 等动作。
- `SnapshotResponse` 已有 `version`、`url`、`interactive_count` 和 `deep_scanned`。
- `ExploreAgent` 已维护 `_action_history`、`_consecutive_same_page`、`_consecutive_empty_snapshots` 和 `_deep_scan_just_ran`。
- `ExploreExecutor` 已在动作执行前进行参数、快照版本和 ref 校验。
- `VisionModule` 已能截图并调用多模态模型，但目前主要服务于失败恢复。

这意味着视觉增强应复用现有状态，不再建立第二套循环计数和页面生命周期。

---

## 四、修订后的总体架构

```text
ExploreAgent
  |
  +-- 标准 Snapshot
  |     |
  |     +-- 信息充足 ------------------------------+
  |     |                                           |
  |     +-- 信息不足 --> Deep Scan                  |
  |                         |                       |
  |                         +-- 信息充足 -----------+
  |                         |                       |
  |                         +-- 仍不足 --> VisionGate
  |                                           |
  |                                           v
  |                                  ExploreVisionRouter
  |                                  /                 \
  |                         主模型融合规划         独立视觉分析
  |                         (一次带图规划)       (分析后文本规划)
  |                                  \                 /
  +----------------------------------- ActionBatch ---+
                                                 |
                                                 v
                                      ExploreExecutor
                                      e-ref -> DOM/ref
                                      v-ref -> 坐标目标
```

### 4.1 模块职责

| 模块 | 职责 | 不负责 |
|------|------|--------|
| `SnapshotGenerator` | 生成 ARIA 快照和页面表面统计 | 调用模型、判断任务意图 |
| `VisionGate` | 根据状态机和预算判断是否需要视觉 | 分析截图、执行动作 |
| `ExploreVisionRouter` | 能力路由、截图分析、schema 校验 | 直接操作页面 |
| `ExploreAgent` | 组织观察、规划、重规划和上下文 | 自行模拟鼠标 |
| `ExploreExecutor` | 校验并执行 e-ref/v-ref 动作 | 信任模型原始坐标 |

---

## 五、统一视觉状态机

不要在 `snapshot()` 中分散编写多个互相独立的 if。新增明确状态：

```python
class VisionStage(str, Enum):
    ARIA = "aria"
    DEEP_SCAN = "deep_scan"
    VISION = "vision"
    EXHAUSTED = "exhausted"
```

每个页面代次的决策顺序：

```text
ARIA 充足 -> 文本规划
ARIA 不足且未 deep scan -> request_deep_scan
deep scan 充足 -> 文本规划
deep scan 不足且视觉可用且预算允许 -> 视觉规划
视觉失败或预算耗尽 -> pause_for_input / 明确失败
```

### 5.1 可跳过 deep scan 的情况

只有存在强表面信号时才能从 ARIA 直接进入视觉：

- 可见 Canvas/WebGL 占视口面积超过阈值。
- 页面主体是视频流、远程桌面或像素画布。
- deep scan 已在当前 `navigation_epoch` 执行过。

`Canvas/Video 占比` 不能仅从交互节点推断。建议给 `SnapshotResponse` 增加表面统计：

```python
class SurfaceStats(BaseModel):
    canvas_count: int = 0
    video_count: int = 0
    canvas_viewport_ratio: float = 0.0
    visible_dom_element_count: int = 0
```

### 5.2 ARIA 质量评分

不要仅统计 `name` 是否为空。有效标签应按以下顺序计算：

```text
name -> placeholder -> context -> title/aria-description（如快照支持）
```

建议形成 0 到 1 的质量分，而不是多个布尔条件：

```python
quality = (
    0.45 * named_interactive_ratio
    + 0.25 * unique_label_ratio
    + 0.20 * actionable_role_ratio
    + 0.10 * operation_success_ratio
)
```

初始阈值建议为 `0.45`，通过实际数据调整。密码框、分隔线、图标按钮等角色应使用不同权重。

---

## 六、视觉调用路径与真实成本

### 6.1 路径 A：主模型融合规划

当进入规划前已经由启发式确定需要视觉，并且主模型明确支持图片输入时，将 ARIA JSON、截图和 ActionBatch schema 一次发送给主模型，直接返回 `ActionBatch`。

```text
截图 + ARIA + 任务 -> chat_json_with_image() -> ActionBatch
```

相对于普通文本规划：

- API 调用次数不增加。
- 图片 token、上传时间和请求体积仍然增加。
- 不需要先生成 `PageAnalysis` 再规划。

### 6.2 路径 B：独立视觉分析

主模型不支持视觉，但 `VisionModule` 可用时：

```text
截图 -> VisionModule -> ValidatedPageAnalysis
ARIA + ValidatedPageAnalysis -> 文本规划 -> ActionBatch
```

相对于普通文本规划增加一次 API 调用。

### 6.3 路径 C：LLM 自评估后升级

文本规划返回 `need_vision=true` 后重新规划：

- 主模型支持视觉：一次文本规划 + 一次带图规划，共两次调用。
- 需要独立视觉模型：一次文本规划 + 一次视觉分析 + 一次文本重规划，共三次调用。

因此自评估只作为第三层兜底，不应宣传为零额外成本。

### 6.4 路径对比

| 路径 | 总调用数 | 额外调用 | 备注 |
|------|---------:|---------:|------|
| 纯 ARIA 文本规划 | 1 | 0 | 默认路径 |
| 主模型融合规划 | 1 | 0 | 调用数不增，但图片 token 增加 |
| 独立视觉分析后规划 | 2 | 1 | 主模型无视觉时使用 |
| 文本自评估后主模型视觉重规划 | 2 | 1 | 仅不确定时使用 |
| 文本自评估后独立视觉分析 | 3 | 2 | 成本最高，需严格限流 |

---

## 七、模型能力声明

### 7.1 不使用宽泛关键词猜测

新增三态配置：

```text
LLM_SUPPORTS_VISION=auto|true|false
```

判定优先级：

1. 用户显式设置 `true/false`。
2. provider + 完整模型 ID 的保守能力表。
3. 未知模型返回 `False`。

禁止用 `"mimo-v2"`、`"doubao"` 等宽泛子串直接判定。尤其不能把 `mimo-v2.5-pro` 视为视觉模型。

### 7.2 与当前类型保持一致

当前 `LLMConfig` 是 `dataclass`，建议在其中增加字段和方法，不写成 Pydantic 模型：

```python
@dataclass
class LLMConfig:
    # existing fields...
    supports_vision_override: bool | None = None

    def supports_vision(self) -> bool:
        if self.supports_vision_override is not None:
            return self.supports_vision_override
        return lookup_model_capability(self.provider, self.model).vision
```

在 `LLMClient` 上提供稳定接口：

```python
@property
def supports_vision(self) -> bool:
    return self._config.supports_vision()
```

Router 只访问 `llm.supports_vision`，不访问私有配置。

---

## 八、数据模型与坐标契约

### 8.1 新增视觉目标模型

不要把坐标只放在 Agent 私有字典中。将其作为快照的一部分传给 Executor：

```python
class ScreenshotMeta(BaseModel):
    image_width: int
    image_height: int
    viewport_width: int
    viewport_height: int
    scroll_x: float = 0
    scroll_y: float = 0
    device_scale_factor: float = 1.0
    page_url: str
    navigation_epoch: int


class VisualTarget(BaseModel):
    ref: str
    role: str = "generic"
    name: str = ""
    # 统一保存为 0..1 的截图归一化坐标
    x: float
    y: float
    width: float
    height: float
    confidence: float
    snapshot_v: str


class SnapshotResponse(BaseModel):
    # existing fields...
    vision_enhanced: bool = False
    visual_summary: str = ""
    visual_targets: list[VisualTarget] = Field(default_factory=list)
    screenshot_meta: ScreenshotMeta | None = None
```

### 8.2 坐标转换

视觉模型必须返回截图归一化坐标。Executor 转换为 CSS 视口坐标：

```python
css_x = target.x * meta.viewport_width
css_y = target.y * meta.viewport_height
```

执行前必须：

1. 检查 `target.snapshot_v == current_snapshot.version`。
2. 检查 URL、`navigation_epoch`、viewport 和滚动位置未变化。
3. 将坐标限制在视口范围内。
4. 使用 `document.elementFromPoint(css_x, css_y)` 做命中探测。
5. 若页面已变化，返回 `SNAPSHOT_STALE` 并重新观察，不点击。

### 8.3 v-ref 生命周期

- v-ref 使用 `v1`、`v2`，仅在一个快照版本中有效。
- hover、scroll、resize、navigation 和 DOM 大幅变化后必须重新截图。
- 视觉目标不进入长期经验库。
- 经验库只可保存“需要视觉”的站点提示，不保存坐标。

---

## 九、动作模型与 Executor 适配

### 9.1 新增 `hover_at`

```python
class ActionType(str, Enum):
    # existing values...
    HOVER_AT = "hover_at"
```

校验要求：

- `hover_at` 与 `click_at` 一样要求 `x/y`，但不要求 ref。
- `HOVER_AT` 不加入 `_REF_REQUIRED_ACTIONS`。
- 坐标必须是有限数值且位于当前视口内。

### 9.2 推荐的 v-ref 使用方式

LLM 优先输出：

```json
{"action": "click", "ref": "v1", "snapshot_v": "snapshot_v4"}
```

Executor 在**参数和 ref 校验之前**调用 `_normalize_visual_actions()`，把 v-ref 动作解析为内部坐标动作。不要要求 LLM 重复填写 ref 和坐标，以免两者不一致。

```python
def _normalize_visual_actions(self, actions, snapshot):
    targets = {target.ref: target for target in snapshot.visual_targets}
    for action in actions:
        if not action.ref or not action.ref.startswith("v"):
            continue
        target = targets.get(action.ref)
        if target is None:
            raise RefExpiredError(action.ref, snapshot.version)
        if action.action == ActionType.CLICK:
            action.action = ActionType.CLICK_AT
            action.x, action.y = self._target_center(target, snapshot)
            action.ref = None
        elif action.action == ActionType.HOVER:
            action.action = ActionType.HOVER_AT
            action.x, action.y = self._target_center(target, snapshot)
            action.ref = None
        else:
            raise ExploreError("视觉目标暂不支持该动作", ErrorCode.INVALID_FORMAT)
```

首期只允许视觉目标执行 `click` 和 `hover`。视觉发现的输入框不得直接 `fill`，应先坐标点击，再使用 `keyboard/type`，并在每步后重新观察。

---

## 十、视觉输出验证与安全边界

### 10.1 视觉内容一律不可信

页面截图、OCR 文字、视觉模型总结和视觉目标描述全部按外部不可信内容处理。禁止将视觉模型返回的“建议动作”直接交给 Executor。

### 10.2 使用 schema，而不是正则过滤

`_sanitize_vision_output()` 仅保留以下职责：

- 长度限制。
- 控制字符清理。
- 日志转义。
- 明确的外部内容边界标签。

安全控制由以下措施承担：

1. 视觉输出必须通过 Pydantic/JSON Schema 校验。
2. `role` 使用枚举或有限字符串集合。
3. `confidence` 限制为 0..1。
4. 坐标必须为有限数值并处于 0..1。
5. 元素数量不超过配置上限。
6. 视觉模型不能返回 `evaluate`、URL、文件路径或脚本。
7. 最终动作仍由规划器生成并由 Executor 白名单校验。

### 10.3 敏感操作

以下场景默认禁止自动视觉点击，必须回退 ref 或请求用户确认：

- 支付、转账、购买和订阅。
- 删除、发布、发送、提交表单。
- 浏览器权限、系统权限、下载和文件上传。
- 密码、验证码、身份证、银行卡等敏感输入区域。
- 跨域跳转或未知域名。

### 10.4 截图隐私

新增配置：

```text
EXPLORE_VISION_SENSITIVE_POLICY=block|confirm|allow
EXPLORE_VISION_DOMAIN_DENYLIST=
EXPLORE_VISION_MAX_IMAGE_BYTES=4000000
```

默认 `block`。不得在日志中写入 base64、原始截图或完整视觉响应；只记录截图哈希、尺寸、路由、耗时和错误码。

---

## 十一、ExploreVisionRouter

建议接口：

```python
class ExploreVisionRouter:
    def can_use_primary_vision(self) -> bool: ...
    def can_use_fallback_vision(self) -> bool: ...

    def plan_with_primary_vision(
        self,
        *,
        task: str,
        snapshot: SnapshotResponse,
        screenshot: bytes,
        schema: dict,
    ) -> ActionBatch: ...

    def analyze_with_fallback(
        self,
        *,
        task: str,
        snapshot: SnapshotResponse,
        screenshot: bytes,
    ) -> ValidatedPageAnalysis: ...
```

不建议只提供一个返回 `PageAnalysis | None` 的 `analyze()`，因为主模型融合规划和独立视觉分析的返回类型、调用次数及职责不同。

`VisionModule` 新增：

```python
def analyze_screenshot(self, screenshot_bytes: bytes, prompt: str) -> PageAnalysis:
    ...
```

同时扩展 `ElementInfo`：

```python
@dataclass
class ElementInfo:
    description: str = ""
    role: str = "generic"
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    confidence: float = 0.0
```

---

## 十二、预算、缓存和熔断

### 12.1 计数范围

```python
class VisionBudget:
    calls_per_task: int
    calls_per_navigation_epoch: int
    consecutive_failures: int
```

- 每次真正导航时增加 `navigation_epoch` 并重置页面预算。
- 普通 snapshot 不重置预算。
- 默认每个页面代次最多 2 次、每个任务最多 5 次。
- 连续 2 次视觉失败后，本任务熔断视觉能力。

### 12.2 缓存

缓存键建议为：

```text
sha256(screenshot_bytes) + task_class + prompt_version + model_id
```

只缓存结构化分析，不默认落盘原始截图。页面发生滚动或 viewport 改变后缓存失效。

### 12.3 超时与重试

- 截图超时：不重试，回退文本规划。
- 网络超时：最多重试 1 次，使用退避。
- 4xx/schema 错误：不重试。
- 解析错误：允许一次“仅修复 JSON”的低成本重试。
- 页面导航导致执行上下文销毁：丢弃结果，重新 snapshot。

---

## 十三、配置项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `EXPLORE_VISION_ENABLED` | `false` | 灰度阶段默认关闭 |
| `EXPLORE_VISION_MODE` | `auto` | `auto|primary|fallback|off` |
| `LLM_SUPPORTS_VISION` | `auto` | 主模型视觉能力覆盖 |
| `EXPLORE_VISION_QUALITY_THRESHOLD` | `0.45` | ARIA 质量阈值 |
| `EXPLORE_VISION_MAX_ELEMENTS` | `20` | 单次最大视觉目标数 |
| `EXPLORE_VISION_MAX_CALLS_PER_PAGE` | `2` | 每导航代次上限 |
| `EXPLORE_VISION_MAX_CALLS_PER_TASK` | `5` | 每任务上限 |
| `EXPLORE_VISION_TIMEOUT_MS` | `30000` | 单次视觉调用超时 |
| `EXPLORE_VISION_MIN_CONFIDENCE` | `0.65` | 自动交互最低置信度 |
| `EXPLORE_VISION_MAX_IMAGE_BYTES` | `4000000` | 截图大小限制 |
| `EXPLORE_VISION_SENSITIVE_POLICY` | `block` | 敏感页策略 |

初始上线必须默认关闭，经过测试后再改为 `auto`。

---

## 十四、可观测性

每次视觉决策记录结构化事件：

```json
{
  "event": "explore_vision_decision",
  "trigger": "deep_scan_insufficient",
  "route": "primary_fused",
  "snapshot_v": "snapshot_v4",
  "navigation_epoch": 2,
  "aria_quality": 0.31,
  "interactive_count": 2,
  "image_bytes": 382144,
  "latency_ms": 1830,
  "targets_accepted": 4,
  "targets_rejected": 3,
  "outcome": "success"
}
```

禁止记录 API Key、截图 base64、密码字段内容和未截断的页面正文。

核心指标：

- 视觉触发率。
- 视觉后任务成功率增量。
- 错误坐标点击率。
- 平均额外调用次数和延迟。
- schema 拒绝率。
- 敏感操作拦截次数。

---

## 十五、文件变更清单

| 文件 | 变更 |
|------|------|
| `src/core/explore/models.py` | 新增 `HOVER_AT`、视觉阶段、表面统计、截图元数据、视觉目标和配置字段 |
| `src/core/explore/snapshot.py` | 收集 surface stats、viewport、scroll、DPR 和 navigation epoch |
| `src/core/explore/agent.py` | 接入统一状态机、VisionGate、融合规划、自评估重规划和预算 |
| `src/core/explore/executor.py` | 在校验前规范化 v-ref；坐标转换、新鲜度检查和 `hover_at` |
| `src/core/explore/vision_router.py` | 新增两条明确路由：融合规划、独立分析 |
| `src/core/vision.py` | 新增 `analyze_screenshot()`，扩展并验证 ElementInfo |
| `src/core/llm_client.py` | 新增 `chat_json_with_image()` 和显式视觉能力接口 |
| `src/config.py` | 增加视觉开关、预算、隐私和超时配置 |
| `.env.example` | 提供配置示例，默认关闭 |
| `tests/test_explore/test_vision_gate.py` | 状态机和触发测试 |
| `tests/test_explore/test_visual_coordinates.py` | DPR、缩放、滚动、越界和 stale 测试 |
| `tests/test_explore/test_visual_executor.py` | v-ref 规范化和敏感动作阻断测试 |
| `tests/test_explore/test_vision_router.py` | 路由、降级、预算、超时和 schema 测试 |
| `tests/test_explore/test_vision_security.py` | 注入文本、恶意字段、超长输出和隐私测试 |

---

## 十六、分阶段实施

### Phase 0：基础契约

- 新增配置和能力声明。
- 新增 ScreenshotMeta、VisualTarget 和视觉预算。
- 新增结构化日志。
- 不执行视觉坐标动作。

### Phase 1：只读视觉增强

- deep scan 后才允许触发视觉。
- 独立视觉模型只返回页面总结和候选目标。
- 结果只辅助文本规划，不允许 v-ref 点击。
- 验证触发准确率和成本。

### Phase 2：受控坐标交互

- 启用 `hover_at`。
- 仅对非敏感 `click/hover` 开放 v-ref。
- 加入坐标新鲜度、elementFromPoint 探测和用户确认。

### Phase 3：主模型融合规划

- 实现 `chat_json_with_image()`。
- 支持一次调用同时完成视觉理解和 ActionBatch 规划。
- 对比融合路径与独立分析路径的成功率和成本。

### Phase 4：灰度自动化

- 对允许域名和用户显式开关启用 `auto`。
- 指标达标后逐步扩大范围。
- 保留一键回退 `EXPLORE_VISION_ENABLED=false`。

---

## 十七、测试矩阵

### 17.1 单元测试

- ARIA 充足时不触发视觉。
- ARIA 不足时先 deep scan。
- Canvas 强信号可跳过 deep scan。
- 页面快照不会错误重置视觉预算。
- `mimo-v2.5-pro` 不会被误判为视觉模型。
- 视觉 schema 拒绝 NaN、负值、越界框和超量元素。
- v-ref 转换发生在参数/ref 校验之前。
- DPR=1、1.25、1.5、2 下坐标转换正确。
- scroll、resize、navigation 后旧坐标返回 stale。
- 敏感动作不能通过视觉坐标自动执行。

### 17.2 集成测试

- Canvas 按钮。
- hover 后出现菜单。
- 自定义 div 按钮且无 ARIA。
- Shadow DOM 和 iframe 页面。
- 截图期间发生导航。
- 视觉模型超时、4xx、空响应、非法 JSON。
- 主模型无视觉时正确降级 VisionModule。
- 两种视觉能力都不可用时继续纯 ARIA 或请求用户。

### 17.3 端到端验收

建议准备固定测试站点，不直接依赖经常变化的生产网站。

通过标准：

1. 标准网页的视觉触发率低于 5%。
2. Canvas 测试任务成功率较纯 ARIA 提升至少 30 个百分点。
3. 自动坐标误点击率低于 1%。
4. 敏感坐标动作自动执行次数为 0。
5. 单任务视觉调用不超过配置上限。
6. 关闭开关后行为与当前 main 分支一致。

---

## 十八、最终建议

本方案可以实施，但不建议一次完成所有功能。优先建立正确的数据契约、坐标转换、安全边界和可观测性，再开放坐标点击。最重要的实现原则是：

1. **ARIA/ref 永远优先。**
2. **视觉结果是证据，不是指令。**
3. **坐标必须绑定快照版本和页面代次。**
4. **主模型融合规划与独立视觉分析是两条不同路径。**
5. **能力采用显式声明，未知模型保守降级。**
6. **敏感操作不允许纯视觉自动执行。**
7. **先只读增强，再灰度开放坐标操作。**
