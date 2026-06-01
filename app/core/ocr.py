from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image


_OCR_READER: Any | None = None
_OCR_ERROR: str | None = None


def load_easyocr(languages: list[str]) -> tuple[Any | None, str | None]:
    global _OCR_READER, _OCR_ERROR
    if _OCR_READER is not None:
        return _OCR_READER, None
    if _OCR_ERROR is not None:
        return None, _OCR_ERROR

    try:
        import easyocr
    except Exception as exc:
        _OCR_ERROR = f"easyocr_missing: {exc}"
        return None, _OCR_ERROR

    try:
        _OCR_READER = easyocr.Reader(languages, gpu=False)
    except Exception as exc:
        _OCR_ERROR = f"easyocr_init_failed: {exc}"
        return None, _OCR_ERROR

    return _OCR_READER, None


def ocr_image(path: Path, reader: Any) -> str:
    import numpy as np

    with Image.open(path) as image:
        result = reader.readtext(np.array(image), detail=0)
    return "\n".join([text for text in result if text]).strip()


def ocr_pdf(path: Path, reader: Any) -> str:
    import fitz

    chunks: list[str] = []
    with fitz.open(path) as document:
        for page in document:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            import numpy as np

            result = reader.readtext(np.array(image), detail=0)
            text = "\n".join([item for item in result if item]).strip()
            if text:
                chunks.append(text)
    return "\n".join(chunks)
