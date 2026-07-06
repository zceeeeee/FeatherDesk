"""Local WPS Writer / Word automation helpers."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

WPS_PROG_IDS = (
    "KWPS.Application",
    "KWPS.Application.9",
    "WPS.Application",
    "Word.Application",
)

DOCX_FORMAT = 16
PDF_FORMAT = 17

WORD_COLOR_VALUES = {
    "black": 0,
    "blue": 16711680,
    "gray": 8421504,
    "grey": 8421504,
    "green": 32768,
    "red": 255,
    "white": 16777215,
    "yellow": 65535,
    "黑色": 0,
    "蓝色": 16711680,
    "灰色": 8421504,
    "绿色": 32768,
    "红色": 255,
    "白色": 16777215,
    "黄色": 65535,
}

KNOWN_FONT_NAMES = (
    "Microsoft YaHei",
    "Times New Roman",
    "Arial",
    "SimSun",
    "宋体",
    "黑体",
    "楷体",
    "楷体_GB2312",
    "仿宋",
    "微软雅黑",
)

FONT_STYLE_TOKENS = (
    "italic",
    "斜体",
    "红色",
    "蓝色",
    "绿色",
    "黑色",
    "白色",
    "黄色",
    "灰色",
    "字体",
    "font",
)


def _clean_text(value: str | None) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _safe_filename(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    name = re.sub(r"\s+", "_", name)
    return (name[:60] or "wps_article").strip(" ._")


def _safe_file_stem(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"\.(?:docx?|pdf)$", "", text, flags=re.IGNORECASE)
    return _safe_filename(text)


def _normalize_windows_path(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if re.match(r"^[A-Za-z]:[^\\/]", text):
        return f"{text[:2]}\\{text[2:]}"
    return text


def _int_or_default(value: int | str | None, default: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _normalize_font_name(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    for font in KNOWN_FONT_NAMES:
        if font.lower() in lowered:
            return font
    for token in FONT_STYLE_TOKENS:
        text = re.sub(re.escape(token), "", text, flags=re.IGNORECASE)
    text = re.sub(r"\d+\s*号?", "", text).strip()
    return text or None


def _is_italic(value: bool | str | None) -> bool:
    if isinstance(value, bool):
        return value
    text = _clean_text(value).lower()
    return text in {"1", "true", "yes", "on"} or "italic" in text or "斜体" in text


def _font_color_value(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = _clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    for name, color in WORD_COLOR_VALUES.items():
        if name.lower() in lowered:
            return color
    hex_match = re.search(r"#?([0-9a-fA-F]{6})", text)
    if hex_match:
        rgb = int(hex_match.group(1), 16)
        red = (rgb >> 16) & 255
        green = (rgb >> 8) & 255
        blue = rgb & 255
        return red + (green << 8) + (blue << 16)
    try:
        return int(text)
    except ValueError:
        return None


def _paragraphs(body: str) -> list[str]:
    lines = []
    for line in _clean_text(body).split("\n"):
        text = line.strip()
        if text:
            lines.append(text)
    return lines


def _resolve_paths(
    title: str,
    output_dir: str | None = None,
    docx_path: str | None = None,
    pdf_path: str | None = None,
    file_name: str | None = None,
) -> tuple[Path, Path]:
    normalized_output_dir = _normalize_windows_path(output_dir)
    normalized_docx_path = _normalize_windows_path(docx_path)
    normalized_pdf_path = _normalize_windows_path(pdf_path)
    base_dir = (
        Path(normalized_output_dir).expanduser()
        if normalized_output_dir
        else Path.home() / "Documents" / "agentic-playwright-mcp" / "wps_exports"
    )
    base_dir.mkdir(parents=True, exist_ok=True)

    file_stem = _safe_file_stem(file_name or "")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = file_stem or f"{_safe_filename(title)}_{stamp}"
    docx = (
        Path(normalized_docx_path).expanduser()
        if normalized_docx_path
        else Path(normalized_pdf_path).expanduser().with_suffix(".docx")
        if normalized_pdf_path
        else base_dir / f"{base_name}.docx"
    )
    pdf = (
        Path(normalized_pdf_path).expanduser()
        if normalized_pdf_path
        else base_dir / f"{base_name}.pdf"
    )
    docx.parent.mkdir(parents=True, exist_ok=True)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    return docx.resolve(strict=False), pdf.resolve(strict=False)


def _dispatch_writer(
    dispatch_fn: Callable[[str], Any] | None = None,
) -> tuple[Any, str]:
    dispatchers: list[Callable[[str], Any]]
    if dispatch_fn is None:
        try:
            import win32com.client  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - depends on Windows env
            raise RuntimeError(
                "WPS desktop export requires pywin32 on Windows."
            ) from exc
        dispatchers = [
            getattr(win32com.client, "DispatchEx", win32com.client.Dispatch),
            win32com.client.Dispatch,
        ]
    else:
        dispatchers = [dispatch_fn]

    errors: list[str] = []
    for prog_id in WPS_PROG_IDS:
        for current_dispatch in dispatchers:
            try:
                return current_dispatch(prog_id), prog_id
            except Exception as exc:
                errors.append(f"{prog_id}: {type(exc).__name__}: {exc}")

    detail = "; ".join(errors)
    raise RuntimeError(f"Unable to start WPS Writer or Word via COM. Tried {detail}")


def _set_attr(obj: Any, name: str, value: Any) -> None:
    try:
        setattr(obj, name, value)
    except Exception:
        pass


def _call(obj: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    method = getattr(obj, name, None)
    if method is None:
        raise AttributeError(name)
    return method(*args, **kwargs)


def _set_font(
    selection: Any,
    font_name: str,
    size: int,
    bold: bool,
    italic: bool = False,
    color: int | None = None,
) -> None:
    font = getattr(selection, "Font", None)
    if font is None:
        return
    _set_attr(font, "Name", font_name)
    _set_attr(font, "Size", size)
    _set_attr(font, "Bold", -1 if bold else 0)
    _set_attr(font, "Italic", -1 if italic else 0)
    if color is not None:
        _set_attr(font, "Color", color)


def _set_paragraph(selection: Any, alignment: int, first_line_indent: int = 0) -> None:
    paragraph = getattr(selection, "ParagraphFormat", None)
    if paragraph is None:
        return
    _set_attr(paragraph, "Alignment", alignment)
    _set_attr(paragraph, "FirstLineIndent", first_line_indent)
    _set_attr(paragraph, "LineSpacingRule", 5)


def _apply_numbering(selection: Any) -> bool:
    try:
        list_format = selection.Range.ListFormat
        list_format.ApplyNumberDefault()
        return True
    except Exception:
        return False


def _remove_numbering(selection: Any) -> None:
    try:
        selection.Range.ListFormat.RemoveNumbers()
    except Exception:
        pass


def _active_document(app: Any, fallback: Any) -> Any:
    try:
        active = app.ActiveDocument
        if active is not None:
            return active
    except Exception:
        pass
    return fallback


def _type_paragraph(selection: Any, text: str, numbered: bool = False) -> None:
    applied_numbering = _apply_numbering(selection) if numbered else False
    _call(selection, "TypeText", text)
    _call(selection, "TypeParagraph")
    if applied_numbering:
        _remove_numbering(selection)


def _insert_image(selection: Any, image_path: str | None) -> str | None:
    normalized = _normalize_windows_path(image_path)
    if not normalized:
        return None
    path = Path(normalized).expanduser().resolve(strict=False)
    if not path.exists():
        raise FileNotFoundError(f"WPS image path does not exist: {path}")

    _call(selection, "TypeParagraph")
    containers = [
        getattr(selection, "InlineShapes", None),
        getattr(getattr(selection, "Range", None), "InlineShapes", None),
    ]
    for inline_shapes in containers:
        if inline_shapes is None:
            continue
        add_picture = getattr(inline_shapes, "AddPicture", None)
        if add_picture is None:
            continue
        try:
            add_picture(str(path), False, True)
        except TypeError:
            add_picture(str(path))
        _call(selection, "TypeParagraph")
        return str(path)
    raise RuntimeError("WPS Writer selection does not support InlineShapes.AddPicture")


def _save_docx(doc: Any, docx_path: Path) -> None:
    try:
        doc.SaveAs2(str(docx_path), FileFormat=DOCX_FORMAT)
        return
    except TypeError:
        pass
    except Exception:
        try:
            doc.SaveAs2(str(docx_path))
            return
        except Exception:
            pass

    try:
        doc.SaveAs(str(docx_path), FileFormat=DOCX_FORMAT)
    except TypeError:
        doc.SaveAs(str(docx_path))


def _export_pdf(doc: Any, pdf_path: Path) -> None:
    try:
        doc.ExportAsFixedFormat(str(pdf_path), PDF_FORMAT)
        return
    except Exception:
        pass

    try:
        doc.SaveAs2(str(pdf_path), FileFormat=PDF_FORMAT)
    except TypeError:
        doc.SaveAs2(str(pdf_path), PDF_FORMAT)


def export_article_to_pdf(
    title: str,
    body: str,
    output_dir: str | None = None,
    docx_path: str | None = None,
    pdf_path: str | None = None,
    file_name: str | None = None,
    keep_open: bool = True,
    visible: bool = True,
    font_name: str | None = None,
    font_size: int | str | None = None,
    font_color: int | str | None = None,
    italic: bool | str | None = None,
    image_path: str | None = None,
    dispatch_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Create a WPS/Word document, apply basic article formatting, and export PDF."""

    title_text = _clean_text(title) or "未命名文档"
    body_text = _clean_text(body)
    if not body_text:
        raise ValueError("WPS export requires article body content")
    body_font = _normalize_font_name(font_name) or "Microsoft YaHei"
    body_size = _int_or_default(font_size, 12)
    title_size = max(body_size + 6, 18)
    font_color_value = _font_color_value(font_color)
    italic_enabled = _is_italic(italic)

    docx, pdf = _resolve_paths(title_text, output_dir, docx_path, pdf_path, file_name)
    app, provider = _dispatch_writer(dispatch_fn)
    _set_attr(app, "Visible", bool(visible))
    _set_attr(app, "DisplayAlerts", 0)

    doc = _active_document(app, app.Documents.Add())
    selection = app.Selection

    _set_font(
        selection,
        body_font,
        title_size,
        True,
        italic=italic_enabled,
        color=font_color_value,
    )
    _set_paragraph(selection, alignment=1)
    _type_paragraph(selection, title_text)

    _set_font(
        selection,
        body_font,
        body_size,
        False,
        italic=italic_enabled,
        color=font_color_value,
    )
    _set_paragraph(selection, alignment=0, first_line_indent=24)

    paragraph_count = 0
    list_item_pattern = re.compile(r"^\s*(?:\d+[.)、]|[-*•])\s*(.+)$")
    for paragraph in _paragraphs(body_text):
        match = list_item_pattern.match(paragraph)
        if match:
            _type_paragraph(selection, match.group(1).strip(), numbered=True)
        else:
            _type_paragraph(selection, paragraph)
        paragraph_count += 1

    inserted_image_path = _insert_image(selection, image_path)

    _save_docx(doc, docx)
    _export_pdf(doc, pdf)

    if not keep_open:
        try:
            doc.Close(False)
        finally:
            try:
                app.Quit()
            except Exception:
                pass

    return {
        "success": True,
        "provider": provider,
        "title": title_text,
        "docx_path": str(docx),
        "pdf_path": str(pdf),
        "paragraph_count": paragraph_count,
        "font_name": body_font,
        "font_size": body_size,
        "font_color": font_color_value,
        "italic": italic_enabled,
        "image_path": inserted_image_path,
        "keep_open": keep_open,
    }
