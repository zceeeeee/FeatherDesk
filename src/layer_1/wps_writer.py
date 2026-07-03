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


def _clean_text(value: str | None) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _safe_filename(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    name = re.sub(r"\s+", "_", name)
    return (name[:60] or "wps_article").strip(" ._")


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

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{_safe_filename(title)}_{stamp}"
    docx = (
        Path(normalized_docx_path).expanduser()
        if normalized_docx_path
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


def _set_font(selection: Any, font_name: str, size: int, bold: bool) -> None:
    font = getattr(selection, "Font", None)
    if font is None:
        return
    _set_attr(font, "Name", font_name)
    _set_attr(font, "Size", size)
    _set_attr(font, "Bold", -1 if bold else 0)


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
    keep_open: bool = True,
    visible: bool = True,
    font_name: str | None = None,
    font_size: int | str | None = None,
    dispatch_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Create a WPS/Word document, apply basic article formatting, and export PDF."""

    title_text = _clean_text(title) or "未命名文档"
    body_text = _clean_text(body)
    if not body_text:
        raise ValueError("WPS export requires article body content")
    body_font = _clean_text(font_name) or "Microsoft YaHei"
    body_size = _int_or_default(font_size, 12)
    title_size = max(body_size + 6, 18)

    docx, pdf = _resolve_paths(title_text, output_dir, docx_path, pdf_path)
    app, provider = _dispatch_writer(dispatch_fn)
    _set_attr(app, "Visible", bool(visible))
    _set_attr(app, "DisplayAlerts", 0)

    doc = _active_document(app, app.Documents.Add())
    selection = app.Selection

    _set_font(selection, body_font, title_size, True)
    _set_paragraph(selection, alignment=1)
    _type_paragraph(selection, title_text)

    _set_font(selection, body_font, body_size, False)
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
        "keep_open": keep_open,
    }
