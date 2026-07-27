"""Tests for per-category aggregation and the published results table."""
from __future__ import annotations


def _trace(category: str, verdict: str, recall=None, tokens=None):
    from evals.traces import Trace

    return Trace(
        question_id=f"{category}-{verdict}",
        category=category,
        question="q",
        gold_answer="g",
        system="cortex-hybrid",
        judge_verdict=verdict,
        recall=recall,
        tokens=tokens or {},
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


def test_aggregate_mean_recall_and_token_totals():
    from evals.report import aggregate

    traces = [
        _trace("temporal", "correct", recall=1.0,
               tokens={"answer_prompt": 100, "judge_prompt": 10}),
        _trace("temporal", "incorrect", recall=0.0,
               tokens={"answer_prompt": 200, "judge_prompt": 20}),
        _trace("abstention", "correct", recall=None),  # no evidence labels
    ]
    result = aggregate(traces)

    assert result["overall"]["recall"] == 0.5
    assert result["categories"]["temporal"]["recall"] == 0.5
    # Unlabeled traces don't drag the mean; a recall-free category shows None.
    assert result["categories"]["abstention"]["recall"] is None
    assert result["overall"]["tokens"] == 330


def test_markdown_includes_recall_and_tokens():
    from evals.report import aggregate, to_markdown

    md = to_markdown(
        aggregate([_trace("temporal", "correct", recall=0.75,
                          tokens={"answer_prompt": 1000})]),
        run_name="run-x",
    )
    assert "Recall" in md
    assert "75.0%" in md
    assert "Tokens" in md
    assert "1,000" in md
