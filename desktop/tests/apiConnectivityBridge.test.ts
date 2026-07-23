import assert from "node:assert/strict";
import test from "node:test";
import { desktopSettings } from "../src/services/api.js";
import type { DesktopBridge, DesktopSettings } from "../src/types.js";

const currentSettings: DesktopSettings = {
  provider: "openai",
  apiKey: "unsaved-key",
  apiKeyMasked: "已安全保存",
  baseUrl: "https://example.test/v1",
  model: "model-a",
  temperature: 0.2,
  requestTimeout: 60,
  browserHeadless: false,
  maxSteps: 20,
  useCloakBrowser: true,
  exploreOcrEnabled: true,
  exploreVisionEnabled: false,
  logLevel: "INFO"
};

test("desktop settings test forwards unsaved form values", async () => {
  let received: DesktopSettings | undefined;
  const desktopAgent = {
    testApiConnection: async (settings: DesktopSettings) => {
      received = settings;
      return { ok: true, message: "连接成功，模型可用", elapsedMs: 12 };
    }
  } as unknown as DesktopBridge;
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { desktopAgent }
  });

  const result = await desktopSettings.test(currentSettings);

  assert.equal(received?.apiKey, "unsaved-key");
  assert.equal(received?.baseUrl, "https://example.test/v1");
  assert.equal(received?.model, "model-a");
  assert.deepEqual(result, {
    ok: true,
    message: "连接成功，模型可用",
    elapsedMs: 12
  });
});
