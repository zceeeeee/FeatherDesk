# API Connectivity Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a button that tests the currently entered API provider, key, base URL, and model without saving settings or restarting the Agent.

**Architecture:** A focused Electron module constructs and sends minimal provider requests, sanitizes errors, and returns one normalized result. A new IPC bridge exposes that operation to the renderer. The settings page uses a small pure reducer for deterministic loading, success, failure, and stale-result clearing behavior.

**Tech Stack:** Electron IPC, TypeScript, React, Node built-in `fetch`, Node test runner.

## Global Constraints

- Test current form values only; do not persist them and do not restart the Agent.
- Require a non-empty API Key, Base URL, and Model; do not fall back to the encrypted saved API key.
- Never include the API key in logs, status text, or errors returned to the renderer.
- Support `openai` compatible `/chat/completions` and Anthropic `/v1/messages` requests.
- Preserve the existing encrypted settings save behavior.
- Add no runtime or test dependency.

---

### Task 1: Provider Connectivity Module

**Files:**
- Create: `desktop/electron/apiConnectivity.ts`
- Create: `desktop/tests/apiConnectivity.test.ts`
- Modify: `desktop/tsconfig.test.json`

**Interfaces:**
- Produces: `ApiConnectionSettings`, `ApiConnectionTestResult`, `buildApiConnectionRequest(settings)`, and `testApiConnection(settings, dependencies?)`.
- Consumes: Node's built-in `fetch`, `AbortController`, and timers.

- [ ] **Step 1: Write failing request-construction tests**

Add tests that call the wished-for `buildApiConnectionRequest` API and assert exact URLs, auth headers, model names, payload shape, and clamped timeout:

```ts
test("builds a minimal OpenAI-compatible model request", () => {
  const request = buildApiConnectionRequest({
    provider: "openai",
    apiKey: "sk-current",
    baseUrl: "https://example.test/v1/",
    model: "model-a",
    requestTimeout: 60
  });
  assert.equal(request.url, "https://example.test/v1/chat/completions");
  assert.equal(request.init.headers.Authorization, "Bearer sk-current");
  assert.equal(JSON.parse(String(request.init.body)).model, "model-a");
  assert.equal(request.timeoutMs, 60_000);
});

test("builds a minimal Anthropic model request", () => {
  const request = buildApiConnectionRequest({
    provider: "anthropic",
    apiKey: "sk-ant-current",
    baseUrl: "https://api.anthropic.test/",
    model: "claude-test",
    requestTimeout: 30
  });
  assert.equal(request.url, "https://api.anthropic.test/v1/messages");
  assert.equal(request.init.headers["x-api-key"], "sk-ant-current");
  assert.equal(request.init.headers["anthropic-version"], "2023-06-01");
});
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd desktop && npm test`

Expected: compilation fails because `electron/apiConnectivity.ts` does not exist.

- [ ] **Step 3: Implement request construction**

Create typed settings/result interfaces, trim and validate required values, remove trailing slashes from Base URL, clamp timeout to 5-600 seconds, and return provider-specific request data. OpenAI uses bearer auth and Anthropic uses `x-api-key` plus `anthropic-version`.

```ts
export interface ApiConnectionSettings {
  provider: string;
  apiKey: string;
  baseUrl: string;
  model: string;
  requestTimeout: number;
}

export interface ApiConnectionTestResult {
  ok: boolean;
  message: string;
  elapsedMs: number;
}
```

Update `desktop/tsconfig.test.json` to include `electron/apiConnectivity.ts`.

- [ ] **Step 4: Run request tests and verify GREEN**

Run: `cd desktop && npm test`

Expected: both new request-construction tests pass.

- [ ] **Step 5: Write failing execution and error-mapping tests**

Use injected `fetch`, clock, and timer dependencies. Cover successful OpenAI and Anthropic payload validation, 401 authentication failure, 404 endpoint/model failure, timeout, network failure, malformed success payload, and API-key redaction:

