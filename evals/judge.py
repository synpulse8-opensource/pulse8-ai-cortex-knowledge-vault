"""LLM-as-judge with strict verdict parsing.

The judge model is injected as a plain async callable so the unit suite
runs offline, and it must differ from the answer model (self-preference
bias). Verdict parsing is strict: replies that don't start with yes/no
become "error" — the judge never silently guesses.

The prompt follows the LongMemEval QA-correctness style (binary yes/no
against a gold answer); blind human validation of a judged sample is
handled separately in evals.blind.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

JUDGE_SYSTEM_PROMPT = (
    "You are an impartial grader. Given a question, a gold answer, and a "
    "model response, decide whether the response is correct.\n"
    "A response is correct if it contains the gold answer's information, "
    "even if worded differently or with extra detail. It is incorrect if "
    "it contradicts the gold answer, omits the asked-for information, or "
    "answers a different question.\n"
    "Reply with exactly one word first: 'yes' if correct, 'no' if not, "
    "optionally followed by a short justification."
)

JUDGE_USER_TEMPLATE = (
    "Question: {question}\n\n"
    "Gold answer: {gold}\n\n"
    "Model response: {hypothesis}\n\n"
    "Is the model response correct? Answer 'yes' or 'no' first."
)


class Judge:
    """Scores hypotheses against gold answers via an injected LLM callable."""

    def __init__(
        self,
        complete: Callable[[str, str], Awaitable[str]],
        judge_model: str,
        answer_model: str,
    ) -> None:
        if judge_model == answer_model:
            raise ValueError(
                "judge model must differ from answer model to blunt "
                "self-preference bias"
            )
        self._complete = complete
        self.judge_model = judge_model
        self.answer_model = answer_model

    async def judge(
        self, question: str, gold: str, hypothesis: str
    ) -> dict[str, Any]:
        """Return {"verdict": correct|incorrect|error, "raw": judge reply}."""
        raw = await self._complete(
            JUDGE_SYSTEM_PROMPT,
            JUDGE_USER_TEMPLATE.format(
                question=question, gold=gold, hypothesis=hypothesis
            ),
        )
        return {"verdict": _parse_verdict(raw), "raw": raw}


def _parse_verdict(raw: str) -> str:
    first_word = raw.strip().split(None, 1)[0].lower().strip(".,:;!") if raw.strip() else ""
    if first_word == "yes":
        return "correct"
    if first_word == "no":
        return "incorrect"
    return "error"
