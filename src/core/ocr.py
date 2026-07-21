"""Windows OCR integration for Explore mode.

Provides lightweight text recognition as a fallback before the vision model.
Uses the Windows.Media.Ocr API via winrt — no API key, no network call,
no per-call cost.  Only works on Windows.

Coordinate contract:
- Input: Playwright ``page.screenshot()`` bytes (PNG, viewport crop).
- Output: coordinates normalized to viewport dimensions (0.0–1.0),
  matching the ``VisualTarget`` coordinate system used by VisionRouter.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from src.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OcrWord:
    """A single recognized word with normalized viewport coordinates."""

    text: str
    x: float = 0.0  # left edge, 0-1
    y: float = 0.0  # top edge, 0-1
    width: float = 0.0  # 0-1
    height: float = 0.0  # 0-1

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


@dataclass
class OcrResult:
    """Full OCR output for a screenshot."""

    words: list[OcrWord] = field(default_factory=list)
    raw_text: str = ""
    viewport_width: int = 0
    viewport_height: int = 0


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_ocr_module: OcrModule | None = None


def get_ocr_module(language: str = "zh-CN") -> OcrModule | None:
    """Return the process-wide OcrModule, or None if unavailable."""
    global _ocr_module
    if _ocr_module is None:
        try:
            _ocr_module = OcrModule(language=language)
        except Exception as exc:
            logger.warning("OCR module init failed: %s", exc)
            return None
    return _ocr_module


def reset_ocr_module() -> None:
    """Reset the process-wide OcrModule instance."""
    global _ocr_module
    _ocr_module = None


# ---------------------------------------------------------------------------
# Core implementation
# ---------------------------------------------------------------------------

# Platform guard — winrt is Windows-only.
_PLATFORM_SUPPORTED = sys.platform == "win32"


class OcrModule:
    """Windows OCR wrapper.

    Raises ``ImportError`` or ``RuntimeError`` on construction if the
    platform or language pack is unavailable.
    """

    def __init__(self, language: str = "zh-CN") -> None:
        if not _PLATFORM_SUPPORTED:
            raise RuntimeError("Windows OCR requires win32 platform")

        # Lazy imports so non-Windows environments never touch winrt.
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine

        lang_obj = Language(language)
        engine = OcrEngine.try_create_from_language(lang_obj)
        if engine is None:
            raise RuntimeError(
                f"Failed to create OCR engine for language '{language}'. "
                "Ensure the language pack is installed in Windows Settings."
            )
        self._engine = engine
        self._language = language
        logger.info("OCR module initialized (language=%s)", language)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def recognize(
        self,
        screenshot_bytes: bytes,
        viewport_width: int = 0,
        viewport_height: int = 0,
    ) -> OcrResult:
        """Recognize text in screenshot bytes.

        Args:
            screenshot_bytes: PNG bytes from ``page.screenshot()``.
            viewport_width: Viewport CSS width (for normalization).
            viewport_height: Viewport CSS height (for normalization).

        Returns:
            ``OcrResult`` with words and normalized coordinates.
        """
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

        # bytes → SoftwareBitmap
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream.get_output_stream_at(0))
        writer.write_bytes(screenshot_bytes)
        await writer.store_async()
        writer.detach_stream()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        actual_w = bitmap.pixel_width
        actual_h = bitmap.pixel_height

        # Use actual bitmap dimensions for normalization if caller didn't
        # provide viewport size (handles device_scale_factor automatically).
        norm_w = viewport_width if viewport_width > 0 else actual_w
        norm_h = viewport_height if viewport_height > 0 else actual_h

        # OCR
        ocr_result = await self._engine.recognize_async(bitmap)

        words: list[OcrWord] = []
        raw_parts: list[str] = []
        for line in ocr_result.lines:
            for word in line.words:
                rect = word.bounding_rect
                text = word.text.strip()
                if not text:
                    continue
                raw_parts.append(text)
                words.append(
                    OcrWord(
                        text=text,
                        x=max(0.0, rect.x / norm_w),
                        y=max(0.0, rect.y / norm_h),
                        width=min(1.0, rect.width / norm_w),
                        height=min(1.0, rect.height / norm_h),
                    )
                )

        logger.info("OCR recognized %d words", len(words))
        return OcrResult(
            words=words,
            raw_text=" ".join(raw_parts),
            viewport_width=actual_w,
            viewport_height=actual_h,
        )

    @staticmethod
    def find_text(
        ocr_result: OcrResult,
        keyword: str,
        *,
        exact: bool = False,
    ) -> list[OcrWord]:
        """Find words matching *keyword* (case-insensitive substring).

        Args:
            ocr_result: Output from ``recognize()``.
            keyword: Text to search for.
            exact: If True, require exact match; otherwise substring.

        Returns:
            List of matching ``OcrWord`` items.
        """
        needle = keyword.strip().lower()
        if not needle:
            return []
        results = []
        for word in ocr_result.words:
            text_lower = word.text.lower()
            if exact and text_lower == needle:
                results.append(word)
            elif not exact and needle in text_lower:
                results.append(word)
        return results
