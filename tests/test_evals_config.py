"""Tests for the eval harness config: pinned, validated, reproducible."""
from __future__ import annotations

from pathlib import Path

import pytest

_VALID_YAML = """\
name: longmemeval-s-hybrid
benchmark: longmemeval
dataset:
  name: longmemeval_s
  url: https://example.com/longmemeval_s.json
  sha256: "aa" 
  path: evals/data/longmemeval_s.json
cortex:
  base_url: http://localhost:8420
  search_mode: hybrid
  top_k: 8
models:
  answer: anthropic/claude-sonnet-4
  judge: openai/gpt-4o
seed: 42
output_dir: evals/out
"""


def _write_config(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(text)
    return p


def test_config_loads_all_pinned_fields(tmp_path: Path):
    from evals.config import EvalConfig

    cfg = EvalConfig.from_yaml(_write_config(tmp_path, _VALID_YAML))
    assert cfg.name == "longmemeval-s-hybrid"
    assert cfg.benchmark == "longmemeval"
    assert cfg.dataset.sha256 == "aa"
    assert cfg.cortex.base_url == "http://localhost:8420"
    assert cfg.cortex.search_mode == "hybrid"
    assert cfg.cortex.top_k == 8
    assert cfg.models.answer == "anthropic/claude-sonnet-4"
    assert cfg.models.judge == "openai/gpt-4o"
    assert cfg.seed == 42


def test_config_rejects_same_judge_and_answer_model(tmp_path: Path):
    """Judge model must differ from answer model (self-preference bias)."""
    from evals.config import EvalConfig

    text = _VALID_YAML.replace("openai/gpt-4o", "anthropic/claude-sonnet-4")
    with pytest.raises(ValueError, match="judge"):
        EvalConfig.from_yaml(_write_config(tmp_path, text))


def test_config_rejects_missing_dataset_sha(tmp_path: Path):
    """Unpinned datasets make runs unreproducible — refuse them."""
    from evals.config import EvalConfig

    text = _VALID_YAML.replace('  sha256: "aa" \n', "")
    with pytest.raises(ValueError, match="sha256"):
        EvalConfig.from_yaml(_write_config(tmp_path, text))
