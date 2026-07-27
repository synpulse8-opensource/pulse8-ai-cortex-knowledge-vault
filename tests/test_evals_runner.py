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
    def test_loads_questions_sessions_ids_and_evidence(self, tmp_path: Path):
        from evals.run_longmemeval import load_longmemeval

        dataset = [
            {
                "question_id": "lme-001",
                "question_type": "single-session-user",
                "question": "Where did I move in March?",
                "answer": "Zurich",
                "haystack_session_ids": ["sharegpt_abc_0", "answer_xyz"],
                "answer_session_ids": ["answer_xyz"],
                "haystack_sessions": [
                    [
                        {"role": "user", "content": "Some unrelated chat."},
                    ],
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
        # Sessions carry their dataset IDs so retrieval hits can be matched
        # against the labeled evidence sessions (recall@k).
        assert q.session_ids == ["sharegpt_abc_0", "answer_xyz"]
        assert q.evidence_session_ids == ["answer_xyz"]
        assert len(q.sessions) == 2
        assert "I moved to Zurich in March." in q.sessions[1]

    def test_loader_tolerates_missing_ids(self, tmp_path: Path):
        """Older/other dumps without ID fields still load (no recall labels)."""
        from evals.run_longmemeval import load_longmemeval

        dataset = [
            {
                "question_id": "lme-002",
                "question_type": "multi-session",
                "question": "q",
                "answer": "a",
                "haystack_sessions": [[{"role": "user", "content": "hi"}]],
            }
        ]
        f = tmp_path / "d.json"
        f.write_text(json.dumps(dataset))

        q = load_longmemeval(f)[0]
        assert q.session_ids == ["lme-002-session-000"]
        assert q.evidence_session_ids == []


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


class FakeAdapter:
    name = "fake-system"

    def __init__(self, retrieved=None):
        self.ingested = []
        self.events = []
        self._retrieved = retrieved or [
            {"path": "wiki/x.md", "snippet": "moved to Zurich in March"}
        ]

    async def ingest(self, filename, _content):
        self.ingested.append(filename)
        self.events.append(("ingest", filename))
        return {"status": "created"}

    async def retrieve(self, _question):
        return self._retrieved


def _make_judge():
    from evals.judge import Judge

    async def judge_complete(_system: str, _user: str) -> str:
        return "yes"

    return Judge(
        complete=judge_complete, judge_model="j-model", answer_model="a-model"
    )


async def _fake_answer(_question: str, contexts: list[dict]) -> str:
    assert contexts, "answerer must receive retrieved context"
    return "Zurich"


def _question(qid="lme-001", **kwargs):
    from evals.run_longmemeval import Question

    defaults = {
        "question_id": qid,
        "category": "single-session-user",
        "question": "Where did I move?",
        "gold_answer": "Zurich",
        "sessions": ["user: I moved to Zurich in March."],
        "session_ids": [f"{qid}-sess-a"],
    }
    defaults.update(kwargs)
    return Question(**defaults)


class TestVaultWipe:
    def test_wipe_clears_contents_and_recreates_layout(self, tmp_path: Path):
        from evals.run_longmemeval import wipe_vault

        vault = tmp_path / "vault"
        (vault / "raw").mkdir(parents=True)
        (vault / "wiki").mkdir()
        (vault / ".cortex").mkdir()
        (vault / "raw" / "a.md").write_text("x")
        (vault / "wiki" / "b.md").write_text("y")
        (vault / ".cortex" / "usage.json").write_text("{}")

        wipe_vault(vault)

        assert (vault / "raw").is_dir() and not list((vault / "raw").iterdir())
        assert (vault / "wiki").is_dir() and not list((vault / "wiki").iterdir())
        assert not (vault / ".cortex").exists()

    def test_wipe_refuses_suspicious_paths(self, tmp_path: Path):
        from evals.run_longmemeval import wipe_vault

        with pytest.raises(ValueError):
            wipe_vault(Path.home())
        with pytest.raises(ValueError):
            wipe_vault(Path("/"))
        # Nonexistent path is also refused rather than silently created.
        with pytest.raises(ValueError):
            wipe_vault(tmp_path / "does-not-exist")


class TestRunEval:
    @pytest.mark.asyncio
    async def test_run_eval_produces_judged_traces(self):
        from evals.runner import run_eval

        adapter = FakeAdapter()
        traces = await run_eval([_question()], adapter, _fake_answer, _make_judge())

        # Sessions are ingested under their dataset session IDs.
        assert adapter.ingested == ["lme-001-sess-a.md"]
        assert len(traces) == 1
        trace = traces[0]
        assert trace.system == "fake-system"
        assert trace.judge_verdict == "correct"
        assert trace.answer == "Zurich"
        assert trace.retrieved[0]["path"] == "wiki/x.md"
        assert set(trace.latency_ms) == {"retrieve", "answer", "judge"}

    @pytest.mark.asyncio
    async def test_reset_fn_called_before_each_question(self):
        """Per-question vault isolation: each question starts from a clean
        vault so its retrieval only sees its own haystack."""
        from evals.runner import run_eval

        adapter = FakeAdapter()

        async def reset():
            adapter.events.append(("reset", None))

        questions = [_question("q1"), _question("q2")]
        await run_eval(questions, adapter, _fake_answer, _make_judge(), reset_fn=reset)

        kinds = [kind for kind, _ in adapter.events]
        assert kinds == ["reset", "ingest", "reset", "ingest"]

    @pytest.mark.asyncio
    async def test_index_fn_called_between_ingest_and_retrieve(self):
        """The search index must be refreshed after a question's haystack is
        ingested and before its retrieval runs."""
        from evals.runner import run_eval

        adapter = FakeAdapter()
        original_retrieve = adapter.retrieve

        async def tracking_retrieve(question):
            adapter.events.append(("retrieve", None))
            return await original_retrieve(question)

        adapter.retrieve = tracking_retrieve

        async def index():
            adapter.events.append(("index", None))

        await run_eval(
            [_question("q1"), _question("q2")],
            adapter,
            _fake_answer,
            _make_judge(),
            index_fn=index,
        )
        kinds = [kind for kind, _ in adapter.events]
        assert kinds == ["ingest", "index", "retrieve"] * 2

    @pytest.mark.asyncio
    async def test_recall_computed_from_evidence_session_ids(self):
        from evals.runner import run_eval

        adapter = FakeAdapter(
            retrieved=[
                {"path": "wiki/answer_xyz.md", "snippet": "evidence hit"},
                {"path": "raw/other_1.md", "snippet": "noise"},
            ]
        )
        question = _question(
            sessions=["s1", "s2"],
            session_ids=["answer_xyz", "answer_abc"],
            evidence_session_ids=["answer_xyz", "answer_abc"],
        )
        (trace,) = await run_eval([question], adapter, _fake_answer, _make_judge())
        # One of two evidence sessions retrieved -> recall 0.5.
        assert trace.recall == 0.5

    @pytest.mark.asyncio
    async def test_recall_matches_slugified_wiki_paths(self):
        """Cortex kebab-cases filename stems when compiling raw -> wiki
        (answer_XYZ_1 -> answer-xyz-1.md); recall matching must too."""
        from evals.runner import run_eval

        adapter = FakeAdapter(
            retrieved=[{"path": "wiki/answer-280352e9.md", "snippet": "hit"}]
        )
        question = _question(
            sessions=["s1"],
            session_ids=["answer_280352E9"],
            evidence_session_ids=["answer_280352E9"],
        )
        (trace,) = await run_eval([question], adapter, _fake_answer, _make_judge())
        assert trace.recall == 1.0

    @pytest.mark.asyncio
    async def test_recall_none_without_evidence_labels(self):
        from evals.runner import run_eval

        (trace,) = await run_eval(
            [_question()], FakeAdapter(), _fake_answer, _make_judge()
        )
        assert trace.recall is None

    @pytest.mark.asyncio
    async def test_on_trace_streams_each_completed_trace(self):
        """Long runs persist traces as they complete (crash-safe)."""
        from evals.runner import run_eval

        streamed = []

        async def on_trace(trace):
            streamed.append(trace.question_id)

        traces = await run_eval(
            [_question("q1"), _question("q2")],
            FakeAdapter(),
            _fake_answer,
            _make_judge(),
            on_trace=on_trace,
        )
        assert streamed == ["q1", "q2"]
        assert len(traces) == 2

    @pytest.mark.asyncio
    async def test_token_usage_attributed_per_phase(self):
        """A shared ledger (incremented inside the LLM callables) is
        snapshotted around each phase, attributing tokens per question."""
        from evals.judge import Judge
        from evals.runner import run_eval

        ledger = {"prompt": 0, "completion": 0}

        async def counting_answer(_question, _contexts):
            ledger["prompt"] += 100
            ledger["completion"] += 10
            return "Zurich"

        async def counting_judge_complete(_system, _user):
            ledger["prompt"] += 50
            ledger["completion"] += 5
            return "yes"

        judge = Judge(
            complete=counting_judge_complete,
            judge_model="j-model",
            answer_model="a-model",
        )
        (trace,) = await run_eval(
            [_question()], FakeAdapter(), counting_answer, judge, usage_ledger=ledger
        )
        assert trace.tokens == {
            "answer_prompt": 100,
            "answer_completion": 10,
            "judge_prompt": 50,
            "judge_completion": 5,
        }
