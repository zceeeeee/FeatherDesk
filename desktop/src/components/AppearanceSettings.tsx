import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Check, Pin, RotateCcw, Save, Trash2, X } from "lucide-react";
import {
  CLASSIC_PALETTE,
  DEFAULT_TYPOGRAPHY,
  MAX_FONT_SIZE_PX,
  MIN_FONT_SIZE_PX
} from "../../electron/appearanceModel";
import { PET_SKINS } from "../skins/skinRegistry";
import { useAppearanceStore } from "../stores/appearanceStore";
import type { PetSkinId, ThemePalette, TypographyPreferences } from "../types";
import {
  getContrastRatio,
  getReadableForeground,
  isSamePalette,
  normalizeFontSize,
  normalizeHexColor,
  normalizeThemePalette
} from "../utils/colorUtils";
import { PetAvatar } from "./PetAvatar";

const skinIds: PetSkinId[] = ["classic", "animated-cat", "maltese"];
const paletteFields: Array<{
  key: keyof ThemePalette;
  label: string;
  description: string;
}> = [
  { key: "warmAccent", label: "暖色强调", description: "用于用户消息、悬停状态和暖色强调。" },
  { key: "background", label: "主背景", description: "用于聊天、Dashboard 和输入区域背景。" },
  { key: "secondaryAccent", label: "次强调色", description: "用于顶部栏、侧边栏和次要按钮。" },
  { key: "primaryAccent", label: "主操作色", description: "用于发送按钮、当前导航和焦点边框。" }
];

function palettePreviewStyle(
  palette: ThemePalette,
  typography: TypographyPreferences
): CSSProperties {
  const warm = normalizeHexColor(palette.warmAccent) ?? CLASSIC_PALETTE.warmAccent;
  const background = normalizeHexColor(palette.background) ?? CLASSIC_PALETTE.background;
  const secondary = normalizeHexColor(palette.secondaryAccent) ?? CLASSIC_PALETTE.secondaryAccent;
  const primary = normalizeHexColor(palette.primaryAccent) ?? CLASSIC_PALETTE.primaryAccent;
  const fontColor = normalizeHexColor(typography.fontColor) ?? DEFAULT_TYPOGRAPHY.fontColor;
  return {
    "--preview-warm-accent": warm,
    "--preview-background": background,
    "--preview-secondary": secondary,
    "--preview-primary": primary,
    "--preview-font-color": fontColor,
    "--preview-font-size": `${normalizeFontSize(typography.baseFontSizePx)}px`,
    "--preview-on-primary": getReadableForeground(primary),
    "--preview-on-secondary": getReadableForeground(secondary)
  } as CSSProperties;
}

