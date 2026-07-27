"""Tests for per-question trace records (the auditable run artifact)."""
from __future__ import annotations

from pathlib import Path


def _sample_trace():
    from evals.traces import Trace

    return Trace(
        question_id="q-001",
        category="multi-session",
        question="When did the user move to Zurich?",
        gold_answer="March 2025",
        system="cortex-hybrid",
        retrieved=[{"path": "wiki/session-12.md", "snippet": "moved to Zurich"}],
        answer="The user moved to Zurich in March 2025.",
        judge_verdict="correct",
        judge_raw="yes — matches gold",
        latency_ms={"retrieve": 120, "answer": 900, "judge": 300},
    )


def test_trace_jsonl_roundtrip(tmp_path: Path):
    from evals.traces import Trace, read_traces, write_traces

    path = tmp_path / "traces.jsonl"
    original = [_sample_trace(), _sample_trace()]
    write_traces(path, original)

    loaded = read_traces(path)
    assert len(loaded) == 2
    assert isinstance(loaded[0], Trace)
    assert loaded[0] == original[0]
    # One JSON object per line — greppable, diffable, streamable.
    assert len(path.read_text().strip().splitlines()) == 2


def test_read_traces_missing_file(tmp_path: Path):
    from evals.traces import read_traces

    assert read_traces(tmp_path / "nope.jsonl") == []


def test_roundtrip_survives_unicode_line_separators(tmp_path: Path):
    """Model answers can contain U+2028/U+2029; since we write JSONL with
    ensure_ascii=False these land unescaped in the file, and reading must
    split records on newline only — not on every Unicode line break."""
    from dataclasses import replace

    from evals.traces import read_traces, write_traces

    trace = replace(
        _sample_trace(), answer="first part\u2028second part\u2029third"
    )
    path = tmp_path / "traces.jsonl"
    write_traces(path, [trace, _sample_trace()])

    loaded = read_traces(path)
    assert len(loaded) == 2
    assert loaded[0].answer == "first part\u2028second part\u2029third"
