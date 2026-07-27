"""Aggregation and reporting: per-category numbers, losses included.

Accuracy = correct / (correct + incorrect). Judge errors (unparseable
verdicts) are excluded from the denominator and reported as their own
column — visible, never silently dropped or counted as wrong.
"""
from __future__ import annotations

from typing import Any

from evals.traces import Trace


def _bucket() -> dict[str, Any]:
    return {
        "correct": 0,
        "incorrect": 0,
        "errors": 0,
        "accuracy": None,
        "recall": None,
        "tokens": 0,
        "_recall_sum": 0.0,
        "_recall_n": 0,
    }


def _finalize(bucket: dict[str, Any]) -> None:
    judged = bucket["correct"] + bucket["incorrect"]
    bucket["accuracy"] = bucket["correct"] / judged if judged else None
    if bucket["_recall_n"]:
        bucket["recall"] = bucket["_recall_sum"] / bucket["_recall_n"]
    del bucket["_recall_sum"], bucket["_recall_n"]


def aggregate(traces: list[Trace]) -> dict[str, Any]:
    """Aggregate judge verdicts, mean recall, and token totals."""
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
            if trace.recall is not None:
                bucket["_recall_sum"] += trace.recall
                bucket["_recall_n"] += 1
            bucket["tokens"] += sum(trace.tokens.values())

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
        "| Category | Accuracy | Recall | Correct | Incorrect | Judge errors | Tokens |",
        "|---|---|---|---|---|---|---|",
    ]

    def row(label: str, b: dict[str, Any], bold: bool = False) -> str:
        acc = _pct(b["accuracy"])
        if bold:
            label, acc = f"**{label}**", f"**{acc}**"
        return (
            f"| {label} | {acc} | {_pct(b['recall'])} | {b['correct']} "
            f"| {b['incorrect']} | {b['errors']} | {b['tokens']:,} |"
        )

    for category in sorted(aggregation["categories"]):
        lines.append(row(category, aggregation["categories"][category]))
    lines.append(row("overall", aggregation["overall"], bold=True))
    return "\n".join(lines) + "\n"
