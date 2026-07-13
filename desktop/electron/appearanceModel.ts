export type PetSkinId = "classic" | "animated-cat" | "maltese";

export interface ThemePalette {
  warmAccent: string;
  background: string;
  secondaryAccent: string;
  primaryAccent: string;
}

export interface TypographyPreferences {
  baseFontSizePx: number;
  fontColor: string;
}

export interface PaletteHistoryItem {
  id: string;
  palette: ThemePalette;
  createdAt: string;
  lastUsedAt: string;
}

export interface AppearancePreferences {
  version: 2;
  skinId: PetSkinId;
  alwaysOnTop: boolean;
  palette: ThemePalette;
  typography: TypographyPreferences;
  paletteHistory: PaletteHistoryItem[];
}

export interface AppearanceUpdatePatch {
  skinId?: PetSkinId;
  alwaysOnTop?: boolean;
  palette?: ThemePalette;
  typography?: TypographyPreferences;
}

export interface UpdateAppearanceOptions {
  recordPaletteHistory?: boolean;
  now?: string;
}

export const CLASSIC_PALETTE: ThemePalette = {
  warmAccent: "#FFB6A6",
  background: "#FFEBD3",
  secondaryAccent: "#9BCEC1",
  primaryAccent: "#67A2C5"
};

export const DEFAULT_TYPOGRAPHY: TypographyPreferences = {
  baseFontSizePx: 13,
  fontColor: "#2F4858"
};

export const MIN_FONT_SIZE_PX = 12;
export const MAX_FONT_SIZE_PX = 18;

