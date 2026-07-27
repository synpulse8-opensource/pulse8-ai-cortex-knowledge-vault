"""Tests for blind human validation of the LLM judge."""
from __future__ import annotations


def _trace(i: int, verdict: str):
    from evals.traces import Trace

    return Trace(
        question_id=f"q-{i:03d}",
        category="temporal",
        question=f"question {i}",
        gold_answer=f"gold {i}",
        system="cortex-hybrid",
        answer=f"answer {i}",
        judge_verdict=verdict,
    )


class TestBlindSampling:
    def test_blinded_items_carry_no_identifiers(self):
        from evals.blind import sample_for_blind_review

        traces = [_trace(i, "correct") for i in range(20)]
        items, key = sample_for_blind_review(traces, n=5, seed=42)

        assert len(items) == 5
        for item in items:
            assert set(item) == {"review_id", "question", "gold_answer", "answer"}
        # The key file, kept separate, maps back to system and verdict.
        assert len(key) == 5
        for review_id, entry in key.items():
            assert entry["system"] == "cortex-hybrid"
            assert entry["judge_verdict"] == "correct"
            assert any(i["review_id"] == review_id for i in items)

    def test_sampling_is_deterministic_per_seed(self):
        from evals.blind import sample_for_blind_review

        traces = [_trace(i, "correct") for i in range(50)]
        items_a, _ = sample_for_blind_review(traces, n=10, seed=7)
        items_b, _ = sample_for_blind_review(traces, n=10, seed=7)
        items_c, _ = sample_for_blind_review(traces, n=10, seed=8)

        assert [i["question"] for i in items_a] == [i["question"] for i in items_b]
        assert [i["question"] for i in items_a] != [i["question"] for i in items_c]


class TestAgreement:
    def test_perfect_agreement(self):
        from evals.blind import agreement

        key = {
            "r1": {"question_id": "q-001", "judge_verdict": "correct", "system": "s"},
            "r2": {"question_id": "q-002", "judge_verdict": "incorrect", "system": "s"},
        }
        result = agreement(key, {"r1": "correct", "r2": "incorrect"})
        assert result["percent"] == 1.0
        assert result["kappa"] == 1.0
        assert result["disagreements"] == []

    def test_partial_agreement_reports_kappa_and_disagreements(self):
        from evals.blind import agreement

        # Judge: correct, correct, incorrect, incorrect
        # Human: correct, incorrect, incorrect, correct  -> 50% agreement
        key = {
            f"r{i}": {"question_id": f"q-{i}", "judge_verdict": v, "system": "s"}
            for i, v in enumerate(["correct", "correct", "incorrect", "incorrect"])
        }
        human = {"r0": "correct", "r1": "incorrect", "r2": "incorrect", "r3": "correct"}
        result = agreement(key, human)

        assert result["percent"] == 0.5
        # po=0.5, pe=0.5 -> kappa = 0 (agreement no better than chance).
        assert result["kappa"] == 0.0
        assert len(result["disagreements"]) == 2
        assert {d["review_id"] for d in result["disagreements"]} == {"r1", "r3"}
