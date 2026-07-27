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
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from evals.adapters.cortex import CortexAdapter
from evals.config import EvalConfig
from evals.datasets.download import download
from evals.judge import Judge
from evals.report import aggregate, to_markdown
from evals.runner import run_eval
from evals.traces import write_traces

ANSWER_SYSTEM_PROMPT = (
    "Answer the question using only the provided context. Sessions in the "
    "context carry a 'Session date:' line; use those dates for any "
    "time-related reasoning. If the context does not contain the answer, "
    "say you don't know."
)


@dataclass(frozen=True)
class Question:
    """One benchmark question with the sessions that must be ingested.

    ``session_ids`` parallels ``sessions``; ``evidence_session_ids`` marks
    which sessions contain the answer (dataset labels), enabling recall@k.
    """

    question_id: str
    category: str
    question: str
    gold_answer: str
    sessions: list[str] = field(default_factory=list)
    session_ids: list[str] = field(default_factory=list)
    evidence_session_ids: list[str] = field(default_factory=list)
    question_date: str = ""


def _render_session(turns: list[dict[str, Any]], date: str = "") -> str:
    """Render one session; its timestamp becomes part of the ingested
    content (official LongMemEval setup timestamps every session)."""
    body = "\n\n".join(
        f"**{turn.get('role', 'user')}**: {turn.get('content', '')}"
        for turn in turns
    )
    if date:
        return f"Session date: {date}\n\n{body}"
    return body


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
        question_id = str(item["question_id"])
        raw_sessions = item.get("haystack_sessions", [])
        dates = item.get("haystack_dates", []) or [""] * len(raw_sessions)
        sessions = [
            _render_session(session, date)
            for session, date in zip(raw_sessions, dates)
        ]
        session_ids = [
            str(sid) for sid in item.get("haystack_session_ids", [])
        ] or [f"{question_id}-session-{i:03d}" for i in range(len(sessions))]
        questions.append(
            Question(
                question_id=question_id,
                category=item.get("question_type", "unknown"),
                question=item["question"],
                gold_answer=str(item.get("answer", "")),
                sessions=sessions,
                session_ids=session_ids,
                evidence_session_ids=[
                    str(sid) for sid in item.get("answer_session_ids", [])
                ],
                question_date=str(item.get("question_date", "") or ""),
            )
        )
    return questions


def wipe_vault(vault_path: Path | str) -> None:
    """Empty the benchmark vault between questions (per-question isolation).

    Refuses obviously wrong targets: `/`, the home directory, or a path
    that does not already exist as a directory.
    """
    vault = Path(vault_path).resolve()
    if vault == Path("/") or vault == Path.home() or not vault.is_dir():
        raise ValueError(f"refusing to wipe suspicious vault path: {vault}")

    for child in vault.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    (vault / "raw").mkdir()
    (vault / "wiki").mkdir()
    (vault / "daily").mkdir()


def _make_complete(model: str, ledger: dict[str, int] | None = None):
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
        if ledger is not None and response.usage is not None:
            ledger["prompt"] = ledger.get("prompt", 0) + (
                response.usage.prompt_tokens or 0
            )
            ledger["completion"] = ledger.get("completion", 0) + (
                response.usage.completion_tokens or 0
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
        context_chars=config.cortex.context_chars,
    )
    ledger: dict[str, int] = {"prompt": 0, "completion": 0}
    answer_complete = _make_complete(config.models.answer, ledger)

    async def answer_fn(question: str, contexts: list[dict[str, Any]]) -> str:
        context_block = "\n\n---\n\n".join(
            f"[{c['path']}]\n{c['snippet']}" for c in contexts
        )
        return await answer_complete(
            ANSWER_SYSTEM_PROMPT, f"Context:\n{context_block}\n\nQuestion: {question}"
        )

    judge = Judge(
        complete=_make_complete(config.models.judge, ledger),
        judge_model=config.models.judge,
        answer_model=config.models.answer,
    )

    reset_fn = None
    if config.cortex.vault_path:
        vault_path = Path(config.cortex.vault_path)

        async def _wipe():
            wipe_vault(vault_path)

        reset_fn = _wipe

    index_fn = None
    if config.cortex.qmd_update_url:
        # Synchronous rescan + embed; generous timeout for embedding.
        qmd_client = httpx.AsyncClient(timeout=900.0)

        async def _reindex():
            response = await qmd_client.post(config.cortex.qmd_update_url)
            response.raise_for_status()

        index_fn = _reindex

    # Keep smoke-run artifacts apart from full-run (publishable) ones.
    run_name = config.name if limit is None else f"{config.name}-limit{limit}"
    out_dir = Path(config.output_dir) / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    traces_path = out_dir / "traces.jsonl"
    traces_path.write_text("")  # fresh run

    done = 0

    async def progress_reset():
        nonlocal done
        done += 1
        print(f"[{done}/{len(questions)}] {time.strftime('%H:%M:%S')}", flush=True)
        if reset_fn is not None:
            await reset_fn()

    async def persist_trace(trace):
        # Append immediately: a crash late in a long run loses nothing.
        with traces_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(trace), ensure_ascii=False) + "\n")
        print(
            f"  {trace.question_id}: {trace.judge_verdict}"
            f" (recall={trace.recall})",
            flush=True,
        )

    traces = await run_eval(
        questions,
        adapter,
        answer_fn,
        judge,
        reset_fn=progress_reset,
        index_fn=index_fn,
        usage_ledger=ledger,
        on_trace=persist_trace,
    )
    await adapter.aclose()

    write_traces(traces_path, traces)
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
