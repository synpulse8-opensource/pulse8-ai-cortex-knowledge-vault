from __future__ import annotations

import json
from pathlib import Path

from anthropic import AsyncAnthropic

from cortex.compiler.prompts import COMPILE_SYSTEM_PROMPT, INGEST_SYSTEM_PROMPT
from cortex.config import settings
from cortex.vault.reader import read_note, scan_vault
from cortex.vault.writer import write_note


class KnowledgeCompiler:
    """Compiles raw sources into structured wiki articles using an LLM."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.compiler_model

    async def ingest_source(self, source_path: Path) -> list[Path]:
        """Read a raw source, call LLM to produce wiki articles, write them to wiki/."""
        source_content = source_path.read_text()
        relative_source = str(source_path.relative_to(self.vault_path))

        index_content = self._build_index_context()

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=settings.compiler_max_tokens,
            system=INGEST_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    f"## Raw Source: {relative_source}\n\n"
                    f"{source_content}\n\n"
                    f"## Existing Wiki Index\n\n{index_content}"
                ),
            }],
        )

        articles = self._parse_articles(response.content[0].text)

        created_paths: list[Path] = []
        for article in articles:
            filename = article["filename"]
            if not filename.endswith(".md"):
                filename += ".md"
            note_path = self.vault_path / "wiki" / filename

            frontmatter = article.get("frontmatter", {})
            frontmatter["source_path"] = relative_source

            write_note(
                path=note_path,
                vault_root=self.vault_path,
                content=article["content"],
                frontmatter=frontmatter,
                mode="upsert",
                authored_by=self.model,
                model=self.model,
            )
            created_paths.append(note_path)

        return created_paths

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

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=settings.compiler_max_tokens,
            system=COMPILE_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    f"## New Articles\n\n{'---'.join(new_articles)}\n\n"
                    f"## Existing Wiki Index\n\n{index_context}"
                ),
            }],
        )

        updates = self._parse_updates(response.content[0].text)
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

    def _parse_articles(self, text: str) -> list[dict]:
        """Parse LLM response into article dicts, handling code fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return []

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
