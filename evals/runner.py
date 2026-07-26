"""Benchmark orchestration: ingest -> retrieve -> answer -> judge -> trace.

All model interaction is injected (adapter, answer callable, judge), so
this module is fully testable offline and identical across benchmarks.
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from evals.judge import Judge
from evals.traces import Trace

AnswerFn = Callable[[str, list[dict[str, Any]]], Awaitable[str]]


async def run_eval(
    questions: list[Any],
    adapter: Any,
    answer_fn: AnswerFn,
    judge: Judge,
) -> list[Trace]:
    """Run every question through the system under test and judge it."""
    traces: list[Trace] = []
    for question in questions:
        for i, session in enumerate(question.sessions):
            await adapter.ingest(
                f"{question.question_id}-session-{i:03d}.md", session
            )

        start = time.perf_counter()
        retrieved = await adapter.retrieve(question.question)
        retrieve_ms = int((time.perf_counter() - start) * 1000)

        start = time.perf_counter()
        answer = await answer_fn(question.question, retrieved)
        answer_ms = int((time.perf_counter() - start) * 1000)

        start = time.perf_counter()
        verdict = await judge.judge(
            question=question.question,
            gold=question.gold_answer,
            hypothesis=answer,
        )
        judge_ms = int((time.perf_counter() - start) * 1000)

        traces.append(
            Trace(
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
            )
        )
    return traces
