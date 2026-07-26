"""Benchmark orchestration: ingest -> retrieve -> answer -> judge -> trace.

All model interaction is injected (adapter, answer callable, judge), so
this module is fully testable offline and identical across benchmarks.

Per-question isolation: when ``reset_fn`` is provided it runs before each
question's ingest, so retrieval only ever sees that question's haystack —
the setting the benchmarks define.
"""
from __future__ import annotations

import time
from pathlib import PurePosixPath
from typing import Any, Awaitable, Callable

from evals.judge import Judge
from evals.traces import Trace

AnswerFn = Callable[[str, list[dict[str, Any]]], Awaitable[str]]


def _session_filename(question: Any, index: int) -> str:
    session_ids = getattr(question, "session_ids", None) or []
    if index < len(session_ids):
        return f"{session_ids[index]}.md"
    return f"{question.question_id}-session-{index:03d}.md"


def _compute_recall(question: Any, retrieved: list[dict[str, Any]]) -> float | None:
    evidence = getattr(question, "evidence_session_ids", None) or []
    if not evidence:
        return None
    retrieved_stems = {PurePosixPath(r.get("path", "")).stem for r in retrieved}
    found = sum(1 for sid in evidence if sid in retrieved_stems)
    return found / len(evidence)


async def run_eval(
    questions: list[Any],
    adapter: Any,
    answer_fn: AnswerFn,
    judge: Judge,
    reset_fn: Callable[[], Awaitable[None]] | None = None,
    index_fn: Callable[[], Awaitable[None]] | None = None,
    usage_ledger: dict[str, int] | None = None,
    on_trace: Callable[[Trace], Awaitable[None]] | None = None,
) -> list[Trace]:
    """Run every question through the system under test and judge it.

    ``index_fn`` runs after a question's haystack is ingested and before
    retrieval — e.g. to force a synchronous QMD rescan + embed.
    ``on_trace`` receives each completed trace immediately, so long runs
    can persist results incrementally (crash-safe).
    """
    traces: list[Trace] = []
    for question in questions:
        if reset_fn is not None:
            await reset_fn()

        for i, session in enumerate(question.sessions):
            await adapter.ingest(_session_filename(question, i), session)

        if index_fn is not None:
            await index_fn()

        start = time.perf_counter()
        retrieved = await adapter.retrieve(question.question)
        retrieve_ms = int((time.perf_counter() - start) * 1000)

        snapshot = dict(usage_ledger) if usage_ledger else {}
        start = time.perf_counter()
        answer = await answer_fn(question.question, retrieved)
        answer_ms = int((time.perf_counter() - start) * 1000)
        answer_usage = {
            k: usage_ledger[k] - snapshot.get(k, 0) for k in (usage_ledger or {})
        }

        snapshot = dict(usage_ledger) if usage_ledger else {}
        start = time.perf_counter()
        verdict = await judge.judge(
            question=question.question,
            gold=question.gold_answer,
            hypothesis=answer,
        )
        judge_ms = int((time.perf_counter() - start) * 1000)
        judge_usage = {
            k: usage_ledger[k] - snapshot.get(k, 0) for k in (usage_ledger or {})
        }

        tokens: dict[str, int] = {}
        if usage_ledger is not None:
            tokens = {
                **{f"answer_{k}": v for k, v in answer_usage.items()},
                **{f"judge_{k}": v for k, v in judge_usage.items()},
            }

        trace = Trace(
            question_id=question.question_id,
            category=question.category,
            question=question.question,
            gold_answer=question.gold_answer,
            system=adapter.name,
            retrieved=retrieved,
            answer=answer,
            judge_verdict=verdict["verdict"],
            judge_raw=verdict["raw"],
            latency_ms={
                "retrieve": retrieve_ms,
                "answer": answer_ms,
                "judge": judge_ms,
            },
            recall=_compute_recall(question, retrieved),
            tokens=tokens,
        )
        traces.append(trace)
        if on_trace is not None:
            await on_trace(trace)
    return traces
