# Retrieval Benchmarks: Published, Blind-Validated, Reproducible

**Status:** In progress — harness scaffolding under TDD
**Created:** 2026-07-26
**Supersedes:** Phase 6 of [completed/plan-enterprise-auditable-vault.md](completed/plan-enterprise-auditable-vault.md)

## Framing

Cortex has a feature table but zero published evidence that its retrieval or
compilation quality is good. For a knowledge system, unbenchmarked is the same
as unproven. The goal is what graphify achieved: published numbers on public
benchmarks, blind-validated judging, and one-command reproduction. One honest
number converts more enterprise architects than any feature table.

Three principles drive every decision below:

1. **The reproduction command is the product.** Anyone must be able to rerun a
   published configuration from a fresh clone.
2. **Blind validation is what makes numbers convert.** An LLM judge alone is
   marketing; an LLM judge whose agreement with blinded human review is
   measured and published is evidence.
3. **Publish the losses.** Per-category results including weak categories,
   costs, latency, and an ablation showing whether the graph actually helps.

## Benchmark selection

| Benchmark | Why | Order |
|---|---|---|
| **LongMemEval** (~500 questions, multi-session histories) | Public dataset with official judge prompts; tests extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention. Zep / Mem0 / graphify publish comparable numbers. | 1st |
| **LOCOMO** | The benchmark everyone compares on — but it has known dataset-quality issues and a history of vendor disputes (Mem0 vs Zep). Never publish a competitor comparison unless we reran their system ourselves with published configs, or we cite their self-reported numbers clearly labeled as such. | 2nd (reuses ~80% of harness) |
| **Regulatory-corpus retrieval eval** (custom, public corpus: EUR-Lex MiFID II + delegated acts, or EBA guidelines) | Matches the actual buyer. Generated questions with grounded citations, human-verified sample. Metrics: Recall@k, nDCG@10, citation faithfulness. Exercises `vault_path` / `vault_impact` in ways conversational benchmarks cannot. No memory-tool competitor has a BFSI-native number. | 3rd (highest lift, highest strategic value) |

## How Cortex runs a conversational-memory benchmark

Ingest each session as a raw source → compiler builds wiki + graph → answer
questions via `vault_search` / `vault_context` → answer model produces a
response from retrieved context → judge model scores it against gold.

## Harness architecture (`evals/`, not shipped in the wheel)

```
evals/
  __init__.py
  config.py           # EvalConfig: pinned models, modes, seeds, dataset SHA
  traces.py           # per-question Trace records, JSONL write/read
  adapters/
    base.py           # SystemAdapter protocol: ingest / retrieve / name
    cortex.py         # CortexAdapter over REST (httpx)
    baseline.py       # naive RAG (no graph) for the ablation
  judge.py            # official judge prompts; injected LLM callable;
                      # enforces judge model != answer model
  report.py           # per-category aggregation + markdown tables
  blind.py            # blind-review sampling (identifiers stripped) +
                      # agreement metrics (percent, Cohen's kappa)
  datasets/
    download.py       # pinned URL + SHA-256 verification; data never committed
  run_longmemeval.py  # thin runner over run_eval(config, adapter, judge, ...)
  configs/
    longmemeval-s-hybrid.yaml
```

Design constraints:

- **No API spend in tests.** The judge takes an injected `complete` callable;
  adapters are tested against `httpx.MockTransport`. The full unit suite runs
  offline.
- **Everything pinned.** A config names the Cortex version, `QMD_SEARCH_MODE`,
  compiler/answer/judge models, seed, and dataset SHA-256. A published run is
  a config file plus a traces artifact.
- **Raw traces are published.** Per-question JSONL (question, retrieved
  context, answer, judge verdict, tokens, latency) ships as a release
  artifact so every judgment is auditable.

## Reproduction command (the deliverable)

```bash
./scripts/start.sh
uv run python -m evals.run_longmemeval --config evals/configs/longmemeval-s-hybrid.yaml
```

## Blind-validation protocol

1. Judge model ≠ answer model (enforced by config validation) to blunt
   self-preference bias.
2. Sample ~100 judged items, strip all system/run identifiers, human-label
   them without knowing which system produced each answer.
3. Publish agreement (percent + Cohen's kappa) and the disagreement cases
   verbatim in the methodology page.

## Honesty rules

- Per-category results, including losses. Abstention and temporal reasoning
  are where document-vault architectures typically struggle — say so.
- Cost and latency next to accuracy: tokens per question, wall-clock per
  phase.
- Ablation: Cortex with graph context vs plain QMD search vs naive RAG on raw
  files. If the graph doesn't move the number, we want to know first.
- Contamination caveat: the answer model may have seen the corpus in
  pretraining; state it rather than waiting to be asked.

## Publishing

- `docs/benchmarks/` — methodology page + results tables per configuration.
- README gets a small results table linking there.
- Release artifacts: traces JSONL + config per published run.

## Effort estimate

- LongMemEval harness + first published configuration: ~1 week focused work,
  $50–200 API cost per full run depending on models.
- LOCOMO: incremental (~80% harness reuse).
- Regulatory eval: largest lift (dataset construction + human verification).

## Out of scope (for now)

- Code-task benchmarks (graphify's home turf, not Cortex's claim).
- Competitor reruns — only after our own numbers are stable.