```ts
test("reports a usable model after a valid completion response", async () => {
  const result = await testApiConnection(openAiSettings, {
    fetch: async () => new Response(JSON.stringify({ choices: [{ message: { content: "ok" } }] }), { status: 200 }),
    now: (() => { const values = [100, 142]; return () => values.shift()!; })()
  });
  assert.deepEqual(result, {
    ok: true,
    message: "连接成功，模型可用",
    elapsedMs: 42
  });
});

test("does not expose the API key in provider errors", async () => {
  const result = await testApiConnection(openAiSettings, {
    fetch: async () => new Response(JSON.stringify({ error: { message: "bad sk-current" } }), { status: 500 })
  });
  assert.equal(result.ok, false);
  assert.equal(result.message.includes("sk-current"), false);
});
```

- [ ] **Step 6: Run the tests and verify RED**

Run: `cd desktop && npm test`

Expected: tests fail because `testApiConnection` has not been implemented.

- [ ] **Step 7: Implement execution and normalized errors**

Use an `AbortController`, clear its timer in `finally`, parse only JSON, validate `choices` for OpenAI and `content` for Anthropic, and return stable Chinese messages. Replace every occurrence of the current API key in provider messages with `[已隐藏]` and cap provider text at 180 characters.

- [ ] **Step 8: Run Task 1 tests and commit**

Run: `cd desktop && npm test`

Expected: all desktop tests pass.

```powershell
git add desktop/electron/apiConnectivity.ts desktop/tests/apiConnectivity.test.ts desktop/tsconfig.test.json
git commit -m "feat: add API connectivity tester"
```

---

### Task 2: Electron IPC Bridge

**Files:**
- Modify: `desktop/electron/main.ts`
- Modify: `desktop/electron/preload.ts`
- Modify: `desktop/src/types.ts`
- Modify: `desktop/src/services/api.ts`
- Create: `desktop/tests/apiConnectivityBridge.test.ts`
- Modify: `desktop/tsconfig.test.json`

**Interfaces:**
- Consumes: `testApiConnection(settings)` from Task 1.
- Produces: `window.desktopAgent.testApiConnection(settings): Promise<ApiConnectionTestResult>` and `desktopSettings.test(settings)`.

- [ ] **Step 1: Write a failing bridge-contract test**

Create a compile-time/runtime contract test around the service wrapper with a stubbed `window.desktopAgent`:

```ts
test("desktop settings test forwards unsaved form values", async () => {
  let received: DesktopSettings | undefined;
  globalThis.window = {
    desktopAgent: {
      testApiConnection: async (settings: DesktopSettings) => {
        received = settings;
        return { ok: true, message: "连接成功，模型可用", elapsedMs: 12 };
      }
    }
  } as unknown as Window & typeof globalThis;

  const result = await desktopSettings.test(currentSettings);
  assert.equal(received?.apiKey, "unsaved-key");
  assert.equal(result.ok, true);
});
```

Add the new test and any imported renderer service file to `desktop/tsconfig.test.json`.

- [ ] **Step 2: Run the test and verify RED**

Run: `cd desktop && npm test`

Expected: TypeScript fails because `testApiConnection` and `desktopSettings.test` are missing.

- [ ] **Step 3: Add the IPC contract and handler**

- Import `testApiConnection` in `desktop/electron/main.ts`.
- Register `ipcMain.handle("settings:test-connection", (_event, incoming) => testApiConnection(...))`.
- Add `testApiConnection` to preload using `ipcRenderer.invoke("settings:test-connection", settings)`.
- Add shared renderer-side input/result types and the method to `DesktopBridge`.
- Add `desktopSettings.test` in `desktop/src/services/api.ts`.

The handler passes only current IPC input and does not read `settings.json`, call `safeStorage`, write a file, or invoke `restartBackend`.

- [ ] **Step 4: Run bridge tests and verify GREEN**

Run: `cd desktop && npm test`

Expected: all desktop tests pass and the test confirms the unsaved key is forwarded.

- [ ] **Step 5: Commit the bridge**

```powershell
git add desktop/electron/main.ts desktop/electron/preload.ts desktop/src/types.ts desktop/src/services/api.ts desktop/tests/apiConnectivityBridge.test.ts desktop/tsconfig.test.json
git commit -m "feat: expose API connectivity test to settings"
```

---

### Task 3: Settings Page Interaction

