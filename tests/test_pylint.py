"""Ensure the codebase passes pylint with no errors or warnings."""
from __future__ import annotations

import subprocess


def test_pylint_passes():
    """All tracked .py files must pass pylint cleanly."""
    tracked = subprocess.check_output(
        ["git", "ls-files", "*.py"], text=True
    ).splitlines()
    assert tracked, "No tracked .py files found"

    result = subprocess.run(
        ["python", "-m", "pylint", *tracked],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"pylint exited with code {result.returncode}\n{result.stdout}"
    )
