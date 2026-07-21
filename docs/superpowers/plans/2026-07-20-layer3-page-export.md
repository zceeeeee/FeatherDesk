# Layer 3 Page Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Layer 3 page-export atomic operation that keeps visible text, table data, and links in the current task's in-memory `export_result` for later operations.

**Architecture:** `src/layer_3/exporter.py` owns DOM extraction and returns a serializable `ExportResult`. `TaskContext` owns the latest result for one task. The script engine exposes `export_page()` and `get_export_result()`, while Explore exposes an `export` action and adds a bounded result summary to the next planner prompt.

**Tech Stack:** Python, Pydantic v2, synchronous Playwright `Page`, existing Explore action models/executor, pytest.

## Global Constraints

- Extract only visible page text, visible tables, and visible links.
- Exclude scripts, styles, hidden nodes, SVG/canvas/video/image nodes, and image URLs.
- Keep the result in memory under `export_result`; never write a temporary file.
- Do not add a skill registry entry or a user-facing export message.
- Use the existing Playwright `Page` interface so Chromium and CloakBrowser share the implementation.
- Keep the future Taobao product images and price statistics out of this change.

---

### Task 1: Layer 3 Exporter and Data Contract

**Files:**
- Create: `src/layer_3/exporter.py`
- Create: `tests/test_exporter.py`

**Interfaces:**
- Produces: `ExportTable`, `ExportLink`, `ExportResult`, `export_page(page, limits=None)`, and `normalize_export_payload(payload, limits=None)`.
- Consumes: a synchronous Playwright `Page` with `url`, `title()`, and `evaluate()`.

- [ ] **Step 1: Write failing data-contract and normalization tests**

Add tests for whitespace normalization, image/script filtering in the normalized payload, tables, links, and deterministic limits:

```python
def test_normalize_export_payload_keeps_text_tables_and_links_but_drops_images():
    result = normalize_export_payload({
        "url": " https://example.test/page ",
        "title": " Example ",
        "text": "  Product   list\\n  Visible text  ",
        "tables": [{
            "headers": [" Product ", " Price "],
            "rows": [[" Item A ", " 19.90 "]],
            "images": ["https://cdn.example.test/a.jpg"],
        }],
        "links": [
            {"text": " Item A ", "href": " /item-a "},
            {"text": " image ", "href": "https://cdn.example.test/a.jpg"},
        ],
        "images": ["https://cdn.example.test/a.jpg"],
    })

    assert result.model_dump() == {
        "url": "https://example.test/page",
        "title": "Example",
        "text": "Product list Visible text",
        "tables": [{"headers": ["Product", "Price"], "rows": [["Item A", "19.90"]]}],
        "links": [{"text": "Item A", "href": "/item-a"}],
    }

def test_normalize_export_payload_applies_text_and_collection_limits():
    result = normalize_export_payload(
        {"text": "abcdefgh", "tables": [{"headers": [], "rows": [["1"], ["2"]]}] * 3,
         "links": [{"text": str(i), "href": f"/item-{i}"} for i in range(3)]},
        limits={"max_text_chars": 5, "max_tables": 2, "max_rows": 1, "max_links": 2},
    )

    assert result.text == "abcde"
    assert len(result.tables) == 2
    assert len(result.tables[0].rows) == 1
    assert len(result.links) == 2
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/test_exporter.py -q`

Expected: collection fails because `src.layer_3.exporter` does not exist.

- [ ] **Step 3: Implement the serializable models and normalizer**

Create Pydantic models with only these fields:

```python
class ExportTable(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)

class ExportLink(BaseModel):
    text: str
    href: str

class ExportResult(BaseModel):
    url: str = ""
    title: str = ""
    text: str = ""
    tables: list[ExportTable] = Field(default_factory=list)
    links: list[ExportLink] = Field(default_factory=list)
```

Normalize all scalar strings by collapsing whitespace and trimming. Drop unknown fields, including any `images` field. Apply limits after normalization. Do not turn a missing table or link list into an error.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `pytest tests/test_exporter.py -q`

Expected: the data-contract and limit tests pass.

- [ ] **Step 5: Write failing page-evaluation tests**

Use a fake page to verify `export_page()` requests one DOM evaluation and combines the page URL/title with the page-evaluation payload:

```python
class FakePage:
    url = "https://example.test/catalog"

    def title(self):
        return "Catalog"

    def evaluate(self, script, *args):
        assert "visibility" in script
        assert "TABLE" in script
        assert "IMG" in script
        return {"text": "Visible catalog", "tables": [], "links": []}

def test_export_page_uses_playwright_page_and_returns_result():
    result = export_page(FakePage())
    assert result.url == "https://example.test/catalog"
    assert result.title == "Catalog"
    assert result.text == "Visible catalog"
```