export function AppearanceSettings() {
  const store = useAppearanceStore();
  const [draftPalette, setDraftPalette] = useState<ThemePalette>({ ...store.palette });
  const [draftTypography, setDraftTypography] = useState<TypographyPreferences>({ ...store.typography });
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    setDraftPalette({ ...store.palette });
    setDraftTypography({ ...store.typography });
    setLocalError(null);
  }, [store.palette, store.typography]);

  const normalizedPalette = useMemo(
    () => normalizeThemePalette(draftPalette),
    [draftPalette]
  );
  const normalizedFontColor = normalizeHexColor(draftTypography.fontColor);
  const contrast = normalizedPalette && normalizedFontColor
    ? getContrastRatio(normalizedFontColor, normalizedPalette.background)
    : null;
  const paletteChanged = normalizedPalette
    ? !isSamePalette(normalizedPalette, store.palette)
    : false;
  const typographyChanged =
    normalizeFontSize(draftTypography.baseFontSizePx) !== store.typography.baseFontSizePx ||
    normalizedFontColor !== store.typography.fontColor;
  const hasDraftChanges = paletteChanged || typographyChanged;
  const contrastBlocked = contrast !== null && contrast < 3;

  function updatePaletteField(field: keyof ThemePalette, value: string) {
    setDraftPalette((current) => ({ ...current, [field]: value }));
    setLocalError(null);
  }

  function normalizePaletteField(field: keyof ThemePalette) {
    const color = normalizeHexColor(draftPalette[field]);
    if (color) updatePaletteField(field, color);
  }

  function cancelDraft() {
    setDraftPalette({ ...store.palette });
    setDraftTypography({ ...store.typography });
    setLocalError(null);
  }

  async function saveDraft() {
    if (!normalizedPalette || !normalizedFontColor) {
      setLocalError("颜色必须使用六位十六进制格式，例如 #67A2C5。");
      return;
    }
    if (contrastBlocked) {
      setLocalError("字体颜色与主背景过于接近，界面文字可能无法阅读。请调整字体颜色或主背景颜色。");
      return;
    }
    const typography = {
      baseFontSizePx: normalizeFontSize(draftTypography.baseFontSizePx),
      fontColor: normalizedFontColor
    };
    try {
      await store.saveTheme(normalizedPalette, typography, paletteChanged);
    } catch {
      // Store exposes the persisted error state.
    }
  }

  return (
    <div className="page-view appearance-view">
      <header className="page-heading">
        <h1>外观与皮肤</h1>
        <p>皮肤、配色、字体和窗口置顶分别保存，并实时同步到所有窗口。</p>
      </header>

      <section className="appearance-section">
        <div className="appearance-section-heading">
          <div><h2>桌面宠物行为</h2><p>控制宠物窗和展开聊天框的窗口层级。</p></div>
        </div>
        <label className="appearance-toggle-row">
          <span className="appearance-toggle-copy">
            <Pin size={18} />
            <span><strong>始终置顶</strong><small>开启后保持在普通应用窗口上方，Dashboard 不受影响。</small></span>
          </span>
          <input
            type="checkbox"
            checked={store.alwaysOnTop}
            disabled={store.saving}
            onChange={(event) => void store.setAlwaysOnTop(event.target.checked)}
          />
        </label>
      </section>

      <section className="appearance-section">
        <div className="appearance-section-heading">
          <div><h2>宠物皮肤</h2><p>皮肤不会改变当前配色、字体或置顶设置。</p></div>
        </div>
        <div className="skin-grid" role="radiogroup" aria-label="宠物皮肤">
          {skinIds.map((id) => {
            const skin = PET_SKINS[id];
            const selected = store.skinId === id;
            return (
              <button
                type="button"
                role="radio"
                aria-checked={selected}
                className={`skin-card ${selected ? "selected" : ""}`}
                key={id}
                disabled={store.saving}
                onClick={() => void store.setSkinId(id)}
              >
                <span className="skin-preview"><PetAvatar skinId={id} state="idle" variant="preview" /></span>
                <span className="skin-card-copy">
                  <strong>{skin.name}</strong>
                  <span>{skin.description}</span>
                  {skin.attribution ? <small>素材来源：{skin.attribution}</small> : null}
                </span>
                {selected ? <span className="skin-selected"><Check size={14} />当前使用</span> : null}
              </button>
            );
          })}
        </div>
      </section>

      <section className="appearance-section">
        <div className="appearance-section-heading split-heading">
          <div><h2>经典配色</h2><p>固定的内置四色预设，不占用最近配色记录。</p></div>
          <div className="section-actions">
            <button className="button-secondary" disabled={store.saving} onClick={() => void store.resetClassicPalette()}>
              <RotateCcw size={15} />应用经典配色
            </button>
            <button className="button-secondary danger-text" disabled={store.saving} onClick={() => {
              if (window.confirm("恢复全部外观默认值？皮肤、置顶、配色和字体都将恢复。")) {
                void store.resetAppearanceDefaults();
              }
            }}>恢复全部外观默认值</button>
          </div>
        </div>
        <div className="classic-palette-row">
          {paletteFields.map((field) => (
            <span key={field.key}><i style={{ background: CLASSIC_PALETTE[field.key] }} />{CLASSIC_PALETTE[field.key]}</span>
          ))}
        </div>
      </section>

      <section className="appearance-section theme-editor-section">
        <div className="appearance-section-heading">
          <div><h2>自定义配色与字体</h2><p>先在下方预览，确认后再应用到所有窗口。</p></div>
        </div>
        <div className="theme-editor-layout">
          <div className="theme-controls">
            <div className="palette-input-grid">
              {paletteFields.map((field) => {
                const normalized = normalizeHexColor(draftPalette[field.key]);
                return (
                  <label className={`color-field ${normalized ? "" : "invalid"}`} key={field.key}>
                    <span><strong>{field.label}</strong><small>{field.description}</small></span>
                    <span className="color-input-row">
                      <input
                        type="color"
                        aria-label={`${field.label}颜色选择器`}
                        value={normalized ?? "#000000"}
                        onChange={(event) => updatePaletteField(field.key, event.target.value.toUpperCase())}
                      />
                      <input
                        type="text"
                        aria-label={`${field.label}十六进制值`}
                        value={draftPalette[field.key]}
                        onChange={(event) => updatePaletteField(field.key, event.target.value)}
                        onBlur={() => normalizePaletteField(field.key)}
                        spellCheck={false}
                      />
                    </span>
                  </label>
                );
              })}
            </div>

            <div className="typography-controls">
              <label>
                <span><strong>基础字体大小</strong><small>适用于聊天、设置、历史和状态文字。</small></span>
                <span className="font-size-row">
                  <input
                    type="range"
                    min={MIN_FONT_SIZE_PX}
                    max={MAX_FONT_SIZE_PX}
                    step="1"
                    value={normalizeFontSize(draftTypography.baseFontSizePx)}
                    onChange={(event) => setDraftTypography((current) => ({ ...current, baseFontSizePx: Number(event.target.value) }))}
                  />
                  <input
                    type="number"
                    min={MIN_FONT_SIZE_PX}
                    max={MAX_FONT_SIZE_PX}
                    step="1"
                    value={draftTypography.baseFontSizePx}
                    onChange={(event) => setDraftTypography((current) => ({
                      ...current,
                      baseFontSizePx: event.target.value === "" ? DEFAULT_TYPOGRAPHY.baseFontSizePx : Number(event.target.value)
                    }))}
                    onBlur={() => setDraftTypography((current) => ({ ...current, baseFontSizePx: normalizeFontSize(current.baseFontSizePx) }))}
                  />
                  <span>px</span>
                </span>
              </label>
              <label className={normalizedFontColor ? "" : "invalid"}>
                <span><strong>字体颜色</strong><small>错误、警告和危险操作仍保留语义颜色。</small></span>
                <span className="color-input-row">
                  <input
                    type="color"
                    aria-label="字体颜色选择器"
                    value={normalizedFontColor ?? "#000000"}
                    onChange={(event) => setDraftTypography((current) => ({ ...current, fontColor: event.target.value.toUpperCase() }))}
                  />
                  <input
                    type="text"
                    aria-label="字体颜色十六进制值"
                    value={draftTypography.fontColor}
                    onChange={(event) => setDraftTypography((current) => ({ ...current, fontColor: event.target.value }))}
                    onBlur={() => {
                      const color = normalizeHexColor(draftTypography.fontColor);
                      if (color) setDraftTypography((current) => ({ ...current, fontColor: color }));
                    }}
                    spellCheck={false}
                  />
                  <button
                    type="button"
                    className="text-action"
                    onClick={() => setDraftTypography((current) => ({ ...current, fontColor: DEFAULT_TYPOGRAPHY.fontColor }))}
                  >恢复推荐颜色</button>
                </span>
              </label>
            </div>

            {contrast !== null && contrast < 4.5 ? (
              <p className={`contrast-message ${contrastBlocked ? "error" : "warning"}`}>
                {contrastBlocked
                  ? "字体颜色与主背景过于接近，必须调整后才能保存。"
                  : `当前文字对比度为 ${contrast.toFixed(2)}，可保存，但建议提高到 4.5 以上。`}
              </p>
            ) : null}
            {localError ? <p className="contrast-message error">{localError}</p> : null}

            <div className="theme-save-actions">
              <button
                className="button-primary"
                disabled={store.saving || !hasDraftChanges || !normalizedPalette || !normalizedFontColor || contrastBlocked}
                onClick={() => void saveDraft()}
              ><Save size={15} />应用并保存</button>
              <button className="button-secondary" disabled={store.saving || !hasDraftChanges} onClick={cancelDraft}>
                <X size={15} />取消修改
              </button>
            </div>
          </div>

          <div className="theme-preview" style={palettePreviewStyle(draftPalette, draftTypography)}>
            <div className="theme-preview-header"><strong>桌面智能体</strong><span>预览</span></div>
            <div className="theme-preview-body">
              <p className="preview-copy"><strong>标题文字</strong><span>普通文字与小号状态文字</span></p>
              <div className="preview-message assistant">这是 AI 消息预览。</div>
              <div className="preview-message user">这是用户消息预览。</div>
              <div className="preview-buttons"><button>主要按钮</button><button>次要按钮</button></div>
            </div>
          </div>
        </div>
      </section>

      <section className="appearance-section">
        <div className="appearance-section-heading split-heading">
          <div><h2>最近使用的配色</h2><p>最多保存五套自定义四色组合，最新使用的排在最前。</p></div>
          {store.paletteHistory.length ? (
            <button className="button-secondary danger-text" disabled={store.saving} onClick={() => {
              if (window.confirm("清空全部自定义配色历史？")) void store.clearPaletteHistory();
            }}><Trash2 size={15} />清空历史</button>
          ) : null}
        </div>
        {store.paletteHistory.length ? (
          <div className="palette-history-list">
            {store.paletteHistory.map((item, index) => (
              <div className="palette-history-row" key={item.id}>
                <div><strong>最近配色 {index + 1}</strong><small>最后使用：{new Date(item.lastUsedAt).toLocaleString("zh-CN")}</small></div>
                <div className="history-swatches" aria-label={Object.values(item.palette).join("、")}>
                  {paletteFields.map((field) => <i key={field.key} title={item.palette[field.key]} style={{ background: item.palette[field.key] }} />)}
                </div>
                <button className="button-secondary" disabled={store.saving} onClick={() => void store.applyHistoryPalette(item.id)}>应用</button>
                <button className="icon-history-delete" title="删除这套配色" disabled={store.saving} onClick={() => void store.deleteHistoryPalette(item.id)}><Trash2 size={15} /></button>
              </div>
            ))}
          </div>
        ) : <p className="empty-palette-history">尚未保存自定义配色。</p>}
      </section>

      <p className={`appearance-save-status ${store.error ? "error" : ""}`} role="status" aria-live="polite">
        {store.saving
          ? "正在保存……"
          : store.error
            ? store.error
            : store.lastSavedAt
              ? "已保存到本机"
              : "设置保存在本机，应用重启后会自动恢复。"}
      </p>
    </div>
  );
}
