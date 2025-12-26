"""
OCR extraction for Captain Trading chart images.

Captain messages frequently include entry/SL/TP levels only in the attached image.
This module extracts those numeric levels using OCR and simple heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import io
import re

from PIL import Image, ImageEnhance, ImageOps
import pytesseract


@dataclass(frozen=True)
class TradeLevels:
    entry: Decimal
    stop_loss: Decimal
    take_profits: list[Decimal]
    raw_ocr_text: str


_NUM = r"(?P<num>\d+(?:\.\d+)?)"


def extract_trade_levels_from_image_bytes(image_bytes: bytes) -> TradeLevels | None:
    """Extract entry/SL/TP levels from a Captain Trading chart image."""
    entry = _extract_entry_from_region(image_bytes)
    stop_loss = _extract_stop_loss_from_region(image_bytes)
    if entry is None or stop_loss is None:
        return None

    ocr_text = _ocr_text_for_take_profit_labels(image_bytes)
    normalized = _normalize_ocr_text(ocr_text)
    take_profits = _merge_take_profits(
        _extract_take_profits(normalized, entry=entry),
        _extract_take_profits_from_region(image_bytes, entry=entry),
    )

    if not take_profits:
        return None

    return TradeLevels(
        entry=entry,
        stop_loss=stop_loss,
        take_profits=take_profits,
        raw_ocr_text=ocr_text,
    )


def _ocr_text_for_take_profit_labels(image_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    right = _preprocess_for_text_ocr(image)
    config = "--psm 6 -c preserve_interword_spaces=1"
    return pytesseract.image_to_string(right, config=config)


_REGION_TOP_RIGHT = ("top_right", 0.60, 0.00, 1.00, 0.25)
_REGION_ENTRY_RIGHT = ("entry_right", 0.60, 0.20, 1.00, 0.55)
_REGION_BOTTOM_RIGHT = ("bottom_right", 0.60, 0.72, 1.00, 1.00)


def _preprocess_for_text_ocr(image: Image.Image) -> Image.Image:
    # Captain labels are usually on the right side; crop to reduce noise.
    width, height = image.size
    crop_left = int(width * 0.55)
    image = image.crop((crop_left, 0, width, height))

    image = ImageOps.grayscale(image)
    image = image.resize((image.size[0] * 2, image.size[1] * 2), Image.Resampling.LANCZOS)

    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = ImageEnhance.Sharpness(image).enhance(2.0)

    # Binarize to make the label text pop.
    image = image.point(lambda p: 255 if p > 160 else 0)
    return image


def _normalize_ocr_text(text: str) -> str:
    upper = text.upper()

    # Common OCR confusions in numeric contexts.
    upper = upper.replace("O", "0")
    upper = upper.replace("S TOP", "STOP")
    upper = upper.replace("TP:", "TP ")
    upper = upper.replace("TP1", "TP 1")
    upper = upper.replace("TP2", "TP 2")
    upper = upper.replace("TP3", "TP 3")

    return upper


def _extract_named_level(text: str, names: list[str]) -> Decimal | None:
    for name in names:
        pattern = re.compile(rf"{re.escape(name)}\s*[:：]?\s*{_NUM}")
        match = pattern.search(text)
        if not match:
            continue
        parsed = _parse_decimal(match.group("num"))
        if parsed is not None:
            return parsed
    return None


def _extract_take_profits(text: str, *, entry: Decimal | None) -> list[Decimal]:
    pattern = re.compile(rf"\bTP\s*\d+\s*[:：\.\-]?\s*{_NUM}")
    matches = [m.group("num") for m in pattern.finditer(text)]
    levels: list[Decimal] = []
    for raw in matches:
        parsed = _parse_decimal(raw, reference=entry)
        if parsed is not None:
            levels.append(parsed)

    # Preserve order but remove duplicates.
    unique: list[Decimal] = []
    for level in levels:
        if level not in unique:
            unique.append(level)
    return unique


def _parse_decimal(value: str, *, reference: Decimal | None = None) -> Decimal | None:
    cleaned = value.strip()
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        return None

    if reference is None:
        return parsed

    # OCR sometimes prefixes an extra digit (e.g., "24430.57" instead of "4430.57").
    if parsed > reference * 2:
        without_leading = re.sub(r"^\d", "", cleaned)
        try:
            repaired = Decimal(without_leading)
        except InvalidOperation:
            return parsed
        if repaired < reference * 2:
            return repaired

    return parsed


def _ocr_numeric_region(
    image: Image.Image,
    region: tuple[str, float, float, float, float],
    *,
    scale: int,
) -> str:
    _, x0, y0, x1, y1 = region
    width, height = image.size
    box = (int(width * x0), int(height * y0), int(width * x1), int(height * y1))
    cropped = image.crop(box)
    cropped = ImageOps.grayscale(cropped)
    cropped = cropped.resize(
        (cropped.size[0] * scale, cropped.size[1] * scale),
        Image.Resampling.LANCZOS,
    )
    cropped = ImageEnhance.Contrast(cropped).enhance(2.5)
    cropped = ImageEnhance.Sharpness(cropped).enhance(2.5)
    config = "--psm 6 -c tessedit_char_whitelist=0123456789."
    return pytesseract.image_to_string(cropped, config=config)


def _extract_stop_loss_from_region(image_bytes: bytes) -> Decimal | None:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    text = _ocr_numeric_region(image, _REGION_TOP_RIGHT, scale=3)
    return _select_best_numeric_candidate(text)


def _extract_entry_from_region(image_bytes: bytes) -> Decimal | None:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    text = _ocr_numeric_region(image, _REGION_ENTRY_RIGHT, scale=3)
    return _select_best_numeric_candidate(text)


def _select_best_numeric_candidate(text: str) -> Decimal | None:
    matches = re.findall(_NUM, text)
    if not matches:
        return None

    candidates: list[tuple[int, int, Decimal]] = []
    for raw in matches:
        parsed = _parse_decimal(raw)
        if parsed is None:
            continue

        digits = len(raw.replace(".", ""))
        decimal_places = 0
        if "." in raw:
            decimal_places = len(raw.split(".", 1)[1])

        # Prefer values with decimals (prices) and with more digits (less noise).
        score = 0
        if decimal_places > 0:
            score += 10
        if decimal_places == 2:
            score += 5
        score += digits

        candidates.append((score, digits, parsed))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][2]


def _extract_take_profits_from_region(image_bytes: bytes, *, entry: Decimal) -> list[Decimal]:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    text = _ocr_numeric_region(image, _REGION_BOTTOM_RIGHT, scale=3)
    matches = re.findall(_NUM, text)
    levels: list[Decimal] = []
    for raw in matches:
        parsed = _parse_decimal(raw, reference=entry)
        if parsed is not None:
            levels.append(parsed)
    return levels


def _merge_take_profits(existing: list[Decimal], additional: list[Decimal]) -> list[Decimal]:
    merged = list(existing)
    for level in additional:
        if level not in merged:
            merged.append(level)
    return merged
