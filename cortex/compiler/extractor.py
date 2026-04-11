from __future__ import annotations

from pathlib import Path


def detect_source_type(path: Path) -> str:
    """Detect the type of a raw source file based on its extension."""
    ext = path.suffix.lower()
    type_map = {
        ".pdf": "pdf",
        ".md": "markdown",
        ".markdown": "markdown",
        ".url": "url",
    }
    return type_map.get(ext, "text")


async def extract_text_from_pdf(path: Path) -> str:
    """Extract text from a PDF file using pdftotext."""
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "pdftotext", str(path), "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"pdftotext error: {stderr.decode()}")
    return stdout.decode()


async def extract_text_from_url(url: str) -> str:
    """Fetch a URL and return its text content."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text
