"""Blind human validation of the LLM judge.

An LLM judge alone is marketing; a judge whose agreement with blinded
human review is measured and published is evidence. This module produces
the blinded review set (no system names, no verdicts, no question ids)
plus a separate key file, and computes agreement (percent + Cohen's
kappa) once human labels come back.
"""
from __future__ import annotations

import random
import uuid
from typing import Any

from evals.traces import Trace


def sample_for_blind_review(
    traces: list[Trace], n: int, seed: int
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Deterministically sample traces for blinded human review.

    Returns (items, key): items carry only what a reviewer needs —
    question, gold answer, model answer — under a random review_id; the
    key maps review_id back to question_id, system, and judge verdict and
    must be kept away from reviewers until labels are in.
    """
    rng = random.Random(seed)
    sampled = rng.sample(traces, min(n, len(traces)))

    items: list[dict[str, Any]] = []
    key: dict[str, dict[str, Any]] = {}
    for trace in sampled:
        review_id = uuid.UUID(int=rng.getrandbits(128)).hex[:12]
        items.append(
            {
                "review_id": review_id,
                "question": trace.question,
                "gold_answer": trace.gold_answer,
                "answer": trace.answer,
            }
        )
        key[review_id] = {
            "question_id": trace.question_id,
            "system": trace.system,
            "judge_verdict": trace.judge_verdict,
        }
    return items, key


def agreement(
    key: dict[str, dict[str, Any]], human_labels: dict[str, str]
) -> dict[str, Any]:
    """Judge-vs-human agreement: percent, Cohen's kappa, disagreements."""
    pairs = [
        (key[rid]["judge_verdict"], label)
        for rid, label in human_labels.items()
        if rid in key
    ]
    if not pairs:
        return {"n": 0, "percent": None, "kappa": None, "disagreements": []}

    n = len(pairs)
    agreed = sum(1 for judge, human in pairs if judge == human)
    po = agreed / n

    labels = {label for pair in pairs for label in pair}
    pe = sum(
        (sum(1 for j, _ in pairs if j == label) / n)
        * (sum(1 for _, h in pairs if h == label) / n)
        for label in labels
    )
    if pe == 1.0:
        kappa = 1.0 if po == 1.0 else 0.0
    else:
        kappa = (po - pe) / (1 - pe)

    disagreements = [
        {
            "review_id": rid,
            "question_id": key[rid]["question_id"],
            "judge_verdict": key[rid]["judge_verdict"],
            "human_verdict": label,
        }
        for rid, label in human_labels.items()
        if rid in key and key[rid]["judge_verdict"] != label
    ]

    return {"n": n, "percent": po, "kappa": kappa, "disagreements": disagreements}
