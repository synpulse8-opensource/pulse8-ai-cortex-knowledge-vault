"""Knowledge compiler: MarkItDown conversion + LLM cross-referencing."""
from __future__ import annotations

import asyncio
import json
import re
import logging
from pathlib import Path
from typing import Any

from markitdown import MarkItDown
from openai import AsyncOpenAI

from cortex.compiler.prompts import COMPILE_SYSTEM_PROMPT, ENRICH_SYSTEM_PROMPT
from cortex.compiler.ingest_manifest import record_skipped_file
from cortex.config import settings
from cortex.vault.reader import read_note, scan_vault
from cortex.vault.writer import write_note
from cortex.vault.index import rebuild_index
from cortex.log.audit import log_operation

logger = logging.getLogger(__name__)

_compile_status: dict[str, Any] = {"running": False, "last_result": None}

def _slug_from_stem(stem: str) -> str:
    """Convert a filename stem to a kebab-case slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug or "untitled"


def _title_from_markdown(md_text: str, fallback: str) -> str:
    """Extract the first Markdown heading as the title, or use the fallback."""
    match = re.search(r"^#{1,6}\s+(.+)", md_text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return fallback.replace("-", " ").title()


class KnowledgeCompiler:
    """Converts raw sources to wiki Markdown via MarkItDown; uses LLM only for cross-referencing."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._md = MarkItDown(enable_plugins=False)
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key or "unused",
            base_url=settings.llm_base_url,
        )
        self.model = settings.compiler_model

    async def _chat(self, system: str, user_content: str) -> str:
        """Send a chat completion request and return the assistant's text."""
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=settings.compiler_max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        )
        return response.choices[0].message.content or ""

    async def enrich_article(self, md_content: str, title: str) -> dict:
        """Call LLM to add [[wikilinks]] and tags to a converted Markdown article."""
        index_context = self._build_index_context()
        try:
            text = await self._chat(
                ENRICH_SYSTEM_PROMPT,
                f"## Article: {title}\n\n{md_content}\n\n"
                f"## Existing Wiki Index\n\n{index_context}",
            )
            return self._parse_enrichment(text, md_content)
        except Exception:  # pylint: disable=broad-exception-caught
            return {"content": md_content, "tags": []}

    def _parse_enrichment(self, text: str, original: str) -> dict:
        """Parse the LLM enrichment response, falling back to original on failure."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            data = json.loads(cleaned)
            return {
                "content": data.get("content", original),
                "tags": data.get("tags", []),
            }
        except (json.JSONDecodeError, AttributeError):
            return {"content": original, "tags": []}

    async def ingest_source(
        self, source_path: Path, timeout: float = 3600.0, force: bool = False
    ) -> list[Path]:
        """Convert a raw source file to wiki Markdown, then enrich with LLM if available.

        Args:
            source_path: Path to the raw file to ingest.
            timeout: Max seconds for the full ingest (conversion + enrichment).
            force: If True, re-compile even if wiki article is up-to-date.
        """
        relative_source = str(source_path.relative_to(self.vault_path))
        file_size_mb = source_path.stat().st_size / (1024 * 1024)
        if file_size_mb > settings.compiler_max_file_size_mb:
            reason = (
                f"file too large ({file_size_mb:.1f} MB > "
                f"{settings.compiler_max_file_size_mb} MB limit)"
            )
            logger.warning("Skipping %s: %s", relative_source, reason)
            record_skipped_file(self.vault_path, source_path, reason)
            return []

        slug = _slug_from_stem(source_path.stem)
        wiki_path = self.vault_path / "wiki" / f"{slug}.md"
        if wiki_path.exists() and not force:
            if source_path.stat().st_mtime <= wiki_path.stat().st_mtime:
                logger.info("Skipping %s: wiki already up-to-date", relative_source)
                record_skipped_file(self.vault_path, source_path, "wiki already up-to-date")
                return [wiki_path]

        logger.info("Ingesting %s (%.1f MB)", relative_source, file_size_mb)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._md.convert_local, str(source_path)),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            reason = f"conversion timed out after {timeout:.0f}s"
            logger.warning("Skipping %s: %s", relative_source, reason)
            record_skipped_file(self.vault_path, source_path, reason)
            return []
        except Exception as exc:
            reason = f"conversion failed: {exc}"
            logger.warning("Skipping %s: %s", relative_source, reason)
            record_skipped_file(self.vault_path, source_path, reason)
            return []
        logger.info("Converted %s", relative_source)
        md_content = (result.text_content or "").strip()
        if not md_content:
            reason = "empty conversion result"
            logger.warning("Skipping %s: %s", relative_source, reason)
            record_skipped_file(self.vault_path, source_path, reason)
            return []

        title = _title_from_markdown(md_content, source_path.stem)

        enriched = {"content": md_content, "tags": []}
        if settings.llm_api_key:
            enriched = await self.enrich_article(md_content, title)
        logger.info("Enriched %s", relative_source)
        has_tags = bool(enriched["tags"])
        has_links = "[[" in enriched["content"]
        enrichment_ok = settings.llm_api_key and (has_tags or has_links)

        note_path = wiki_path

        frontmatter: dict = {
            "title": title,
            "source_path": relative_source,
            "enrichment_status": "complete" if enrichment_ok else "incomplete",
        }
        if enriched["tags"]:
            frontmatter["tags"] = enriched["tags"]

        write_note(
            path=note_path,
            vault_root=self.vault_path,
            content=enriched["content"],
            frontmatter=frontmatter,
            mode="upsert",
            authored_by="markitdown",
            model=self.model if settings.llm_api_key else None,
        )
        logger.info("Wrote note %s to %s", title, note_path)

        return [note_path]

    async def compile_cross_references(self, new_paths: list[Path]) -> None:
        """After new articles are created, identify cross-references and contradictions."""
        if not settings.llm_api_key:
            return
        new_articles = []
        for p in new_paths:
            note = read_note(p, self.vault_path)
            new_articles.append(
                f"### {note.title}\n"
                f"Path: {note.path}\n"
                f"Tags: {', '.join(note.tags)}\n\n"
                f"{note.content[:500]}"
            )

        index_context = self._build_index_context()

        text = await self._chat(
            COMPILE_SYSTEM_PROMPT,
            f"## New Articles\n\n{'---'.join(new_articles)}\n\n"
            f"## Existing Wiki Index\n\n{index_context}",
        )

        updates = self._parse_updates(text)
        await self._apply_updates(updates)

    def _build_index_context(self) -> str:
        """Build a summary of existing wiki articles for LLM context."""
        wiki_dir = self.vault_path / "wiki"
        if not wiki_dir.exists():
            return "No existing articles."
        lines = []
        for md_file in sorted(wiki_dir.rglob("*.md")):
            note = read_note(md_file, self.vault_path)
            tags = ", ".join(note.tags) if note.tags else "none"
            lines.append(f"- [{note.title}]({note.path}) — tags: {tags}")
        return "\n".join(lines) if lines else "No existing articles."

    def _parse_updates(self, text: str) -> list[dict]:
        """Parse cross-reference updates from LLM response."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return []

    async def _apply_updates(self, updates: list[dict]) -> None:
        """Apply cross-reference updates to existing articles."""
        for update in updates:
            path = self.vault_path / update["path"]
            if not path.exists():
                continue
            action = update.get("action", "")
            details = update.get("details", "")
            if action == "add_link":
                content = path.read_text()
                content += f"\n\nSee also: {details}\n"
                path.write_text(content)
            elif action == "add_contradiction":
                content = path.read_text()
                content += f"\n\n> [!contradiction]\n> {details}\n"
                path.write_text(content)


