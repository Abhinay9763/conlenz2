from __future__ import annotations

import re
import zipfile
from pathlib import Path

from PIL import Image

from app.core.ocr import load_easyocr, ocr_image, ocr_pdf


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
OOXML_EXTENSIONS = {".docx", ".pptx", ".xlsx"}


class ExtractResult:
    def __init__(
        self,
        text: str,
        *,
        source: str,
        image_width: int | None = None,
        image_height: int | None = None,
        image_dpi: tuple[float, float] | None = None,
        ocr_used: bool = False,
    ) -> None:
        self.text = text
        self.source = source
        self.image_width = image_width
        self.image_height = image_height
        self.image_dpi = image_dpi
        self.ocr_used = ocr_used


def extract_text(
    path: Path,
    *,
    ocr_enabled: bool,
    ocr_languages: list[str],
    pdf_readability_threshold: int,
    max_text_chars: int,
) -> ExtractResult:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return _extract_image(path, ocr_enabled, ocr_languages)
    if suffix == ".pdf":
        return _extract_pdf(path, ocr_enabled, ocr_languages, pdf_readability_threshold)
    if suffix in OOXML_EXTENSIONS:
        return _extract_ooxml(path, max_text_chars)

    return _extract_text_file(path, max_text_chars)


def _extract_image(path: Path, ocr_enabled: bool, ocr_languages: list[str]) -> ExtractResult:
    with Image.open(path) as image:
        width, height = image.size
        dpi = image.info.get("dpi")

    if not ocr_enabled:
        return ExtractResult("", source="image", image_width=width, image_height=height, image_dpi=dpi, ocr_used=False)

    reader, error = load_easyocr(ocr_languages)
    if reader is None:
        return ExtractResult("", source=f"image:{error}", image_width=width, image_height=height, image_dpi=dpi, ocr_used=False)

    text = ocr_image(path, reader)
    return ExtractResult(text, source="image:ocr", image_width=width, image_height=height, image_dpi=dpi, ocr_used=True)


def _extract_pdf(
    path: Path,
    ocr_enabled: bool,
    ocr_languages: list[str],
    pdf_readability_threshold: int,
) -> ExtractResult:
    import fitz

    chunks: list[str] = []
    with fitz.open(path) as document:
        for page in document:
            chunks.append((page.get_text("text") or "").strip())
    text = "\n".join([chunk for chunk in chunks if chunk])
    if text and len(text) >= pdf_readability_threshold:
        return ExtractResult(text, source="pdf:text", ocr_used=False)

    if not ocr_enabled:
        return ExtractResult(text, source="pdf:text", ocr_used=False)

    reader, error = load_easyocr(ocr_languages)
    if reader is None:
        return ExtractResult(text, source=f"pdf:{error}", ocr_used=False)

    ocr_text = ocr_pdf(path, reader)
    combined = "\n".join([text, ocr_text]).strip()
    return ExtractResult(combined, source="pdf:ocr", ocr_used=True)


def _extract_text_file(path: Path, max_text_chars: int) -> ExtractResult:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ExtractResult("", source="text:error", ocr_used=False)
    if len(text) > max_text_chars:
        text = text[:max_text_chars]
    return ExtractResult(text, source="text", ocr_used=False)


def _extract_ooxml(path: Path, max_text_chars: int) -> ExtractResult:
    texts: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                if not re.search(r"(document|slide|sharedStrings)\.xml$", name, re.IGNORECASE):
                    continue
                raw = archive.read(name)
                decoded = raw.decode("utf-8", errors="ignore")
                decoded = re.sub(r"<[^>]+>", " ", decoded)
                texts.append(decoded)
    except Exception:
        return ExtractResult("", source="ooxml:error", ocr_used=False)

    text = "\n".join(texts)
    text = " ".join(text.split())
    if len(text) > max_text_chars:
        text = text[:max_text_chars]
    return ExtractResult(text, source="ooxml", ocr_used=False)
