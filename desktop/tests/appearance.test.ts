import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  CLASSIC_PALETTE,
  DEFAULT_TYPOGRAPHY,
  getCompactShapeForSkin,
  getContrastRatio,
  getDefaultAppearancePreferences,
  getReadableForeground,
  isSamePalette,
  mergeAndValidateAppearancePreferences,
  normalizeFontSize,
  normalizeHexColor,
  parseAppearancePreferences,
  readAppearancePreferences,
  updatePaletteHistory,
  validateSkinId,
  writeAppearancePreferences,
  type PaletteHistoryItem,
  type ThemePalette
} from "../electron/appearance.js";

function customPalette(seed: number): ThemePalette {
  const color = (offset: number) => `#${((seed + offset) % 0xFFFFFF).toString(16).padStart(6, "0").toUpperCase()}`;
  return {
    warmAccent: color(0x111111),
    background: color(0x222222),
    secondaryAccent: color(0x333333),
    primaryAccent: color(0x444444)
  };
}

test("appearance version 2 defaults preserve every registered skin", () => {
  assert.deepEqual(getDefaultAppearancePreferences(), {
    version: 2,
    skinId: "classic",
    alwaysOnTop: true,
    palette: CLASSIC_PALETTE,
    typography: DEFAULT_TYPOGRAPHY,
    paletteHistory: []
  });
  assert.equal(validateSkinId("animated-cat"), "animated-cat");
  assert.equal(validateSkinId("maltese"), "maltese");
  assert.equal(validateSkinId("unknown"), "classic");
});

test("version 1 preferences migrate without losing the selected skin", () => {
  assert.deepEqual(parseAppearancePreferences({ version: 1, skinId: "maltese" }), {
    version: 2,
    skinId: "maltese",
    alwaysOnTop: true,
    palette: CLASSIC_PALETTE,
    typography: DEFAULT_TYPOGRAPHY,
    paletteHistory: []
  });
});

test("invalid individual fields are repaired without discarding valid values", () => {
  const parsed = parseAppearancePreferences({
    version: 2,
    skinId: "animated-cat",
    alwaysOnTop: false,
    palette: {
      warmAccent: "#123456",
      background: "bad",
      secondaryAccent: "abcdef",
      primaryAccent: "#ABCDEF"
    },
    typography: { baseFontSizePx: 99, fontColor: "invalid" },
    paletteHistory: [{ id: "bad", palette: {}, createdAt: "x", lastUsedAt: "x" }]
  });
  assert.equal(parsed.skinId, "animated-cat");
  assert.equal(parsed.alwaysOnTop, false);
  assert.equal(parsed.palette.warmAccent, "#123456");
  assert.equal(parsed.palette.background, CLASSIC_PALETTE.background);
  assert.equal(parsed.palette.secondaryAccent, "#ABCDEF");
  assert.equal(parsed.typography.baseFontSizePx, 18);
  assert.equal(parsed.typography.fontColor, DEFAULT_TYPOGRAPHY.fontColor);
  assert.deepEqual(parsed.paletteHistory, []);
});

