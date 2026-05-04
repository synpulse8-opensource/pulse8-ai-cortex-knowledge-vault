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
