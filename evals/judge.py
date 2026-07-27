"""LLM-as-judge with strict verdict parsing.

The judge model is injected as a plain async callable so the unit suite
runs offline, and it must differ from the answer model (self-preference
bias). Verdict parsing is strict: replies that don't start with yes/no
become "error" — the judge never silently guesses.

Grading prompts are LongMemEval's official per-type templates, verbatim
from src/evaluation/evaluate_qa.py (get_anscheck_prompt), so results are
comparable with published numbers; blind human validation of a judged
sample is handled separately in evals.blind.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

JUDGE_SYSTEM_PROMPT = (
    "You are an impartial grader. Reply with exactly one word first: "
    "'yes' or 'no'."
)

# Official LongMemEval grading templates (verbatim). Placeholders:
# question, gold answer (or rubric/explanation), model response.
_DEFAULT_TEMPLATE = (
    "I will give you a question, a correct answer, and a response from a "
    "model. Please answer yes if the response contains the correct answer. "
    "Otherwise, answer no. If the response is equivalent to the correct "
    "answer or contains all the intermediate steps to get the correct "
    "answer, you should also answer yes. If the response only contains a "
    "subset of the information required by the answer, answer no. "
    "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
    "Is the model response correct? Answer yes or no only."
)

_TEMPORAL_TEMPLATE = (
    "I will give you a question, a correct answer, and a response from a "
    "model. Please answer yes if the response contains the correct answer. "
    "Otherwise, answer no. If the response is equivalent to the correct "
    "answer or contains all the intermediate steps to get the correct "
    "answer, you should also answer yes. If the response only contains a "
    "subset of the information required by the answer, answer no. In "
    "addition, do not penalize off-by-one errors for the number of days. "
    "If the question asks for the number of days/weeks/months, etc., and "
    "the model makes off-by-one errors (e.g., predicting 19 days when the "
    "answer is 18), the model's response is still correct. "
    "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
    "Is the model response correct? Answer yes or no only."
)

_KNOWLEDGE_UPDATE_TEMPLATE = (
    "I will give you a question, a correct answer, and a response from a "
    "model. Please answer yes if the response contains the correct answer. "
    "Otherwise, answer no. If the response contains some previous "
    "information along with an updated answer, the response should be "
    "considered as correct as long as the updated answer is the required "
    "answer.\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}"
    "\n\nIs the model response correct? Answer yes or no only."
)

_PREFERENCE_TEMPLATE = (
    "I will give you a question, a rubric for desired personalized "
    "response, and a response from a model. Please answer yes if the "
    "response satisfies the desired response. Otherwise, answer no. The "
    "model does not need to reflect all the points in the rubric. The "
    "response is correct as long as it recalls and utilizes the user's "
    "personal information correctly.\n\nQuestion: {}\n\nRubric: {}\n\n"
    "Model Response: {}\n\nIs the model response correct? "
    "Answer yes or no only."
)

_ABSTENTION_TEMPLATE = (
    "I will give you an unanswerable question, an explanation, and a "
    "response from a model. Please answer yes if the model correctly "
    "identifies the question as unanswerable. The model could say that the "
    "information is incomplete, or some other information is given but the "
    "asked information is not.\n\nQuestion: {}\n\nExplanation: {}\n\n"
    "Model Response: {}\n\nDoes the model correctly identify the question "
    "as unanswerable? Answer yes or no only."
)

_TEMPLATES_BY_CATEGORY = {
    "temporal-reasoning": _TEMPORAL_TEMPLATE,
    "knowledge-update": _KNOWLEDGE_UPDATE_TEMPLATE,
    "single-session-preference": _PREFERENCE_TEMPLATE,
}


def anscheck_prompt(
    question: str,
    gold: str,
    hypothesis: str,
    category: str = "",
    question_id: str = "",
) -> str:
    """Official LongMemEval grading prompt for one hypothesis.

    Question IDs carrying an ``_abs`` suffix mark abstention questions,
    graded on whether the model recognized unanswerability.
    """
    if "_abs" in question_id:
        template = _ABSTENTION_TEMPLATE
    else:
        template = _TEMPLATES_BY_CATEGORY.get(category, _DEFAULT_TEMPLATE)
    return template.format(question, gold, hypothesis)


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
        self,
        question: str,
        gold: str,
        hypothesis: str,
        category: str = "",
        question_id: str = "",
    ) -> dict[str, Any]:
        """Return {"verdict": correct|incorrect|error, "raw": judge reply}."""
        raw = await self._complete(
            JUDGE_SYSTEM_PROMPT,
            anscheck_prompt(question, gold, hypothesis, category, question_id),
        )
        return {"verdict": _parse_verdict(raw), "raw": raw}


def _parse_verdict(raw: str) -> str:
    first_word = raw.strip().split(None, 1)[0].lower().strip(".,:;!") if raw.strip() else ""
    if first_word == "yes":
        return "correct"
    if first_word == "no":
        return "incorrect"
    return "error"
