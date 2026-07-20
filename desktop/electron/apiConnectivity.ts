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

export interface BuiltApiConnectionRequest {
  url: string;
  init: {
    method: "POST";
    headers: Record<string, string>;
    body: string;
  };
  timeoutMs: number;
}

export interface ApiConnectionDependencies {
  fetch?: typeof fetch;
  now?: () => number;
  setTimeout?: typeof setTimeout;
  clearTimeout?: typeof clearTimeout;
}

function required(value: string, label: string): string {
  const normalized = String(value || "").trim();
  if (!normalized) throw new Error(`${label} 不能为空`);
  return normalized;
}

export function buildApiConnectionRequest(
  settings: ApiConnectionSettings
): BuiltApiConnectionRequest {
  const provider = String(settings.provider || "openai").trim().toLowerCase();
  const apiKey = required(settings.apiKey, "API Key");
  const baseUrl = required(settings.baseUrl, "Base URL").replace(/\/+$/, "");
  const model = required(settings.model, "Model");
  const timeoutSeconds = Math.min(
    600,
    Math.max(5, Number(settings.requestTimeout) || 60)
  );
  const body = JSON.stringify({
    model,
    temperature: 0,
    max_tokens: 1,
    messages: [{ role: "user", content: "Reply with OK." }]
  });

  if (provider === "anthropic") {
    return {
      url: `${baseUrl}/v1/messages`,
      init: {
        method: "POST",
        headers: {
          "x-api-key": apiKey,
          "anthropic-version": "2023-06-01",
          "Content-Type": "application/json"
        },
        body
      },
      timeoutMs: timeoutSeconds * 1000
    };
  }

  return {
    url: `${baseUrl}/chat/completions`,
    init: {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json"
      },
      body
    },
    timeoutMs: timeoutSeconds * 1000
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function providerMessage(payload: unknown): string {
  if (!isRecord(payload)) return "";
  const error = payload.error;
  if (typeof error === "string") return error;
  if (isRecord(error) && typeof error.message === "string") return error.message;
  if (typeof payload.message === "string") return payload.message;
  return "";
}

function sanitizeMessage(message: string, apiKey: string): string {
  const withoutKey = apiKey ? message.split(apiKey).join("[已隐藏]") : message;
  return withoutKey.replace(/[\r\n]+/g, " ").trim().slice(0, 180);
}

function validProviderPayload(provider: string, payload: unknown): boolean {
  if (!isRecord(payload)) return false;
  if (provider === "anthropic") return Array.isArray(payload.content);
  return Array.isArray(payload.choices);
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function testApiConnection(
  settings: ApiConnectionSettings,
  dependencies: ApiConnectionDependencies = {}
): Promise<ApiConnectionTestResult> {
  const fetchImpl = dependencies.fetch ?? fetch;
  const now = dependencies.now ?? Date.now;
  const scheduleTimeout = dependencies.setTimeout ?? setTimeout;
  const cancelTimeout = dependencies.clearTimeout ?? clearTimeout;
  const startedAt = now();
  const elapsed = () => Math.max(0, Math.round(now() - startedAt));
  let timeout: ReturnType<typeof setTimeout> | undefined;

  try {
    const request = buildApiConnectionRequest(settings);
    const controller = new AbortController();
    timeout = scheduleTimeout(() => controller.abort(), request.timeoutMs);
    const response = await fetchImpl(request.url, {
      ...request.init,
      signal: controller.signal
    });
    const payload = await readJson(response);

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        return { ok: false, message: "API Key 认证失败", elapsedMs: elapsed() };
      }
      if (response.status === 404) {
        return { ok: false, message: "接口地址或模型不存在", elapsedMs: elapsed() };
      }
      if (response.status === 408) {
        return { ok: false, message: "请求超时", elapsedMs: elapsed() };
      }

      const detail = sanitizeMessage(providerMessage(payload), settings.apiKey.trim());
      const suffix = detail ? `：${detail}` : "";
      return {
        ok: false,
        message: `API 请求失败（HTTP ${response.status}）${suffix}`,
        elapsedMs: elapsed()
      };
    }

    const provider = String(settings.provider || "openai").trim().toLowerCase();
    if (!validProviderPayload(provider, payload)) {
      return { ok: false, message: "模型响应格式无效", elapsedMs: elapsed() };
    }

    return { ok: true, message: "连接成功，模型可用", elapsedMs: elapsed() };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return { ok: false, message: "请求超时", elapsedMs: elapsed() };
    }
    if (error instanceof TypeError) {
      return { ok: false, message: "无法连接 API 地址", elapsedMs: elapsed() };
    }
    const detail = sanitizeMessage(
      error instanceof Error ? error.message : String(error),
      String(settings.apiKey || "").trim()
    );
    return {
      ok: false,
      message: detail || "连通测试失败，请重试",
      elapsedMs: elapsed()
    };
  } finally {
    if (timeout !== undefined) cancelTimeout(timeout);
  }
}
