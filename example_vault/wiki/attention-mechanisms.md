---
title: Attention Mechanisms
tags: [ml, attention, deep-learning]
authored_by: claude-sonnet-4-20250514
created_at: 2026-04-11T10:00:00Z
source_path: raw/transformer-paper.txt
---

# Attention Mechanisms

Attention allows a model to focus on relevant parts of the input when producing output.

## Scaled Dot-Product Attention

$$\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V$$

## Multi-Head Attention

Multiple attention heads run in parallel, each learning different representation subspaces.

Related: [[transformers]]
