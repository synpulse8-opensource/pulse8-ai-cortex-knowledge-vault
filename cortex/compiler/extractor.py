"""Source type detection and MarkItDown-based text extraction."""
from __future__ import annotations

from pathlib import Path

from markitdown import MarkItDown
from openai import OpenAI

from cortex.compiler.prompts import IMAGE_CAPTION_PROMPT
from cortex.config import settings


def make_markitdown() -> MarkItDown:
    """Build MarkItDown; attach a vision LLM for image captioning when configured."""
    kwargs: dict = {"enable_plugins": False}
    if settings.llm_api_key:
        kwargs["llm_client"] = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        kwargs["llm_model"] = settings.compiler_vision_model or settings.compiler_model
        kwargs["llm_prompt"] = IMAGE_CAPTION_PROMPT
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
