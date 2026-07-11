import assert from "node:assert/strict";
import test from "node:test";
import {
  CLASSIC_PALETTE,
  getDefaultAppearancePreferences,
  type AppearancePreferences
} from "../electron/appearanceModel.js";
import { useAppearanceStore } from "../src/stores/appearanceStore.js";

type AppearanceListener = (preferences: AppearancePreferences) => void;

function installBridge(
  preferences: AppearancePreferences,
  update: (
    patch: Record<string, unknown>,
    options?: Record<string, unknown>
  ) => Promise<AppearancePreferences>
) {
  let listener: AppearanceListener | null = null;
  const bridge = {
    getAppearancePreferences: async () => preferences,
    updateAppearancePreferences: update,
    deletePaletteHistory: async () => ({ ...preferences, paletteHistory: [] }),
    clearPaletteHistory: async () => ({ ...preferences, paletteHistory: [] }),
    onAppearanceChanged: (callback: AppearanceListener) => {
      listener = callback;
      return () => { listener = null; };
    }
  };
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { desktopAgent: bridge }
  });
  return { emit: (next: AppearancePreferences) => listener?.(next) };
}

function resetStore(preferences = getDefaultAppearancePreferences()) {
  useAppearanceStore.getState().disposeAppearance();
  useAppearanceStore.setState({
    skinId: preferences.skinId,
    alwaysOnTop: preferences.alwaysOnTop,
    palette: { ...preferences.palette },
    typography: { ...preferences.typography },
    paletteHistory: [...preferences.paletteHistory],
    initialized: false,
    saving: false,
    error: null,
    lastSavedAt: null
  });
}

test("appearance store initializes and accepts complete external updates", async () => {
  const initial = {
    ...getDefaultAppearancePreferences(),
    skinId: "maltese" as const,
    alwaysOnTop: false,
    palette: { ...CLASSIC_PALETTE, primaryAccent: "#123456" }
  };
  resetStore();
  const bridge = installBridge(initial, async () => initial);
  await useAppearanceStore.getState().initializeAppearance();
  assert.equal(useAppearanceStore.getState().skinId, "maltese");
  assert.equal(useAppearanceStore.getState().alwaysOnTop, false);
  assert.equal(useAppearanceStore.getState().palette.primaryAccent, "#123456");

  const external = { ...initial, typography: { baseFontSizePx: 18, fontColor: "#111111" } };
  bridge.emit(external);
  assert.deepEqual(useAppearanceStore.getState().typography, external.typography);
  useAppearanceStore.getState().disposeAppearance();
});

test("always-on-top changes optimistically and rolls back on failure", async () => {
  const initial = getDefaultAppearancePreferences();
  resetStore(initial);
  installBridge(initial, async () => { throw new Error("save failed"); });
  await useAppearanceStore.getState().initializeAppearance();
  const promise = useAppearanceStore.getState().setAlwaysOnTop(false);
  assert.equal(useAppearanceStore.getState().alwaysOnTop, false);
  await promise;
  assert.equal(useAppearanceStore.getState().alwaysOnTop, true);
  assert.match(useAppearanceStore.getState().error ?? "", /save failed/);
  useAppearanceStore.getState().disposeAppearance();
});

test("changing the skin keeps palette, font, and always-on-top values", async () => {
  const initial = {
    ...getDefaultAppearancePreferences(),
    alwaysOnTop: false,
    palette: { ...CLASSIC_PALETTE, primaryAccent: "#234567" },
    typography: { baseFontSizePx: 16, fontColor: "#101010" }
  };
  let receivedPatch: Record<string, unknown> | null = null;
  resetStore(initial);
  installBridge(initial, async (patch) => {
    receivedPatch = patch;
    return { ...initial, skinId: "animated-cat" };
  });
  await useAppearanceStore.getState().initializeAppearance();
  await useAppearanceStore.getState().setSkinId("animated-cat");
  assert.deepEqual(receivedPatch, { skinId: "animated-cat" });
  assert.equal(useAppearanceStore.getState().alwaysOnTop, false);
  assert.deepEqual(useAppearanceStore.getState().palette, initial.palette);
  assert.deepEqual(useAppearanceStore.getState().typography, initial.typography);
  useAppearanceStore.getState().disposeAppearance();
});

test("theme saving sends history intent and keeps the persisted result", async () => {
  const initial = getDefaultAppearancePreferences();
  const palette = { ...CLASSIC_PALETTE, primaryAccent: "#345678" };
  const typography = { baseFontSizePx: 15, fontColor: "#101010" };
  const saved = {
    ...initial,
    palette,
    typography,
    paletteHistory: [{
      id: "saved-theme",
      palette,
      createdAt: "2026-07-11T00:00:00.000Z",
      lastUsedAt: "2026-07-11T00:00:00.000Z"
    }]
  };
  let receivedOptions: Record<string, unknown> | undefined;
  resetStore(initial);
  installBridge(initial, async (_patch, options) => {
    receivedOptions = options;
    return saved;
  });
  await useAppearanceStore.getState().initializeAppearance();
  await useAppearanceStore.getState().saveTheme(palette, typography, true);
  assert.deepEqual(receivedOptions, { recordPaletteHistory: true });
  assert.deepEqual(useAppearanceStore.getState().palette, palette);
  assert.deepEqual(useAppearanceStore.getState().typography, typography);
  assert.equal(useAppearanceStore.getState().paletteHistory.length, 1);
  useAppearanceStore.getState().disposeAppearance();
});

test("theme save failure leaves the persisted theme in place", async () => {
  const initial = getDefaultAppearancePreferences();
  resetStore(initial);
  installBridge(initial, async () => { throw new Error("theme failed"); });
  await useAppearanceStore.getState().initializeAppearance();
  await assert.rejects(
    useAppearanceStore.getState().saveTheme(
      { ...CLASSIC_PALETTE, primaryAccent: "#456789" },
      { baseFontSizePx: 16, fontColor: "#111111" },
      true
    ),
    /theme failed/
  );
  assert.deepEqual(useAppearanceStore.getState().palette, initial.palette);
  assert.deepEqual(useAppearanceStore.getState().typography, initial.typography);
  assert.equal(useAppearanceStore.getState().saving, false);
  assert.match(useAppearanceStore.getState().error ?? "", /theme failed/);
  useAppearanceStore.getState().disposeAppearance();
});

test("applying a history palette does not change typography", async () => {
  const palette = { ...CLASSIC_PALETTE, warmAccent: "#DDAABB" };
  const initial = {
    ...getDefaultAppearancePreferences(),
    typography: { baseFontSizePx: 17, fontColor: "#121212" },
    paletteHistory: [{
      id: "history-one",
      palette,
      createdAt: "2026-07-10T00:00:00.000Z",
      lastUsedAt: "2026-07-10T00:00:00.000Z"
    }]
  };
  let receivedPatch: Record<string, unknown> | null = null;
  resetStore(initial);
  installBridge(initial, async (patch) => {
    receivedPatch = patch;
    return { ...initial, palette };
  });
  await useAppearanceStore.getState().initializeAppearance();
  await useAppearanceStore.getState().applyHistoryPalette("history-one");
  assert.deepEqual(receivedPatch, { palette });
  assert.deepEqual(useAppearanceStore.getState().typography, initial.typography);
  useAppearanceStore.getState().disposeAppearance();
});