**Files:**
- Create: `desktop/src/utils/apiConnectionTestState.ts`
- Create: `desktop/tests/apiConnectionTestState.test.ts`
- Modify: `desktop/tsconfig.test.json`
- Modify: `desktop/src/pages/DashboardPage.tsx`
- Modify: `desktop/src/styles.css`

**Interfaces:**
- Consumes: `desktopSettings.test(settings)` and `ApiConnectionTestResult` from Task 2.
- Produces: `apiConnectionTestReducer(state, action)` and the settings-page test button/status UI.

- [ ] **Step 1: Write failing state tests**

Cover all user-visible transitions:

```ts
test("connection state transitions through testing and success", () => {
  const testing = apiConnectionTestReducer(initialApiConnectionTestState, { type: "start" });
  assert.equal(testing.status, "testing");
  const success = apiConnectionTestReducer(testing, {
    type: "succeed",
    message: "连接成功，模型可用",
    elapsedMs: 25
  });
  assert.deepEqual(success, {
    status: "success",
    message: "连接成功，模型可用",
    elapsedMs: 25
  });
});

test("editing API settings clears a stale result", () => {
  const cleared = apiConnectionTestReducer(
    { status: "success", message: "连接成功，模型可用", elapsedMs: 25 },
    { type: "edit" }
  );
  assert.deepEqual(cleared, initialApiConnectionTestState);
});
```

Also cover failure and ensure `edit` does not change an active `testing` state.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd desktop && npm test`

Expected: compilation fails because the reducer module does not exist.

- [ ] **Step 3: Implement the minimal reducer**

Create an exhaustive discriminated-union reducer with `idle`, `testing`, `success`, and `error` states. Return the initial state on `edit` unless a request is active.

- [ ] **Step 4: Run state tests and verify GREEN**

Run: `cd desktop && npm test`

Expected: all reducer tests pass.

- [ ] **Step 5: Add the test button and status feedback**

In `SettingsView`:

- Use `useReducer(apiConnectionTestReducer, initialApiConnectionTestState)`.
- Route Provider, API Key, Base URL, Model, and timeout edits through a helper that dispatches `edit` before updating settings.
- Validate current API Key, Base URL, and Model before invoking the bridge.
- Dispatch `start`, call `desktopSettings.test(settings)`, then dispatch `succeed` or `fail` using the normalized result.
- Catch IPC errors and show `连通测试失败，请重试` without including credentials.
- Render a secondary button with a `PlugZap` icon beside Save; show a spinner and `测试中` while active.
- Render one accessible status line beneath the action row. Success includes `（{elapsedMs} ms）`; failure uses the error style.
- Keep the browser settings page limited to the existing Save button.

Add stable layout classes for the two-button row and status text without changing unrelated page styling.

- [ ] **Step 6: Run desktop tests, type checking, and build**

Run:

```powershell
cd desktop
npm test
npm run typecheck
npm run build
```

Expected: every command exits with code 0.

- [ ] **Step 7: Commit the settings UI**

```powershell
git add desktop/src/utils/apiConnectionTestState.ts desktop/tests/apiConnectionTestState.test.ts desktop/tsconfig.test.json desktop/src/pages/DashboardPage.tsx desktop/src/styles.css
git commit -m "feat: add API connection test control"
```

---

### Task 4: Final Verification

**Files:**
- Verify only; modify files only if a failing check exposes a defect in the feature.

**Interfaces:**
- Consumes: completed Tasks 1-3.
- Produces: fresh verification evidence for delivery.

- [ ] **Step 1: Check requirement coverage and diff hygiene**

Run:

```powershell
git diff HEAD~3 --check
git status --short
```

Confirm the test path never writes settings, never reads the saved key, never restarts the backend, and never emits credentials.

- [ ] **Step 2: Run the full desktop verification suite**

Run:

```powershell
cd desktop
npm test
npm run typecheck
npm run build
```

Expected: every command exits with code 0 and all tests pass.

- [ ] **Step 3: Review the final commits**

Run: `git log -4 --oneline`

Expected: the design, connectivity module, bridge, and settings UI commits are present with no unrelated changes.
