"""Tests for the eval runner and LongMemEval dataset handling (all offline)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


class TestDatasetVerification:
    def test_verify_sha256_accepts_matching_file(self, tmp_path: Path):
        from evals.datasets.download import verify_sha256

        f = tmp_path / "data.json"
        f.write_bytes(b'{"ok": true}')
        digest = hashlib.sha256(b'{"ok": true}').hexdigest()
        verify_sha256(f, digest)  # must not raise

    def test_verify_sha256_rejects_mismatch(self, tmp_path: Path):
        from evals.datasets.download import verify_sha256

        f = tmp_path / "data.json"
        f.write_bytes(b"tampered")
        with pytest.raises(ValueError, match="SHA-256"):
            verify_sha256(f, "0" * 64)


class TestLongMemEvalLoader:
    def test_loads_questions_and_sessions(self, tmp_path: Path):
        from evals.run_longmemeval import load_longmemeval

        dataset = [
            {
                "question_id": "lme-001",
                "question_type": "single-session-user",
                "question": "Where did I move in March?",
                "answer": "Zurich",
                "haystack_sessions": [
                    [
                        {"role": "user", "content": "I moved to Zurich in March."},
                        {"role": "assistant", "content": "Congratulations!"},
                    ],
                ],
            }
        ]
        f = tmp_path / "longmemeval_s.json"
        f.write_text(json.dumps(dataset))

        questions = load_longmemeval(f)
        assert len(questions) == 1
        q = questions[0]
        assert q.question_id == "lme-001"
        assert q.category == "single-session-user"
        assert q.gold_answer == "Zurich"
        assert len(q.sessions) == 1
        assert "I moved to Zurich in March." in q.sessions[0]


class TestLimit:
    def test_limit_takes_first_n_questions(self, tmp_path: Path):
        """--limit N enables a cheap smoke run before spending on a full one."""
        from evals.run_longmemeval import load_longmemeval

        dataset = [
            {
                "question_id": f"lme-{i:03d}",
                "question_type": "single-session-user",
                "question": f"q{i}",
                "answer": f"a{i}",
                "haystack_sessions": [],
            }
            for i in range(10)
        ]
        f = tmp_path / "d.json"
        f.write_text(json.dumps(dataset))

        questions = load_longmemeval(f, limit=3)
        assert [q.question_id for q in questions] == ["lme-000", "lme-001", "lme-002"]
        assert len(load_longmemeval(f)) == 10  # no limit -> everything


class TestRunEval:
    @pytest.mark.asyncio
    async def test_run_eval_produces_judged_traces(self):
        from evals.judge import Judge
        from evals.run_longmemeval import Question
        from evals.runner import run_eval

        class FakeAdapter:
            name = "fake-system"

            def __init__(self):
                self.ingested = []

            async def ingest(self, filename, _content):
                self.ingested.append(filename)
                return {"status": "created"}

            async def retrieve(self, _question):
                return [{"path": "wiki/x.md", "snippet": "moved to Zurich in March"}]

        async def fake_answer(_question: str, contexts: list[dict]) -> str:
            assert contexts, "answerer must receive retrieved context"
            return "Zurich"

        async def judge_complete(_system: str, _user: str) -> str:
            return "yes"

        judge = Judge(
            complete=judge_complete, judge_model="j-model", answer_model="a-model"
        )
        questions = [
            Question(
                question_id="lme-001",
                category="single-session-user",
                question="Where did I move?",
                gold_answer="Zurich",
                sessions=["user: I moved to Zurich in March."],
            )
        ]

        adapter = FakeAdapter()
        traces = await run_eval(questions, adapter, fake_answer, judge)

        assert adapter.ingested == ["lme-001-session-000.md"]
        assert len(traces) == 1
        trace = traces[0]
        assert trace.system == "fake-system"
        assert trace.judge_verdict == "correct"
        assert trace.answer == "Zurich"
        assert trace.retrieved[0]["path"] == "wiki/x.md"
        assert set(trace.latency_ms) == {"retrieve", "answer", "judge"}