Also test that a closed/missing page raises `ExportError` with a stable message and that evaluation errors are wrapped without returning an empty success result.

- [ ] **Step 6: Run the new tests and verify RED**

Run: `pytest tests/test_exporter.py -q`

Expected: page-export tests fail because `export_page()` and `ExportError` do not exist.

- [ ] **Step 7: Implement visible DOM extraction**

Implement one `page.evaluate()` script that:

- walks `document.body` and skips `SCRIPT`, `STYLE`, `NOSCRIPT`, `TEMPLATE`, `SVG`, `CANVAS`, `VIDEO`, and `IMG` nodes;
- skips nodes whose computed style is `display:none`, `visibility:hidden`, `content-visibility:hidden`, or whose rendered rectangle has no size;
- collects visible text with normalized whitespace;
- collects visible `TABLE` elements, using visible `thead` cells as headers and visible body rows as rows;
- collects visible anchors with non-empty text and `href`, excluding image-only anchors;
- returns only `text`, `tables`, and `links`.

Wrap missing/closed pages and `evaluate()` exceptions in `ExportError`. Combine `page.url` and `page.title()` with the normalized payload and return `ExportResult`.

- [ ] **Step 8: Run Task 1 tests and commit**

Run: `pytest tests/test_exporter.py -q`

Expected: all exporter tests pass.

```powershell
git add src/layer_3/exporter.py tests/test_exporter.py
git commit -m "feat: add layer3 page exporter"
```

---

### Task 2: In-Memory Task Context and Script Entry Points

**Files:**
- Create: `src/core/task_context.py`
- Modify: `src/core/script_engine.py`
- Modify: `src/core/agent_loop.py`
- Create: `tests/test_task_context.py`
- Modify: `tests/test_script_engine.py`

**Interfaces:**
- Consumes: `ExportResult` and `export_page()` from Task 1.
- Produces: `TaskContext`, `ScriptEngine.set_task_context(context)`, `export_page()`, and `get_export_result()` in the restricted script namespace.

- [ ] **Step 1: Write failing context lifecycle tests**

Test replacing the latest successful result, preserving it after a failed export, and clearing it between tasks:

```python
def test_task_context_stores_latest_successful_export_only():
    context = TaskContext()
    first = {"url": "https://a.test", "title": "A", "text": "A", "tables": [], "links": []}
    second = {"url": "https://b.test", "title": "B", "text": "B", "tables": [], "links": []}
    context.set_export_result(first)
    context.set_export_result(second)
    assert context.get_export_result() == second

def test_task_context_reset_drops_previous_export():
    context = TaskContext()
    context.set_export_result({"url": "https://a.test", "title": "A", "text": "A", "tables": [], "links": []})
    context.reset()
    assert context.get_export_result() is None
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/test_task_context.py -q`

Expected: collection fails because `src.core.task_context` does not exist.

- [ ] **Step 3: Implement the task context**

Implement a small dataclass:

```python
@dataclass
class TaskContext:
    export_result: dict[str, Any] | None = None

    def set_export_result(self, result: dict[str, Any]) -> None: ...
    def get_export_result(self) -> dict[str, Any] | None: ...
    def reset(self) -> None: ...
```

Store a defensive copy so later script mutation cannot corrupt the context unexpectedly.

- [ ] **Step 4: Run the context tests and verify GREEN**

Run: `pytest tests/test_task_context.py -q`

Expected: both context tests pass.

- [ ] **Step 5: Write failing script namespace tests**

Add tests with a fake page/browser manager showing that `export_page()` returns a dictionary, writes `export_result`, and `get_export_result()` returns the same task-local value. Verify a new context is empty.

- [ ] **Step 6: Run the tests and verify RED**

Run: `pytest tests/test_script_engine.py -q -k "export_page or export_result"`

Expected: the new tests fail because the script engine has no task-context binding or export functions.

- [ ] **Step 7: Implement script integration and task lifecycle**

- Add `ScriptEngine.set_task_context(context: TaskContext | None)`.
- Inject `export_page()` that calls Layer 3 with the current page, serializes `ExportResult.model_dump()`, stores it in the bound context, and returns the dictionary.
- Inject `get_export_result()` that returns a defensive copy or `None`.
- In `AgentLoop._run_single`, create a fresh `TaskContext`, bind it to the script engine and Explore agent before the state loop, and clear the bindings in `finally` after the task finishes.
- Do not use a global result across top-level tasks.

- [ ] **Step 8: Run script and context tests and commit**

Run: `pytest tests/test_task_context.py tests/test_script_engine.py -q`

Expected: all selected tests pass.

```powershell
git add src/core/task_context.py src/core/script_engine.py src/core/agent_loop.py tests/test_task_context.py tests/test_script_engine.py
git commit -m "feat: pass page exports through task context"
```