test("appearance preferences persist atomically and recover from damaged JSON", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "desktop-appearance-"));
  const file = path.join(directory, "ui-preferences.json");
  try {
    const preferences = {
      ...getDefaultAppearancePreferences(),
      skinId: "maltese" as const,
      alwaysOnTop: false
    };
    writeAppearancePreferences(file, preferences);
    assert.deepEqual(readAppearancePreferences(file), preferences);
    fs.writeFileSync(file, "not-json", "utf8");
    assert.deepEqual(readAppearancePreferences(file), getDefaultAppearancePreferences());
    assert.deepEqual(fs.readdirSync(directory).filter((name) => name.endsWith(".tmp")), []);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("hex colors and font sizes are normalized strictly", () => {
  assert.equal(normalizeHexColor("#ffb6a6"), "#FFB6A6");
  assert.equal(normalizeHexColor("ffb6a6"), "#FFB6A6");
  assert.equal(normalizeHexColor("#FFF"), null);
  assert.equal(normalizeHexColor("#FFFFFF00"), null);
  assert.equal(normalizeHexColor("transparent"), null);
  assert.equal(normalizeFontSize(11), 12);
  assert.equal(normalizeFontSize(19), 18);
  assert.equal(normalizeFontSize(14.6), 15);
  assert.equal(normalizeFontSize(Number.NaN), 13);
});

test("palette history deduplicates, reorders, excludes classic, and keeps five", () => {
  const first = customPalette(1);
  let history: PaletteHistoryItem[] = updatePaletteHistory([], CLASSIC_PALETTE, {
    record: true,
    now: "2026-01-01T00:00:00.000Z"
  });
  assert.deepEqual(history, []);

  history = updatePaletteHistory(history, first, { record: true, now: "2026-01-01T00:00:01.000Z" });
  const originalId = history[0].id;
  history = updatePaletteHistory(history, customPalette(2), { record: true, now: "2026-01-01T00:00:02.000Z" });
  history = updatePaletteHistory(history, first, { record: true, now: "2026-01-01T00:00:03.000Z" });
  assert.equal(history.length, 2);
  assert.equal(history[0].id, originalId);
  assert.ok(isSamePalette(history[0].palette, first));
  assert.equal(history[0].createdAt, "2026-01-01T00:00:01.000Z");
  assert.equal(history[0].lastUsedAt, "2026-01-01T00:00:03.000Z");

  for (let index = 3; index <= 7; index += 1) {
    history = updatePaletteHistory(history, customPalette(index), {
      record: true,
      now: `2026-01-01T00:00:0${index}.000Z`
    });
  }
  assert.equal(history.length, 5);
  assert.ok(isSamePalette(history[0].palette, customPalette(7)));
});

test("merging a skin or font patch preserves unrelated appearance settings", () => {
  const palette = customPalette(20);
  const current = {
    ...getDefaultAppearancePreferences(),
    alwaysOnTop: false,
    palette,
    typography: { baseFontSizePx: 16, fontColor: "#FFFFFF" }
  };
  const skinChanged = mergeAndValidateAppearancePreferences(current, { skinId: "maltese" });
  assert.equal(skinChanged.skinId, "maltese");
  assert.equal(skinChanged.alwaysOnTop, false);
  assert.deepEqual(skinChanged.palette, palette);
  assert.deepEqual(skinChanged.typography, current.typography);

  const fontChanged = mergeAndValidateAppearancePreferences(current, {
    typography: { baseFontSizePx: 17, fontColor: "#FFFFFF" }
  });
  assert.deepEqual(fontChanged.paletteHistory, []);
  assert.equal(fontChanged.typography.baseFontSizePx, 17);
});

test("unreadable text is blocked while readable foreground selection stays valid", () => {
  const current = getDefaultAppearancePreferences();
  assert.throws(() => mergeAndValidateAppearancePreferences(current, {
    palette: { ...CLASSIC_PALETTE, background: "#FFFFFF" },
    typography: { baseFontSizePx: 13, fontColor: "#FFFFFF" }
  }), /过于接近/);
  assert.ok(getContrastRatio("#000000", "#FFFFFF") > 20);
  assert.equal(getReadableForeground("#FFFFFF"), "#000000");
  assert.equal(getReadableForeground("#000000"), "#FFFFFF");
});

test("classic is circular while animated skins keep the full compact rectangle", () => {
  const classic = getCompactShapeForSkin("classic", 80);
  const animated = getCompactShapeForSkin("animated-cat", 80);
  const maltese = getCompactShapeForSkin("maltese", 80);
  assert.ok(classic.length > 1);
  assert.ok(classic.some((rect) => rect.width < 80));
  assert.deepEqual(animated, [{ x: 0, y: 0, width: 80, height: 80 }]);
  assert.deepEqual(maltese, [{ x: 0, y: 0, width: 80, height: 80 }]);
});
