import { create } from "zustand";
import {
  CLASSIC_PALETTE,
  DEFAULT_TYPOGRAPHY,
  getDefaultAppearancePreferences
} from "../../electron/appearanceModel.js";
import type {
  AppearancePreferences,
  PaletteHistoryItem,
  PetSkinId,
  ThemePalette,
  TypographyPreferences
} from "../types.js";

interface AppearanceState {
  skinId: PetSkinId;
  alwaysOnTop: boolean;
  palette: ThemePalette;
  typography: TypographyPreferences;
  paletteHistory: PaletteHistoryItem[];
  initialized: boolean;
  saving: boolean;
  error: string | null;
  lastSavedAt: number | null;
  initializeAppearance(): Promise<void>;
  disposeAppearance(): void;
  setSkinId(skinId: PetSkinId): Promise<void>;
  setAlwaysOnTop(enabled: boolean): Promise<void>;
  saveTheme(
    palette: ThemePalette,
    typography: TypographyPreferences,
    recordPaletteHistory: boolean
  ): Promise<void>;
  applyHistoryPalette(historyId: string): Promise<void>;
  deleteHistoryPalette(historyId: string): Promise<void>;
  clearPaletteHistory(): Promise<void>;
  resetClassicPalette(): Promise<void>;
  resetAppearanceDefaults(): Promise<void>;
  handleExternalAppearanceChange(preferences: AppearancePreferences): void;
}

let removeAppearanceListener: (() => void) | null = null;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function valuesFromPreferences(preferences: AppearancePreferences) {
  return {
    skinId: preferences.skinId,
    alwaysOnTop: preferences.alwaysOnTop,
    palette: { ...preferences.palette },
    typography: { ...preferences.typography },
    paletteHistory: preferences.paletteHistory.map((item) => ({
      ...item,
      palette: { ...item.palette }
    })),
    initialized: true,
    saving: false,
    error: null
  };
}

const defaults = getDefaultAppearancePreferences();

export const useAppearanceStore = create<AppearanceState>((set, get) => ({
  ...valuesFromPreferences(defaults),
  initialized: false,
  lastSavedAt: null,

  initializeAppearance: async () => {
    if (!removeAppearanceListener) {
      removeAppearanceListener = window.desktopAgent.onAppearanceChanged(
        get().handleExternalAppearanceChange
      );
    }
    try {
      const preferences = await window.desktopAgent.getAppearancePreferences();
      set(valuesFromPreferences(preferences));
    } catch (error) {
      set({
        ...valuesFromPreferences(defaults),
        error: errorMessage(error, "无法读取外观设置")
      });
    }
  },

  disposeAppearance: () => {
    removeAppearanceListener?.();
    removeAppearanceListener = null;
  },

  setSkinId: async (skinId) => {
    if (get().saving || skinId === get().skinId) return;
    const previous = get().skinId;
    set({ skinId, saving: true, error: null });
    try {
      const saved = await window.desktopAgent.updateAppearancePreferences({ skinId });
      set({ ...valuesFromPreferences(saved), lastSavedAt: Date.now() });
    } catch (error) {
      set({
        skinId: previous,
        saving: false,
        error: errorMessage(error, "皮肤保存失败")
      });
    }
  },

  setAlwaysOnTop: async (enabled) => {
    if (get().saving || enabled === get().alwaysOnTop) return;
    const previous = get().alwaysOnTop;
    set({ alwaysOnTop: enabled, saving: true, error: null });
    try {
      const saved = await window.desktopAgent.updateAppearancePreferences({ alwaysOnTop: enabled });
      set({ ...valuesFromPreferences(saved), lastSavedAt: Date.now() });
    } catch (error) {
      set({
        alwaysOnTop: previous,
        saving: false,
        error: errorMessage(error, "置顶设置保存失败，已恢复原设置")
      });
    }
  },

  saveTheme: async (palette, typography, recordPaletteHistory) => {
    if (get().saving) return;
    set({ saving: true, error: null });
    try {
      const saved = await window.desktopAgent.updateAppearancePreferences(
        { palette, typography },
        { recordPaletteHistory }
      );
      set({ ...valuesFromPreferences(saved), lastSavedAt: Date.now() });
    } catch (error) {
      set({ saving: false, error: errorMessage(error, "主题保存失败") });
      throw error;
    }
  },

  applyHistoryPalette: async (historyId) => {
    if (get().saving) return;
    const historyItem = get().paletteHistory.find((item) => item.id === historyId);
    if (!historyItem) return;
    set({ saving: true, error: null });
    try {
      const saved = await window.desktopAgent.updateAppearancePreferences(
        { palette: historyItem.palette },
        { recordPaletteHistory: true }
      );
      set({ ...valuesFromPreferences(saved), lastSavedAt: Date.now() });
    } catch (error) {
      set({ saving: false, error: errorMessage(error, "历史配色应用失败") });
    }
  },

  deleteHistoryPalette: async (historyId) => {
    if (get().saving) return;
    set({ saving: true, error: null });
    try {
      const saved = await window.desktopAgent.deletePaletteHistory(historyId);
      set({ ...valuesFromPreferences(saved), lastSavedAt: Date.now() });
    } catch (error) {
      set({ saving: false, error: errorMessage(error, "配色记录删除失败") });
    }
  },

  clearPaletteHistory: async () => {
    if (get().saving) return;
    set({ saving: true, error: null });
    try {
      const saved = await window.desktopAgent.clearPaletteHistory();
      set({ ...valuesFromPreferences(saved), lastSavedAt: Date.now() });
    } catch (error) {
      set({ saving: false, error: errorMessage(error, "配色历史清空失败") });
    }
  },

  resetClassicPalette: async () => {
    if (get().saving) return;
    set({ saving: true, error: null });
    try {
      const saved = await window.desktopAgent.updateAppearancePreferences(
        { palette: { ...CLASSIC_PALETTE } },
        { recordPaletteHistory: false }
      );
      set({ ...valuesFromPreferences(saved), lastSavedAt: Date.now() });
    } catch (error) {
      set({ saving: false, error: errorMessage(error, "经典配色恢复失败") });
    }
  },

  resetAppearanceDefaults: async () => {
    if (get().saving) return;
    set({ saving: true, error: null });
    try {
      const saved = await window.desktopAgent.updateAppearancePreferences(
        {
          skinId: "classic",
          alwaysOnTop: true,
          palette: { ...CLASSIC_PALETTE },
          typography: { ...DEFAULT_TYPOGRAPHY }
        },
        { recordPaletteHistory: false }
      );
      set({ ...valuesFromPreferences(saved), lastSavedAt: Date.now() });
    } catch (error) {
      set({ saving: false, error: errorMessage(error, "默认外观恢复失败") });
    }
  },

  handleExternalAppearanceChange: (preferences) => {
    set(valuesFromPreferences(preferences));
  }
}));
