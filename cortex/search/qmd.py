from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class QMDSearch:
    """Bridge to QMD search engine (https://github.com/tobi/qmd)."""

    def __init__(self, vault_path: Path, qmd_bin: str = "qmd") -> None:
        self.vault_path = vault_path
        self.qmd_bin = qmd_bin
        self._initialized = False

    async def _run_safe(self, args: list[str]) -> str:
        """Run a QMD command, returning empty string on failure instead of raising."""
        try:
            return await self._run(args)
        except RuntimeError:
            logger.debug("QMD command %s failed (likely already configured)", args[:2])
            return ""

    async def initialize(self) -> None:
        """Set up QMD collections for the vault directories."""
        for name in ("wiki", "agents", "sessions", "daily"):
            await self._run_safe(["collection", "add", str(self.vault_path / name), "--name", name])

        await self._run_safe(["context", "add", "qmd://wiki", "Knowledge articles compiled from raw sources"])
        await self._run_safe(["context", "add", "qmd://agents", "Agent definition files"])
        await self.update()
        self._initialized = True

    async def update(self) -> None:
        """Re-index and re-embed all collections."""
        await self._run(["update"])
        await self._run(["embed"])

    async def search(
        self,
        query: str,
        mode: str = "hybrid",
        collection: str | None = None,
        top_k: int = 10,
    ) -> list[dict]:
        """Search the vault via QMD.

        mode: 'keyword' → search, 'semantic' → vsearch, 'hybrid' → query
        """
        cmd_map = {"keyword": "search", "semantic": "vsearch", "hybrid": "query"}
        cmd = cmd_map.get(mode, "query")
        args = [cmd, query, "--json", "-n", str(top_k)]
        if collection:
            args.extend(["-c", collection])
        result = await self._run(args)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return []

    async def _run(self, args: list[str]) -> str:
        """Run a QMD CLI command and return stdout."""
        proc = await asyncio.create_subprocess_exec(
            self.qmd_bin,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"QMD error: {stderr.decode()}")
        return stdout.decode()
