"""Validate the QMD container Dockerfile installs qmd as real files, not a symlink.

Regression guard: with npm >= 9 (node:22), ``npm install -g .`` from a local
folder creates a global *symlink* to the source directory. The build then
deletes the source folder, leaving a dangling symlink — every ``qmd`` spawn
inside the container fails with ENOENT and searches silently return [].
Installing from a packed tarball forces npm to copy files.
"""
from __future__ import annotations

import re
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parent.parent / "docker" / "qmd" / "Dockerfile"


def test_qmd_not_installed_from_local_folder():
    """`npm install -g .` symlinks the (later deleted) source dir — forbidden."""
    content = DOCKERFILE.read_text()
    assert not re.search(r"npm install -g \.(?=\s|\\|$)", content), (
        "npm install -g <folder> creates a symlink into the build dir that is "
        "deleted later in the same layer; install from a packed tarball instead"
    )


def test_qmd_installed_as_real_files():
    """qmd must be installed from a registry tarball or packed .tgz — not a local folder."""
    content = DOCKERFILE.read_text()
    from_registry = "@tobilu/qmd" in content and re.search(
        r"npm install -g\s+@tobilu/qmd", content
    )
    from_packed_tarball = "npm pack" in content and ".tgz" in content
    assert from_registry or from_packed_tarball, (
        "install qmd via `npm install -g @tobilu/qmd` or pack + install a .tgz tarball"
    )
