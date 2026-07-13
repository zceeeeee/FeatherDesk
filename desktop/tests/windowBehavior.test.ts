import assert from "node:assert/strict";
import test from "node:test";
import { applyAlwaysOnTopToWindow, type AlwaysOnTopWindow } from "../electron/windowBehavior.js";

function createWindowMock() {
  const calls: Array<{ method: string; arguments: unknown[] }> = [];
  const target: AlwaysOnTopWindow = {
    setAlwaysOnTop: (...args) => calls.push({ method: "setAlwaysOnTop", arguments: args }),
    moveTop: (...args) => calls.push({ method: "moveTop", arguments: args }),
    setVisibleOnAllWorkspaces: (...args) => calls.push({ method: "setVisibleOnAllWorkspaces", arguments: args })
  };
  return { target, calls };
}

test("Windows always-on-top uses floating and normal levels without workspace calls", () => {
  const enabled = createWindowMock();
  applyAlwaysOnTopToWindow(enabled.target, true, "win32", true);
  assert.deepEqual(enabled.calls, [
    { method: "setAlwaysOnTop", arguments: [true, "floating"] },
    { method: "moveTop", arguments: [] }
  ]);

  const disabled = createWindowMock();
  applyAlwaysOnTopToWindow(disabled.target, false, "win32", true);
  assert.deepEqual(disabled.calls, [
    { method: "setAlwaysOnTop", arguments: [false, "normal"] }
  ]);
});

test("macOS and Linux synchronize workspace visibility", () => {
  const mac = createWindowMock();
  applyAlwaysOnTopToWindow(mac.target, true, "darwin");
  assert.deepEqual(mac.calls, [
    { method: "setAlwaysOnTop", arguments: [true, "floating"] },
    { method: "setVisibleOnAllWorkspaces", arguments: [true, { visibleOnFullScreen: true }] }
  ]);

  const linux = createWindowMock();
  applyAlwaysOnTopToWindow(linux.target, false, "linux");
  assert.deepEqual(linux.calls, [
    { method: "setAlwaysOnTop", arguments: [false, "normal"] },
    { method: "setVisibleOnAllWorkspaces", arguments: [false] }
  ]);
});
