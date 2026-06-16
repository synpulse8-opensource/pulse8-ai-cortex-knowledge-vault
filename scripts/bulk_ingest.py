"""CLI entry point for bulk ingestion from a local directory."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from cortex.compiler.bulk import BulkIngestor
from cortex.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-bulk-ingest",
        description="Bulk-ingest files from a local directory into the Cortex vault.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the source directory containing files to ingest.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Maximum number of parallel LLM enrichment calls (default: 4).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass SHA-256 manifest check and re-ingest all files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be ingested without actually copying or compiling.",
    )
    parser.add_argument(
        "--prune",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Remove raw/wiki files whose sources were deleted from the source directory.",
    )
    return parser


async def run_cli(argv: list[str] | None = None, vault_path: Path | None = None) -> dict:
    """Parse arguments and run the bulk ingest pipeline.

    ``vault_path`` can be injected for testing; defaults to ``settings.vault_path``.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    source_dir = Path(args.source)
    if not source_dir.is_dir():
        logger.error("Source directory does not exist: %s", source_dir)
        sys.exit(1)

    vp = vault_path or settings.vault_path

    ingestor = BulkIngestor(
        vault_path=vp,
        source_dir=source_dir,
        concurrency=args.concurrency,
        force=args.force,
        dry_run=args.dry_run,
        prune=args.prune,
    )

    result = await ingestor.run()

    if result["dry_run"]:
        logger.info("[DRY RUN] Would copy %d files, skip %d", len(result["copied"]), len(result["skipped"]))
        for name in result["copied"]:
            logger.info("  + %s", name)
    else:
        logger.info(
            "Copied %d, skipped %d, compiled %d",
            len(result["copied"]), len(result["skipped"]), len(result["compiled"]),
        )

    return result


def main() -> None:
    asyncio.run(run_cli())


if __name__ == "__main__":
    main()
