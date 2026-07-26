"""Aggregation and reporting: per-category numbers, losses included.

Accuracy = correct / (correct + incorrect). Judge errors (unparseable
verdicts) are excluded from the denominator and reported as their own
column — visible, never silently dropped or counted as wrong.
"""
from __future__ import annotations

from typing import Any

from evals.traces import Trace


def _bucket() -> dict[str, Any]:
    return {"correct": 0, "incorrect": 0, "errors": 0, "accuracy": None}


def _finalize(bucket: dict[str, Any]) -> None:
    judged = bucket["correct"] + bucket["incorrect"]
    bucket["accuracy"] = bucket["correct"] / judged if judged else None


def aggregate(traces: list[Trace]) -> dict[str, Any]:
    """Aggregate judge verdicts overall and per category."""
    overall = _bucket()
    categories: dict[str, dict[str, Any]] = {}

    for trace in traces:
        buckets = [overall, categories.setdefault(trace.category, _bucket())]
        for bucket in buckets:
            if trace.judge_verdict == "correct":
                bucket["correct"] += 1
            elif trace.judge_verdict == "incorrect":
                bucket["incorrect"] += 1
            else:
                bucket["errors"] += 1

    _finalize(overall)
    for bucket in categories.values():
        _finalize(bucket)

    return {"overall": overall, "categories": categories}


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def to_markdown(aggregation: dict[str, Any], run_name: str) -> str:
    """Render the aggregation as the published results table."""
    lines = [
        f"## Results — `{run_name}`",
        "",
        "| Category | Accuracy | Correct | Incorrect | Judge errors |",
        "|---|---|---|---|---|",
    ]
    for category in sorted(aggregation["categories"]):
        b = aggregation["categories"][category]
        lines.append(
            f"| {category} | {_pct(b['accuracy'])} | {b['correct']} "
            f"| {b['incorrect']} | {b['errors']} |"
        )
    o = aggregation["overall"]
    lines.append(
        f"| **overall** | **{_pct(o['accuracy'])}** | {o['correct']} "
        f"| {o['incorrect']} | {o['errors']} |"
    )
    return "\n".join(lines) + "\n"
