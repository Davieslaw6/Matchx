from io import BytesIO

import pytest
from PIL import Image

from app.imports.screenshot_ocr import (
    MAX_IMAGE_BYTES, ImageValidationError, extract_candidates, validate_image,
)

def png_bytes(width=20, height=20):
    stream = BytesIO()
    Image.new("RGB", (width, height), "white").save(stream, format="PNG")
    return stream.getvalue()

def test_validates_real_image_bytes_and_matching_mime_type():
    data = png_bytes()
    image_format, width, height = validate_image(data, "image/png")
    assert (image_format, width, height) == ("PNG", 20, 20)

def test_rejects_mime_mismatch_and_oversized_image():
    with pytest.raises(ImageValidationError, match="does not match"):
        validate_image(png_bytes(), "image/jpeg")
    with pytest.raises(ImageValidationError, match="5 MiB"):
        validate_image(b"x" * (MAX_IMAGE_BYTES + 1), "image/png")

def test_ocr_candidates_are_explicitly_unverified_and_do_not_assign_outcomes():
    parsed = extract_candidates("Arsenal vs Forest\nHome 1.85 Draw 3.5 Away 4.1")
    assert parsed["match_candidates"][0]["home_candidate"] == "Arsenal"
    assert parsed["match_candidates"][0]["away_candidate"] == "Forest"
    assert parsed["odds_candidates"][0]["numeric_candidates"] == [1.85, 3.5, 4.1]
    assert parsed["odds_candidates"][0]["status"] == "unverified_ocr_candidate"
    assert parsed["requires_manual_review"] is True
