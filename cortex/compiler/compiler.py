"""Knowledge compiler: MarkItDown conversion + LLM cross-referencing."""
from __future__ import annotations

import json
import re
from pathlib import Path

from markitdown import MarkItDown
from openai import AsyncOpenAI

from cortex.compiler.prompts import COMPILE_SYSTEM_PROMPT
from cortex.config import settings
from cortex.vault.reader import read_note
from cortex.vault.writer import write_note


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

    async def ingest_source(self, source_path: Path) -> list[Path]:
        """Convert a raw source file to a wiki Markdown note using MarkItDown."""
        relative_source = str(source_path.relative_to(self.vault_path))

        result = self._md.convert_local(str(source_path))
        md_content = (result.text_content or "").strip()

        slug = _slug_from_stem(source_path.stem)
        title = _title_from_markdown(md_content, source_path.stem)

        filename = f"{slug}.md"
        note_path = self.vault_path / "wiki" / filename

        frontmatter = {
            "title": title,
            "source_path": relative_source,
        }

        write_note(
            path=note_path,
            vault_root=self.vault_path,
            content=md_content,
            frontmatter=frontmatter,
            mode="upsert",
            authored_by="markitdown",
            model=None,
        )

        return [note_path]

    async def compile_cross_references(self, new_paths: list[Path]) -> None:
        """After new articles are created, identify cross-references and contradictions."""
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
