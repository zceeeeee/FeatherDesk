import { getReadableForeground } from "./colorUtils";
import type { ThemePalette, TypographyPreferences } from "../types";

export function applyAppearanceToDocument(
  palette: ThemePalette,
  typography: TypographyPreferences
): void {
  const root = document.documentElement;
  root.style.setProperty("--theme-warm-accent", palette.warmAccent);
  root.style.setProperty("--theme-background", palette.background);
  root.style.setProperty("--theme-secondary-accent", palette.secondaryAccent);
  root.style.setProperty("--theme-primary-accent", palette.primaryAccent);
  root.style.setProperty("--theme-font-color", typography.fontColor);
  root.style.setProperty("--theme-font-size-base", `${typography.baseFontSizePx}px`);
  root.style.setProperty("--theme-on-primary", getReadableForeground(palette.primaryAccent));
  root.style.setProperty("--theme-on-secondary", getReadableForeground(palette.secondaryAccent));
  root.style.setProperty("--theme-on-warm", getReadableForeground(palette.warmAccent));
}
