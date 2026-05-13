---
title: Transformer Architecture
tags: [ml, architecture, attention, nlp, deep-learning]
authored_by: cortex-compiler
created_at: 2026-04-11T10:00:00Z
source_path: raw/transformer-paper.txt
---

# Transformer Architecture

The [[transformer]] model replaces recurrence entirely with [[self-attention]] mechanisms, enabling significantly faster training through parallelisation.

## Key Components

- **[[multi-head-attention]]**: parallel attention functions across representation subspaces
- **[[positional-encoding]]**: sine/cosine functions to inject sequence position information
- **[[feed-forward-network]]**: two linear transformations with ReLU activation
- **Residual connections + [[layer-normalisation]]**

## Core Formula

```
Attention(Q, K, V) = softmax(Q K^T / sqrt(d_k)) V
```

## Significance

The paper demonstrates that recurrence is not necessary for [[sequence-modelling]], achieving state-of-the-art results on [[machine-translation]] benchmarks with reduced training time. This architecture became the foundation for modern [[large-language-models]].


See also: Add a reference to 'Web2BigTable' under downstream applications or agentic systems to illustrate how LLMs (Transformers) are used as orchestrators in internet-scale information extraction.


See also: Add a mention of industrial applications of transformer-based models in large-scale codebase maintenance and migration, citing the Google 2025 paper on LLM-driven code migration.


See also: Add a 'Further Reading' or 'Modern Evolution' link to the Zhao et al. (2023) survey, which provides a detailed taxonomy of LLMs built upon the Transformer architecture.
