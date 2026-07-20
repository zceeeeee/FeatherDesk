import assert from "node:assert/strict";
import test from "node:test";
import {
  buildApiConnectionRequest,
  testApiConnection,
  type ApiConnectionSettings
} from "../electron/apiConnectivity.js";

const openAiSettings: ApiConnectionSettings = {
  provider: "openai",
  apiKey: "sk-current",
  baseUrl: "https://example.test/v1",
  model: "model-a",
  requestTimeout: 60
};

test("builds a minimal OpenAI-compatible model request", () => {
  const request = buildApiConnectionRequest({
    provider: "openai",
    apiKey: "sk-current",
    baseUrl: "https://example.test/v1/",
    model: "model-a",
    requestTimeout: 60
  });

  assert.equal(request.url, "https://example.test/v1/chat/completions");
  assert.equal(request.init.method, "POST");
  assert.equal(request.init.headers.Authorization, "Bearer sk-current");
  assert.equal(request.init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(request.init.body), {
    model: "model-a",
    temperature: 0,
    max_tokens: 1,
    messages: [{ role: "user", content: "Reply with OK." }]
  });
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
  assert.equal(request.init.method, "POST");
  assert.equal(request.init.headers["x-api-key"], "sk-ant-current");
  assert.equal(request.init.headers["anthropic-version"], "2023-06-01");
  assert.deepEqual(JSON.parse(request.init.body), {
    model: "claude-test",
    temperature: 0,
    max_tokens: 1,
    messages: [{ role: "user", content: "Reply with OK." }]
  });
  assert.equal(request.timeoutMs, 30_000);
});

test("trims required values and clamps timeout to the settings range", () => {
  const request = buildApiConnectionRequest({
    provider: "openai",
    apiKey: "  sk-current  ",
    baseUrl: "  https://example.test/v1///  ",
    model: "  model-a  ",
    requestTimeout: 1
  });

  assert.equal(request.url, "https://example.test/v1/chat/completions");
  assert.equal(request.init.headers.Authorization, "Bearer sk-current");
  assert.equal(JSON.parse(request.init.body).model, "model-a");
  assert.equal(request.timeoutMs, 5_000);
});

test("requires the current API key, base URL, and model", () => {
  const base = {
    provider: "openai",
    apiKey: "sk-current",
    baseUrl: "https://example.test/v1",
    model: "model-a",
    requestTimeout: 60
  };

  assert.throws(
    () => buildApiConnectionRequest({ ...base, apiKey: "" }),
    /API Key/
  );
  assert.throws(
    () => buildApiConnectionRequest({ ...base, baseUrl: "" }),
    /Base URL/
  );
  assert.throws(
    () => buildApiConnectionRequest({ ...base, model: "" }),
    /Model/
  );
});

test("reports a usable OpenAI-compatible model after a valid response", async () => {
  const times = [100, 142];
  const result = await testApiConnection(openAiSettings, {
    fetch: async () => new Response(
      JSON.stringify({ choices: [{ message: { content: "OK" } }] }),
      { status: 200 }
    ),
    now: () => times.shift()!
  });

  assert.deepEqual(result, {
    ok: true,
    message: "连接成功，模型可用",
    elapsedMs: 42
  });
});

test("reports a usable Anthropic model after a valid response", async () => {
  const result = await testApiConnection(
    { ...openAiSettings, provider: "anthropic" },
    {
      fetch: async () => new Response(
        JSON.stringify({ content: [{ type: "text", text: "OK" }] }),
        { status: 200 }
      )
    }
  );

  assert.equal(result.ok, true);
  assert.equal(result.message, "连接成功，模型可用");
});

test("maps authentication and missing model responses", async () => {
  const unauthorized = await testApiConnection(openAiSettings, {
    fetch: async () => new Response("{}", { status: 401 })
  });
  const missing = await testApiConnection(openAiSettings, {
    fetch: async () => new Response("{}", { status: 404 })
  });

  assert.equal(unauthorized.message, "API Key 认证失败");
  assert.equal(missing.message, "接口地址或模型不存在");
});

test("maps timeout, network, and malformed provider responses", async () => {
  const timedOut = await testApiConnection(openAiSettings, {
    fetch: async () => { throw new DOMException("aborted", "AbortError"); }
  });
  const unreachable = await testApiConnection(openAiSettings, {
    fetch: async () => { throw new TypeError("fetch failed"); }
  });
  const malformed = await testApiConnection(openAiSettings, {
    fetch: async () => new Response(JSON.stringify({ result: "OK" }), { status: 200 })
  });

  assert.equal(timedOut.message, "请求超时");
  assert.equal(unreachable.message, "无法连接 API 地址");
  assert.equal(malformed.message, "模型响应格式无效");
});

test("does not expose the API key in provider errors", async () => {
  const result = await testApiConnection(openAiSettings, {
    fetch: async () => new Response(
      JSON.stringify({ error: { message: "bad credential sk-current" } }),
      { status: 500 }
    )
  });

  assert.equal(result.ok, false);
  assert.equal(result.message.includes("sk-current"), false);
  assert.match(result.message, /\[已隐藏\]/);
});
