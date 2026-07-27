"""Eval run configuration: everything pinned, refuse the unreproducible.

A published benchmark run is a config file plus a traces artifact. The
config therefore pins the dataset (URL + SHA-256), the Cortex retrieval
settings, the answer and judge models, and the seed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class DatasetConfig:
    """Pinned dataset reference. Data files are downloaded, never committed."""

    name: str
    url: str
    sha256: str
    path: str


@dataclass(frozen=True)
class CortexConfig:
    """How the harness talks to a running Cortex instance.

    ``vault_path`` (local path) enables per-question vault isolation: the
    runner wipes it between questions. ``qmd_update_url`` is POSTed after
    each question's ingest to force a synchronous QMD rescan + embed.
    ``context_chars`` > 0 makes the adapter feed full note content (capped
    per note) to the answer model instead of search snippets.
    """

    base_url: str
    search_mode: str = "hybrid"
    top_k: int = 8
    vault_path: str | None = None
    qmd_update_url: str | None = None
    context_chars: int = 0


@dataclass(frozen=True)
class ModelsConfig:
    """Answer and judge models. Must differ (self-preference bias)."""

    answer: str
    judge: str


@dataclass(frozen=True)
class EvalConfig:
    """One reproducible benchmark configuration."""

    name: str
    benchmark: str
    dataset: DatasetConfig
    cortex: CortexConfig
    models: ModelsConfig
    seed: int
    output_dir: str

    @classmethod
    def from_yaml(cls, path: Path | str) -> EvalConfig:
        """Load and validate a config file."""
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

        dataset_data = data.get("dataset") or {}
        if not dataset_data.get("sha256"):
            raise ValueError(
                "dataset.sha256 is required: unpinned datasets make runs "
                "unreproducible"
            )
        dataset = DatasetConfig(
            name=dataset_data["name"],
            url=dataset_data["url"],
            sha256=str(dataset_data["sha256"]).strip(),
            path=dataset_data["path"],
        )

        cortex_data = data.get("cortex") or {}
        cortex = CortexConfig(
            base_url=cortex_data["base_url"],
            search_mode=cortex_data.get("search_mode", "hybrid"),
            top_k=int(cortex_data.get("top_k", 8)),
            vault_path=cortex_data.get("vault_path"),
            qmd_update_url=cortex_data.get("qmd_update_url"),
            context_chars=int(cortex_data.get("context_chars", 0)),
        )

        models_data = data.get("models") or {}
        models = ModelsConfig(
            answer=models_data["answer"], judge=models_data["judge"]
        )
        if models.answer == models.judge:
            raise ValueError(
                "models.judge must differ from models.answer to blunt "
                "self-preference bias"
            )

        return cls(
            name=data["name"],
            benchmark=data["benchmark"],
            dataset=dataset,
            cortex=cortex,
            models=models,
            seed=int(data.get("seed", 42)),
            output_dir=data.get("output_dir", "evals/out"),
        )
