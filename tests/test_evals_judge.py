"""Tests for the LLM judge: injected model callable, strict verdict parsing."""
from __future__ import annotations

import pytest


def _judge_with_reply(reply: str):
    from evals.judge import Judge

    captured = {}

    async def fake_complete(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return reply

    judge = Judge(
        complete=fake_complete,
        judge_model="openai/gpt-4o",
        answer_model="anthropic/claude-sonnet-4",
    )
    return judge, captured


def test_judge_rejects_same_model_as_answerer():
    from evals.judge import Judge

    async def fake_complete(_system: str, _user: str) -> str:
        return "yes"

    with pytest.raises(ValueError, match="judge"):
        Judge(
            complete=fake_complete,
            judge_model="anthropic/claude-sonnet-4",
            answer_model="anthropic/claude-sonnet-4",
        )


@pytest.mark.asyncio
async def test_yes_reply_is_correct():
    judge, captured = _judge_with_reply("yes, the answer matches the gold answer.")
    result = await judge.judge(
        question="When did the user move to Zurich?",
        gold="March 2025",
        hypothesis="The user moved in March 2025.",
    )
    assert result["verdict"] == "correct"
    assert "March 2025" in captured["user"]
    assert "When did the user move to Zurich?" in captured["user"]


@pytest.mark.asyncio
async def test_no_reply_is_incorrect():
    judge, _ = _judge_with_reply("No. The hypothesis contradicts the gold answer.")
    result = await judge.judge(question="q", gold="g", hypothesis="h")
    assert result["verdict"] == "incorrect"


@pytest.mark.asyncio
async def test_unparseable_reply_is_error_not_a_guess():
    """A judge that can't parse must say so, never silently guess."""
    judge, _ = _judge_with_reply("The answer is somewhat aligned, arguably.")
    result = await judge.judge(question="q", gold="g", hypothesis="h")
    assert result["verdict"] == "error"
    assert result["raw"].startswith("The answer is somewhat")
