"""Pinned dataset download with SHA-256 verification.

Benchmark data is downloaded at run time and verified against the hash in
the run config — a silent dataset change would invalidate every published
number, so a mismatch is a hard failure.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from evals.config import DatasetConfig


def verify_sha256(path: Path | str, expected: str) -> None:
    """Raise ValueError unless the file's SHA-256 matches the pinned hash."""
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest != expected.lower():
        raise ValueError(
            f"SHA-256 mismatch for {path}: expected {expected}, got {digest}. "
            "The dataset changed upstream or the download is corrupt — "
            "refusing to run an unreproducible eval."
        )


def download(dataset: DatasetConfig, client: httpx.Client | None = None) -> Path:
    """Download the dataset if missing, then verify its pinned hash."""
    target = Path(dataset.path)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        own_client = client is None
        client = client or httpx.Client(follow_redirects=True, timeout=300.0)
        try:
            with client.stream("GET", dataset.url) as response:
                response.raise_for_status()
                with target.open("wb") as fh:
                    for chunk in response.iter_bytes():
                        fh.write(chunk)
        finally:
            if own_client:
                client.close()
    verify_sha256(target, dataset.sha256)
    return target
