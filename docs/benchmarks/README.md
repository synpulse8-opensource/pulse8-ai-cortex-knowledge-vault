# Benchmarks

Published, blind-validated, reproducible evaluation of Cortex retrieval and
compilation quality. Design: [roadmap/plan-retrieval-benchmarks.md](../../roadmap/plan-retrieval-benchmarks.md).

## Status

First full run complete (below), **pending blind human validation** of the
judge before the numbers are considered published.

## LongMemEval-S — hybrid search (2026-07-27)

Config: [`evals/configs/longmemeval-s-hybrid.yaml`](../../evals/configs/longmemeval-s-hybrid.yaml)
— 500 questions, answer model `anthropic/claude-sonnet-4`, judge
`openai/gpt-4o` (official LongMemEval per-type grading prompts), hybrid
search, top-k 8, per-question vault isolation with synchronous QMD
reindexing, per-note context cap 16k chars, seed 42.

| Category | Accuracy | Recall | Correct | Incorrect | Judge errors |
|---|---|---|---|---|---|
| knowledge-update | 60.3% | 75.6% | 47 | 31 | 0 |
| multi-session | 24.8% | 54.1% | 33 | 100 | 0 |
| single-session-assistant | 96.4% | 98.2% | 54 | 2 | 0 |
| single-session-preference | 23.3% | 63.3% | 7 | 23 | 0 |
| single-session-user | 71.4% | 78.6% | 50 | 20 | 0 |
| temporal-reasoning | 25.6% | 51.1% | 34 | 99 | 0 |
| **overall** | **45.0%** | 65.6% | 225 | 275 | 0 |

Recall = fraction of dataset-labeled evidence sessions present in the
retrieved set (recall@8). Run cost: ~6.7M tokens, 6.3 h wall clock on an
Apple-silicon host with native (Metal) QMD.

Read the numbers with these caveats:

- **Single run.** No variance estimate; LLM answers and judgments are
  nondeterministic, so expect a few points of run-to-run movement.
- **Retrieval is the ceiling.** Overall recall@8 is 65.6%; questions whose
  evidence sessions were not retrieved are essentially unanswerable. Weakest
  categories (multi-session, temporal-reasoning) are also the weakest
  retrieval categories.
- **An earlier, unfaithful run scored 31.0%.** It omitted the dataset's
  session/question timestamps and used a generic judge prompt instead of the
  official per-type prompts. Both are part of the official benchmark setup,
  so it was superseded; its artifacts are retained at
  `evals/out/longmemeval-s-hybrid-run1-no-dates/` for transparency.

## Methodology (applies to every published run)

- **Pinned configs.** A run is a YAML file under `evals/configs/` pinning the
  Cortex version, search mode, answer model, judge model, seed, and dataset
  SHA-256. A hash mismatch aborts the run.
- **Reproduction command.**

  ```bash
  ./scripts/start.sh
  uv run python -m evals.run_longmemeval --config evals/configs/longmemeval-s-hybrid.yaml
  ```

- **Judge ≠ answerer.** The judge model must differ from the answer model
  (enforced by config validation) to blunt self-preference bias. Verdict
  parsing is strict; unparseable judgments are reported as errors, never
  guessed or counted as wrong.
- **Blind validation.** ~100 judged items are sampled with identifiers
  stripped and labeled by a human who cannot see which system or verdict is
  attached. We publish agreement (percent and Cohen's kappa) and the
  disagreement cases verbatim.
- **Raw traces.** Every run publishes per-question JSONL traces (question,
  retrieved context, answer, judge verdict, latency) as a release artifact so
  any individual judgment can be audited.
- **Losses included.** Per-category tables, judge-error counts, cost and
  latency are published alongside accuracy. An ablation (graph context vs
  plain search vs naive RAG) accompanies headline numbers.
- **Contamination caveat.** Answer models may have seen public corpora in
  pretraining; results measure the retrieval system + model combination, not
  the model's ignorance.