---

### Task 3: Explore Export Atomic Action

**Files:**
- Modify: `src/core/explore/models.py`
- Modify: `src/core/explore/executor.py`
- Modify: `src/core/explore/agent.py`
- Modify: `src/core/agent_loop.py`
- Create: `tests/test_explore_export.py`

**Interfaces:**
- Consumes: `TaskContext` from Task 2 and `export_page()` from Task 1.
- Produces: `ActionType.EXPORT`, executor `ActionResult` JSON value, and bounded export summary in the next Explore planner prompt.

- [ ] **Step 1: Write failing model/executor tests**

Test that `Action(action="export")` validates without a ref, invokes the exporter, returns serialized data, and stores it in the bound context:

```python
def test_export_action_returns_serialized_result_and_updates_context():
    context = TaskContext()
    executor = make_executor(task_context=context, exported={
        "url": "https://example.test", "title": "Catalog",
        "text": "Visible catalog", "tables": [], "links": []
    })
    result = executor.execute({"actions": [{"action": "export"}]})
    assert result.success is True
    assert json.loads(result.results[0].value)["text"] == "Visible catalog"
    assert context.get_export_result()["title"] == "Catalog"
```

Add a failure test proving a failed export returns `success=False` and leaves an earlier context result unchanged.

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/test_explore_export.py -q`

Expected: validation or execution fails because `ActionType.EXPORT` and its executor branch do not exist.

- [ ] **Step 3: Add the action type and executor branch**

- Add `EXPORT = "export"` to `ActionType`.
- Exclude export from login-guarded ref actions.
- In `_execute_single`, call `export_page(self._page)`, update the bound context only after success, and return `ActionResult(action=EXPORT, success=True, value=json.dumps(result.model_dump(), ensure_ascii=False))`.
- Convert `ExportError` to `ActionResult(success=False, error=...)` through the existing exception path.
- Do not require `ref`, `value`, URL, or file path for this action.

- [ ] **Step 4: Run model/executor tests and verify GREEN**

Run: `pytest tests/test_explore_export.py -q`

Expected: export action tests pass.

- [ ] **Step 5: Write failing planner-context tests**

Test that after an export result is stored, the next `ExploreAgent.plan_actions()` prompt includes bounded URL/title/text/table information, never image fields, and is empty after task reset.

- [ ] **Step 6: Run the planner tests and verify RED**

Run: `pytest tests/test_explore_export.py -q -k "summary or prompt"`

Expected: tests fail because Explore has no task-context binding or export summary.

- [ ] **Step 7: Implement Explore task-context binding and summary**

- Add `ExploreAgent.set_task_context(context: TaskContext | None)` and pass it into newly created `ExploreExecutor` instances.
- Rely on the executor's successful-export context update; the agent must not parse or rewrite the result. Verify that the bound context remains available for the planner after execution and is cleared by `reset_task_state()`.
- Add a bounded `export_result` section to the planning prompt containing URL, title, text, table headers/rows, and link text/addresses up to the configured prompt limit.
- Clear the binding and transient export summary when `reset_task_state()` runs.
- Keep `ActionRecord` values bounded; do not put full page text into long-term experience records.

- [ ] **Step 8: Run Explore tests and commit**

Run: `pytest tests/test_explore_export.py tests/test_agent_loop.py -q`

Expected: selected Explore and agent-loop tests pass.

```powershell
git add src/core/explore/models.py src/core/explore/executor.py src/core/explore/agent.py src/core/agent_loop.py tests/test_explore_export.py
git commit -m "feat: add explore page export action"
```

---

### Task 4: Full Verification and Scope Check

**Files:**
- Verify only; modify files only if a check exposes a defect in this feature.

**Interfaces:**
- Consumes: completed Tasks 1-3.
- Produces: fresh test evidence and a clean scope report.

- [ ] **Step 1: Run focused Python tests**

Run:

```powershell
pytest tests/test_exporter.py tests/test_task_context.py tests/test_script_engine.py tests/test_explore_export.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the full Python suite**

Run: `pytest -q`

Expected: no new failures from export changes. Existing unrelated failures must be reported separately rather than hidden.

- [ ] **Step 3: Run desktop checks if shared files changed**

Run:

```powershell
cd desktop
npm test
npm run typecheck
npm run build
```

Expected: every command exits with code 0.

- [ ] **Step 4: Check diff and future-scope boundaries**

Run:

```powershell
cd ..
git diff --check
git status --short
rg -n "export_page|ActionType\.EXPORT|export_result" src/layer_3 src/core/explore src/core/script_engine.py
```

Review only the changed files and confirm the change contains no product-image rendering, price statistics, chart generation, skill registry entry, or temporary-file export. Existing unrelated Taobao/search code is outside this feature's scope.