const VALID_SKIN_IDS = new Set<PetSkinId>(["classic", "animated-cat", "maltese"]);
const PALETTE_FIELDS: Array<keyof ThemePalette> = [
  "warmAccent",
  "background",
  "secondaryAccent",
  "primaryAccent"
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function validateSkinId(value: unknown): PetSkinId {
  return typeof value === "string" && VALID_SKIN_IDS.has(value as PetSkinId)
    ? value as PetSkinId
    : "classic";
}

export function normalizeHexColor(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().replace(/^#/, "");
  return /^[0-9A-Fa-f]{6}$/.test(normalized) ? `#${normalized.toUpperCase()}` : null;
}

export function normalizeFontSize(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_TYPOGRAPHY.baseFontSizePx;
  }
  return Math.min(MAX_FONT_SIZE_PX, Math.max(MIN_FONT_SIZE_PX, Math.round(value)));
}

export function normalizeThemePalette(value: unknown): ThemePalette | null {
  if (!isRecord(value)) return null;
  const result = {} as ThemePalette;
  for (const field of PALETTE_FIELDS) {
    const color = normalizeHexColor(value[field]);
    if (!color) return null;
    result[field] = color;
  }
  return result;
}

function repairThemePalette(value: unknown): ThemePalette {
  const candidate = isRecord(value) ? value : {};
  return {
    warmAccent: normalizeHexColor(candidate.warmAccent) ?? CLASSIC_PALETTE.warmAccent,
    background: normalizeHexColor(candidate.background) ?? CLASSIC_PALETTE.background,
    secondaryAccent: normalizeHexColor(candidate.secondaryAccent) ?? CLASSIC_PALETTE.secondaryAccent,
    primaryAccent: normalizeHexColor(candidate.primaryAccent) ?? CLASSIC_PALETTE.primaryAccent
  };
}

function repairTypography(value: unknown): TypographyPreferences {
  const candidate = isRecord(value) ? value : {};
  return {
    baseFontSizePx: normalizeFontSize(candidate.baseFontSizePx),
    fontColor: normalizeHexColor(candidate.fontColor) ?? DEFAULT_TYPOGRAPHY.fontColor
  };
}

export function paletteKey(palette: ThemePalette): string {
  return PALETTE_FIELDS.map((field) => palette[field]).join("|");
}

export function isSamePalette(left: ThemePalette, right: ThemePalette): boolean {
  return paletteKey(left) === paletteKey(right);
}

function isValidTimestamp(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && Number.isFinite(Date.parse(value));
}

function sanitizePaletteHistory(value: unknown): PaletteHistoryItem[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const seenIds = new Set<string>();
  const result: PaletteHistoryItem[] = [];
  for (const item of value) {
    if (!isRecord(item) || typeof item.id !== "string" || !item.id.trim()) continue;
    const id = item.id.trim();
    if (seenIds.has(id)) continue;
    const palette = normalizeThemePalette(item.palette);
    if (!palette || isSamePalette(palette, CLASSIC_PALETTE)) continue;
    if (!isValidTimestamp(item.createdAt) || !isValidTimestamp(item.lastUsedAt)) continue;
    const key = paletteKey(palette);
    if (seen.has(key)) continue;
    seen.add(key);
    seenIds.add(id);
    result.push({
      id,
      palette,
      createdAt: item.createdAt,
      lastUsedAt: item.lastUsedAt
    });
  }
  return result
    .sort((left, right) => Date.parse(right.lastUsedAt) - Date.parse(left.lastUsedAt))
    .slice(0, 5);
}

function stablePaletteHash(palette: ThemePalette): string {
  let hash = 2166136261;
  for (const character of paletteKey(palette)) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

export function updatePaletteHistory(
  history: PaletteHistoryItem[],
  palette: ThemePalette,
  options: { record: boolean; now?: string }
): PaletteHistoryItem[] {
  const current = sanitizePaletteHistory(history);
  if (!options.record || isSamePalette(palette, CLASSIC_PALETTE)) return current;

  const now = isValidTimestamp(options.now) ? options.now : new Date().toISOString();
  const key = paletteKey(palette);
  const existing = current.find((item) => paletteKey(item.palette) === key);
  const nextItem: PaletteHistoryItem = existing
    ? { ...existing, palette: { ...palette }, lastUsedAt: now }
    : {
        id: `palette-${Date.parse(now).toString(36)}-${stablePaletteHash(palette)}`,
        palette: { ...palette },
        createdAt: now,
        lastUsedAt: now
      };
  return [nextItem, ...current.filter((item) => paletteKey(item.palette) !== key)].slice(0, 5);
}

export function getDefaultAppearancePreferences(): AppearancePreferences {
  return {
    version: 2,
    skinId: "classic",
    alwaysOnTop: true,
    palette: { ...CLASSIC_PALETTE },
    typography: { ...DEFAULT_TYPOGRAPHY },
    paletteHistory: []
  };
}

export function parseAppearancePreferences(value: unknown): AppearancePreferences {
  if (!isRecord(value)) return getDefaultAppearancePreferences();
  return {
    version: 2,
    skinId: validateSkinId(value.skinId),
    alwaysOnTop: typeof value.alwaysOnTop === "boolean" ? value.alwaysOnTop : true,
    palette: repairThemePalette(value.palette),
    typography: repairTypography(value.typography),
    paletteHistory: sanitizePaletteHistory(value.paletteHistory)
  };
}

function hexToRgb(color: string): [number, number, number] {
  const normalized = normalizeHexColor(color) ?? "#000000";
  return [
    Number.parseInt(normalized.slice(1, 3), 16),
    Number.parseInt(normalized.slice(3, 5), 16),
    Number.parseInt(normalized.slice(5, 7), 16)
  ];
}

function relativeLuminance(color: string): number {
  const channels = hexToRgb(color).map((channel) => {
    const value = channel / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

export function getContrastRatio(foreground: string, background: string): number {
  const foregroundLuminance = relativeLuminance(foreground);
  const backgroundLuminance = relativeLuminance(background);
  const lighter = Math.max(foregroundLuminance, backgroundLuminance);
  const darker = Math.min(foregroundLuminance, backgroundLuminance);
  return (lighter + 0.05) / (darker + 0.05);
}

export function getReadableForeground(background: string): "#000000" | "#FFFFFF" {
  return getContrastRatio("#000000", background) >= getContrastRatio("#FFFFFF", background)
    ? "#000000"
    : "#FFFFFF";
}

export function mergeAndValidateAppearancePreferences(
  previous: AppearancePreferences,
  patchValue: unknown,
  optionsValue: unknown = {}
): AppearancePreferences {
  if (!isRecord(patchValue)) throw new TypeError("外观设置更新格式无效");
  const patch = patchValue as Record<string, unknown>;
  const options = isRecord(optionsValue) ? optionsValue : {};
  const next: AppearancePreferences = {
    ...previous,
    version: 2,
    palette: { ...previous.palette },
    typography: { ...previous.typography },
    paletteHistory: [...previous.paletteHistory]
  };

  if ("skinId" in patch) {
    if (typeof patch.skinId !== "string" || !VALID_SKIN_IDS.has(patch.skinId as PetSkinId)) {
      throw new TypeError("宠物皮肤无效");
    }
    next.skinId = patch.skinId as PetSkinId;
  }
  if ("alwaysOnTop" in patch) {
    if (typeof patch.alwaysOnTop !== "boolean") throw new TypeError("始终置顶设置无效");
    next.alwaysOnTop = patch.alwaysOnTop;
  }
  if ("palette" in patch) {
    const palette = normalizeThemePalette(patch.palette);
    if (!palette) throw new TypeError("配色必须使用六位十六进制颜色");
    next.palette = palette;
  }
  if ("typography" in patch) {
    if (!isRecord(patch.typography)) throw new TypeError("字体设置无效");
    const fontColor = normalizeHexColor(patch.typography.fontColor);
    if (!fontColor) throw new TypeError("字体颜色必须使用六位十六进制颜色");
    next.typography = {
      baseFontSizePx: normalizeFontSize(patch.typography.baseFontSizePx),
      fontColor
    };
  }

  if (getContrastRatio(next.typography.fontColor, next.palette.background) < 3) {
    throw new RangeError("字体颜色与主背景过于接近，请调整后重试");
  }
  if ("palette" in patch) {
    next.paletteHistory = updatePaletteHistory(previous.paletteHistory, next.palette, {
      record: options.recordPaletteHistory === true,
      now: typeof options.now === "string" ? options.now : undefined
    });
  }
  return next;
}