async def _run_compile(vault_path: Path, qmd_debounce) -> None:
    """Background compile task — processes all uncompiled raw sources."""
    try:
        existing_sources: set[str] = set()
        for note in scan_vault(vault_path):
            sp = note.frontmatter.get("source_path")
            if sp:
                existing_sources.add(sp)

        raw_dir = vault_path / "raw"
        if not raw_dir.exists():
            _compile_status["last_result"] = {"status": "no raw directory", "compiled": 0}
            return

        compiler = KnowledgeCompiler(vault_path)
        compiled_count = 0
        failed_count = 0
        all_created: list[str] = []

        for raw_file in sorted(raw_dir.iterdir()):
            if raw_file.is_dir():
                continue
            rel = str(raw_file.relative_to(vault_path))
            if rel not in existing_sources:
                try:
                    created = await compiler.ingest_source(raw_file)
                    if created:
                        compiled_count += 1
                        all_created.extend(str(p.relative_to(vault_path)) for p in created)
                    else:
                        failed_count += 1
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.exception("Failed to compile %s", rel)
                    record_skipped_file(vault_path, raw_file, f"compile failed: {exc}")
                    failed_count += 1

        await rebuild_index(vault_path)
        qmd_debounce.schedule()
        await log_operation(
            vault_path, "api", "vault:compile", f"Compiled {compiled_count} sources"
        )

        _compile_status["last_result"] = {
            "status": "completed",
            "sources_compiled": compiled_count,
            "sources_failed": failed_count,
            "articles_created": all_created,
        }
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("Compile task failed")
        _compile_status["last_result"] = {"status": "error", "detail": str(exc)}
    finally:
        _compile_status["running"] = False


def start_compile(vault_path: Path, qmd_debounce) -> dict[str, Any]:
    """Start the background compile task. Returns immediately.

    Raises ValueError if a compile is already running.
    """
    if _compile_status["running"]:
        raise ValueError("A compile task is already running")

    raw_dir = vault_path / "raw"
    if not raw_dir.exists():
        return {"status": "no raw directory", "compiled": 0}

    _compile_status["running"] = True
    _compile_status["last_result"] = None
    asyncio.create_task(_run_compile(vault_path, qmd_debounce))

    return {"status": "accepted", "message": "Compile started in background"}


def get_compile_status() -> dict[str, Any]:
    """Return the current compile task status."""
    return {
        "running": _compile_status["running"],
        "last_result": _compile_status["last_result"],
    }
