"""Source type detection and MarkItDown-based text extraction."""
from __future__ import annotations

from pathlib import Path

from markitdown import MarkItDown

from cortex.config import settings
from cortex.llm.backend import LLMBackend, create_backend


def make_markitdown(backend: LLMBackend | None = None) -> MarkItDown:
    """Build MarkItDown; attach a vision LLM for image captioning when the
    configured backend supports it (disabled/Bedrock backends attach none)."""
    if backend is None:
        backend = create_backend(settings)
    kwargs: dict = {"enable_plugins": False}
    if backend.enabled:
        kwargs.update(backend.markitdown_kwargs())
    return MarkItDown(**kwargs)


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
        ".jpg": "image",
        ".jpeg": "image",
        ".png": "image",
    }
    return type_map.get(ext, "text")


def extract_text(path: Path) -> str:
    """Extract text content from any supported file using MarkItDown."""
    result = make_markitdown().convert_local(str(path))
    return (result.text_content or "").strip()
