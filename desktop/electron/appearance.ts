import fs from "node:fs";
import path from "node:path";
import {
  parseAppearancePreferences,
  type AppearancePreferences,
  type PetSkinId
} from "./appearanceModel.js";

export * from "./appearanceModel.js";

export interface ShapeRectangle {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function readAppearancePreferences(file: string): AppearancePreferences {
  try {
    return parseAppearancePreferences(JSON.parse(fs.readFileSync(file, "utf8")));
  } catch {
    return parseAppearancePreferences(null);
  }
}

export function writeAppearancePreferences(
  file: string,
  preferences: AppearancePreferences
): AppearancePreferences {
  const validated = parseAppearancePreferences(preferences);
  const directory = path.dirname(file);
  const temporary = path.join(
    directory,
    `.${path.basename(file)}.${process.pid}.${Date.now()}.tmp`
  );
  fs.mkdirSync(directory, { recursive: true });
  try {
    fs.writeFileSync(temporary, JSON.stringify(validated, null, 2), "utf8");
    fs.renameSync(temporary, file);
  } finally {
    if (fs.existsSync(temporary)) fs.rmSync(temporary, { force: true });
  }
  return validated;
}

export function getCompactShapeForSkin(
  skinId: PetSkinId,
  size: number
): ShapeRectangle[] {
  if (skinId !== "classic") {
    return [{ x: 0, y: 0, width: size, height: size }];
  }

  const rects: ShapeRectangle[] = [];
  for (let y = 0; y < size; y += 4) {
    const dy = y + 2 - size / 2;
    const half = Math.sqrt(Math.max(0, (size / 2) ** 2 - dy ** 2));
    rects.push({
      x: Math.round(size / 2 - half),
      y,
      width: Math.max(1, Math.round(half * 2)),
      height: Math.min(4, size - y)
    });
  }
  return rects;
}
