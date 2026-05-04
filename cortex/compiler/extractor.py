"""Source type detection and MarkItDown-based text extraction."""
from __future__ import annotations

from pathlib import Path

from markitdown import MarkItDown

_MARKITDOWN = MarkItDown(enable_plugins=False)


def detect_source_type(path: Path) -> str:
    """Detect the type of a raw source file based on its extension."""
    ext = path.suffix.lower()
    type_map = {
        ".pdf": "pdf",
        ".md": "markdown",
        ".markdown": "markdown",
        ".url": "url",
        ".docx": "docx",
        ".pptx": "pptx",
        ".xlsx": "xlsx",
        ".html": "html",
        ".htm": "html",
        ".csv": "csv",
        ".json": "json",
        ".xml": "xml",
    }
    return type_map.get(ext, "text")


def extract_text(path: Path) -> str:
    """Extract text content from any supported file using MarkItDown."""
    result = _MARKITDOWN.convert_local(str(path))
    return (result.text_content or "").strip()
