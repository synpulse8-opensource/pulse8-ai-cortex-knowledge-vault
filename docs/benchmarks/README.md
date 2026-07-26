# Benchmarks

Published, blind-validated, reproducible evaluation of Cortex retrieval and
compilation quality. Design: [roadmap/plan-retrieval-benchmarks.md](../../roadmap/plan-retrieval-benchmarks.md).

## Status

No numbers published yet. The harness (`evals/`) is in place; the first
published configuration will be LongMemEval-S with hybrid search.

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
