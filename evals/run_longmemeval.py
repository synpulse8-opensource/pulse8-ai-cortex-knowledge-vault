"""LongMemEval runner.

Reproduction command (the deliverable):

    ./scripts/start.sh
    uv run python -m evals.run_longmemeval \\
        --config evals/configs/longmemeval-s-hybrid.yaml

Requires LLM_API_KEY (and optionally LLM_BASE_URL) in the environment for
the answer and judge models named in the config.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals.adapters.cortex import CortexAdapter
from evals.config import EvalConfig
from evals.datasets.download import download
from evals.judge import Judge
from evals.report import aggregate, to_markdown
from evals.runner import run_eval
from evals.traces import write_traces

ANSWER_SYSTEM_PROMPT = (
    "Answer the question using only the provided context. If the context "
    "does not contain the answer, say you don't know."
)


@dataclass(frozen=True)
class Question:
    """One benchmark question with the sessions that must be ingested."""

    question_id: str
    category: str
    question: str
    gold_answer: str
    sessions: list[str] = field(default_factory=list)


def _render_session(turns: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"**{turn.get('role', 'user')}**: {turn.get('content', '')}"
        for turn in turns
    )


def load_longmemeval(path: Path | str, limit: int | None = None) -> list[Question]:
    """Parse the LongMemEval JSON into Question records.

    ``limit`` caps the number of questions — a cheap smoke run before
    spending on a full one.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if limit is not None:
        data = data[:limit]
    questions = []
    for item in data:
        questions.append(
            Question(
                question_id=str(item["question_id"]),
                category=item.get("question_type", "unknown"),
                question=item["question"],
                gold_answer=str(item.get("answer", "")),
                sessions=[
                    _render_session(session)
                    for session in item.get("haystack_sessions", [])
                ],
            )
        )
    return questions


def _make_complete(model: str):
    """Async (system, user) -> text against an OpenAI-compatible endpoint."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
    )

    async def complete(system: str, user: str) -> str:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    return complete


async def _main(config_path: str, limit: int | None = None) -> None:
    config = EvalConfig.from_yaml(config_path)
    dataset_path = download(config.dataset)
    questions = load_longmemeval(dataset_path, limit=limit)

    adapter = CortexAdapter(
        base_url=config.cortex.base_url,
        search_mode=config.cortex.search_mode,
        top_k=config.cortex.top_k,
    )
    answer_complete = _make_complete(config.models.answer)

    async def answer_fn(question: str, contexts: list[dict[str, Any]]) -> str:
        context_block = "\n\n---\n\n".join(
            f"[{c['path']}]\n{c['snippet']}" for c in contexts
        )
        return await answer_complete(
            ANSWER_SYSTEM_PROMPT, f"Context:\n{context_block}\n\nQuestion: {question}"
        )

    judge = Judge(
        complete=_make_complete(config.models.judge),
        judge_model=config.models.judge,
        answer_model=config.models.answer,
    )

    traces = await run_eval(questions, adapter, answer_fn, judge)
    await adapter.aclose()

    # Keep smoke-run artifacts apart from full-run (publishable) ones.
    run_name = config.name if limit is None else f"{config.name}-limit{limit}"
    out_dir = Path(config.output_dir) / run_name
    write_traces(out_dir / "traces.jsonl", traces)
    report = to_markdown(aggregate(traces), run_name=run_name)
    (out_dir / "report.md").write_text(report)
    print(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LongMemEval against Cortex")
    parser.add_argument("--config", required=True, help="Path to a pinned run config")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N questions (smoke run); omit for the full set",
    )
    args = parser.parse_args()
    asyncio.run(_main(args.config, limit=args.limit))


if __name__ == "__main__":
    main()
