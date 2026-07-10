import { useRef } from "react";
import { getAgentStateLabel } from "../skins/skinRegistry";
import { useAgentStore } from "../stores/agentStore";
import { useAppearanceStore } from "../stores/appearanceStore";
import { PetAvatar } from "./PetAvatar";

export function PetCircle() {
  const visualState = useAgentStore((state) => state.visualState);
  const skinId = useAppearanceStore((state) => state.skinId);
  const pointer = useRef<{
    x: number;
    y: number;
    windowX: number;
    windowY: number;
    dragging: boolean;
  } | null>(null);

  async function onPointerDown(event: React.PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const bounds = await window.desktopAgent.getWindowBounds();
    pointer.current = {
      x: event.screenX,
      y: event.screenY,
      windowX: bounds.x,
      windowY: bounds.y,
      dragging: false
    };
  }

  function onPointerMove(event: React.PointerEvent<HTMLButtonElement>) {
    const start = pointer.current;
    if (!start) return;
    const dx = event.screenX - start.x;
    const dy = event.screenY - start.y;
    if (!start.dragging && Math.hypot(dx, dy) >= 5) start.dragging = true;
    if (start.dragging) {
      void window.desktopAgent.setPetPosition(start.windowX + dx, start.windowY + dy);
    }
  }

  function onPointerUp(event: React.PointerEvent<HTMLButtonElement>) {
    const start = pointer.current;
    pointer.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
    if (start && !start.dragging) void window.desktopAgent.expandChat();
  }

  return (
    <button
      className={`pet-circle skin-${skinId}`}
      aria-label={`桌面智能体，${getAgentStateLabel(visualState)}`}
      title={getAgentStateLabel(visualState)}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onClick={(event) => {
        if (event.detail === 0) void window.desktopAgent.expandChat();
      }}
      onContextMenu={(event) => {
        event.preventDefault();
        void window.desktopAgent.showPetMenu();
      }}
    >
      <PetAvatar skinId={skinId} state={visualState} variant="compact" />
    </button>
  );
}
