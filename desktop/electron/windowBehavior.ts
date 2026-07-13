export interface AlwaysOnTopWindow {
  setAlwaysOnTop(enabled: boolean, level: "floating" | "normal"): void;
  moveTop(): void;
  setVisibleOnAllWorkspaces(
    visible: boolean,
    options?: { visibleOnFullScreen?: boolean }
  ): void;
}

export function applyAlwaysOnTopToWindow(
  targetWindow: AlwaysOnTopWindow,
  enabled: boolean,
  platform: NodeJS.Platform,
  bringToFront = false
): void {
  targetWindow.setAlwaysOnTop(enabled, enabled ? "floating" : "normal");
  if (enabled && bringToFront) targetWindow.moveTop();
  if (platform === "darwin") {
    targetWindow.setVisibleOnAllWorkspaces(enabled, { visibleOnFullScreen: enabled });
  } else if (platform === "linux") {
    targetWindow.setVisibleOnAllWorkspaces(enabled);
  }
}
