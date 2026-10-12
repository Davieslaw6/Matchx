"""Image validation and conservative OCR candidate extraction; no automatic market writes."""
from io import BytesIO
import re
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
import pytesseract

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
_ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
_ODDS_NUMBER = re.compile(r"(?<![A-Za-z0-9])([1-9][0-9]?(?:[.,][0-9]{1,3})?)(?![A-Za-z0-9])")
_MATCH_LINE = re.compile(r"^(.{2,50}?)\s+(?:vs?\.?|v)\s+(.{2,50})$", re.IGNORECASE)
_ODDS_CONTEXT = re.compile(r"odds?|home|draw|away|over|under|1x2|price|market|bookmaker|total", re.IGNORECASE)

class ImageValidationError(ValueError):
    pass

def validate_image(data: bytes, content_type: str) -> tuple[str, int, int]:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ImageValidationError("Image is empty or exceeds the 5 MiB limit.")
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageValidationError("File is not a valid supported image.") from exc
    expected_type = _ALLOWED_FORMATS.get(image_format)
    if expected_type is None or content_type.split(";", 1)[0].strip().lower() != expected_type:
        raise ImageValidationError("Content type does not match a supported PNG, JPEG or WEBP image.")
    if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
        raise ImageValidationError("Image dimensions exceed the 20 megapixel safety limit.")
    return image_format, width, height

def extract_ocr_text(data: bytes) -> str:
    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        return pytesseract.image_to_string(image, config="--psm 6", timeout=12).strip()

def extract_candidates(ocr_text: str) -> dict[str, Any]:
    odds_candidates: list[dict[str, Any]] = []
    match_candidates: list[dict[str, str]] = []
    for line_number, raw_line in enumerate(ocr_text.splitlines(), start=1):
        line = " ".join(raw_line.split())
        if not line:
            continue
        match = _MATCH_LINE.match(line)
        if match:
            match_candidates.append({"line": line, "home_candidate": match.group(1).strip(),
                                     "away_candidate": match.group(2).strip()})
        if _ODDS_CONTEXT.search(line):
            values: list[float] = []
            for token in _ODDS_NUMBER.findall(line):
                try:
                    value = float(token.replace(",", "."))
                except ValueError:
                    continue
                if 1.01 <= value <= 100 and value not in values:
                    values.append(value)
            if values:
                odds_candidates.append({"line_number": line_number, "line": line,
                                        "numeric_candidates": values,
                                        "status": "unverified_ocr_candidate"})
    return {"match_candidates": match_candidates, "odds_candidates": odds_candidates,
            "requires_manual_review": True,
            "limitations": ["OCR text and extracted numbers may be wrong.",
                            "No fixture, market, outcome or bookmaker is inferred automatically.",
                            "Review does not create odds, tickets or wagers."]}
