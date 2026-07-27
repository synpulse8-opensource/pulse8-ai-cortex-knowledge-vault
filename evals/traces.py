"""Per-question trace records — the auditable artifact of a benchmark run.

Every published number decomposes into one JSONL line per question:
what was asked, what was retrieved, what was answered, and how it was
judged. Anyone can audit an individual judgment.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Trace:
    """One question's full lifecycle through the harness."""

    question_id: str
    category: str
    question: str
    gold_answer: str
    system: str
    retrieved: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    judge_verdict: str = ""
    judge_raw: str = ""
    latency_ms: dict[str, int] = field(default_factory=dict)
    # Fraction of labeled evidence sessions present in the retrieved set
    # (None when the dataset carries no evidence labels).
    recall: float | None = None
    tokens: dict[str, int] = field(default_factory=dict)


def write_traces(path: Path | str, traces: list[Trace]) -> None:
    """Write traces as JSONL (one object per line)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for trace in traces:
            fh.write(json.dumps(asdict(trace), ensure_ascii=False) + "\n")


def read_traces(path: Path | str) -> list[Trace]:
    """Read traces back from JSONL; missing file yields an empty list."""
    path = Path(path)
    if not path.exists():
        return []
    traces = []
    # Split on newline only: answers may carry unescaped U+2028/U+2029
    # (written with ensure_ascii=False), which splitlines() would treat
    # as record boundaries, corrupting the parse.
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            traces.append(Trace(**json.loads(line)))
    return traces
