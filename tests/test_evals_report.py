"""Tests for per-category aggregation and the published results table."""
from __future__ import annotations


def _trace(category: str, verdict: str):
    from evals.traces import Trace

    return Trace(
        question_id=f"{category}-{verdict}",
        category=category,
        question="q",
        gold_answer="g",
        system="cortex-hybrid",
        judge_verdict=verdict,
    )


def test_aggregate_per_category_and_overall():
    from evals.report import aggregate

    traces = [
        _trace("temporal", "correct"),
        _trace("temporal", "incorrect"),
        _trace("multi-session", "correct"),
        _trace("multi-session", "correct"),
        _trace("multi-session", "error"),
    ]
    result = aggregate(traces)

    assert result["overall"]["correct"] == 3
    assert result["overall"]["incorrect"] == 1
    assert result["overall"]["errors"] == 1
    # Accuracy excludes judge errors from the denominator; they are
    # reported separately, never hidden.
    assert result["overall"]["accuracy"] == 0.75

    assert result["categories"]["temporal"]["accuracy"] == 0.5
    assert result["categories"]["multi-session"]["accuracy"] == 1.0
    assert result["categories"]["multi-session"]["errors"] == 1


def test_markdown_report_shows_every_category_and_errors():
    from evals.report import aggregate, to_markdown

    traces = [
        _trace("temporal", "correct"),
        _trace("temporal", "incorrect"),
        _trace("abstention", "incorrect"),
    ]
    md = to_markdown(aggregate(traces), run_name="longmemeval-s-hybrid")

    assert "longmemeval-s-hybrid" in md
    assert "temporal" in md
    assert "abstention" in md
    assert "50.0%" in md
    assert "0.0%" in md  # losses are published, not hidden


def test_aggregate_empty_traces():
    from evals.report import aggregate

    result = aggregate([])
    assert result["overall"]["accuracy"] is None
    assert result["categories"] == {}
