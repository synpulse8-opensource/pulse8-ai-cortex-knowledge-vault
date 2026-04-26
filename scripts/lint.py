"""Vault health checks — lint the knowledge base for issues."""
from __future__ import annotations

import asyncio
import logging

from cortex.config import settings
from cortex.graph.builder import build_graph
from cortex.vault.reader import resolve_wikilink, scan_vault

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Run vault health checks and print a report."""
    vault_path = settings.vault_path
    notes = scan_vault(vault_path)
    graph = await build_graph(notes, vault_path / ".cortex" / "graph.json", vault_path)

    issues: list[str] = []

    orphans = await graph.find_orphans()
    note_orphans = [o for o in orphans if not o.startswith("tag:")]
    if note_orphans:
        issues.append(f"## Orphan Notes ({len(note_orphans)})\n")
        for o in note_orphans:
            issues.append(f"- {o}")
        issues.append("")

    broken_links: list[tuple[str, str]] = []
    for note in notes:
        for link in note.wikilinks:
            resolved = resolve_wikilink(link, vault_path)
            if resolved is None:
                broken_links.append((note.path, link))
    if broken_links:
        issues.append(f"## Broken Wikilinks ({len(broken_links)})\n")
        for note_path, link in broken_links:
            issues.append(f"- {note_path}: [[{link}]]")
        issues.append("")

    existing_sources: set[str] = set()
    for note in notes:
        sp = note.frontmatter.get("source_path")
        if sp:
            existing_sources.add(sp)

    raw_dir = vault_path / "raw"
    unprocessed: list[str] = []
    if raw_dir.exists():
        for raw_file in sorted(raw_dir.iterdir()):
            if raw_file.is_dir():
                continue
            rel = str(raw_file.relative_to(vault_path))
            if rel not in existing_sources:
                unprocessed.append(rel)
    if unprocessed:
        issues.append(f"## Unprocessed Raw Sources ({len(unprocessed)})\n")
        for u in unprocessed:
            issues.append(f"- {u}")
        issues.append("")

    missing_provenance: list[str] = []
    for note in notes:
        if "authored_by" not in note.frontmatter:
            missing_provenance.append(note.path)
    if missing_provenance:
        issues.append(f"## Missing Provenance ({len(missing_provenance)})\n")
        for mp in missing_provenance:
            issues.append(f"- {mp}")
        issues.append("")

    if issues:
        report = "# Cortex Lint Report\n\n" + "\n".join(issues)
        print(report)

        report_path = vault_path / ".cortex" / "lint-report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report)
        logger.info("Report written to %s", report_path)
    else:
        print("No issues found. Vault is healthy.")

    stats = await graph.get_stats()
    print(f"\nStats: {stats['total_nodes']} nodes, {stats['total_edges']} edges, {stats['orphans']} orphans")


if __name__ == "__main__":
    asyncio.run(main())
