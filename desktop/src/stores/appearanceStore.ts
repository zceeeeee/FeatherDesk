import { create } from "zustand";
import type { AppearancePreferences, PetSkinId } from "../types";

interface AppearanceState {
  skinId: PetSkinId;
  initialized: boolean;
  saving: boolean;
  error: string | null;
  lastSavedAt: number | null;
  initializeAppearance(): Promise<void>;
  disposeAppearance(): void;
  setSkinId(skinId: PetSkinId): Promise<void>;
  handleExternalAppearanceChange(preferences: AppearancePreferences): void;
}

let removeAppearanceListener: (() => void) | null = null;

export const useAppearanceStore = create<AppearanceState>((set, get) => ({
  skinId: "classic",
  initialized: false,
  saving: false,
  error: null,
  lastSavedAt: null,

  initializeAppearance: async () => {
    if (!removeAppearanceListener) {
      removeAppearanceListener = window.desktopAgent.onAppearanceChanged(
        get().handleExternalAppearanceChange
      );
    }
    try {
      const preferences = await window.desktopAgent.getAppearancePreferences();
      set({ skinId: preferences.skinId, initialized: true, error: null });
    } catch (error) {
      set({
        skinId: "classic",
        initialized: true,
        error: error instanceof Error ? error.message : "无法读取外观设置"
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
      const saved = await window.desktopAgent.setSkin(skinId);
      set({ skinId: saved.skinId, saving: false, lastSavedAt: Date.now() });
    } catch (error) {
      set({
        skinId: previous,
        saving: false,
        error: error instanceof Error ? error.message : "皮肤保存失败"
      });
    }
  },

  handleExternalAppearanceChange: (preferences) => {
    set({ skinId: preferences.skinId, initialized: true, saving: false, error: null });
  }
}));
