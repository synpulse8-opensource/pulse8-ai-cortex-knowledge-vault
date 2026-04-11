---
title: Transformer Architecture
tags: [ml, architecture, attention, nlp]
authored_by: claude-sonnet-4-20250514
created_at: 2026-04-11T10:00:00Z
source_path: raw/transformer-paper.txt
---

# Transformer Architecture

The transformer model replaces recurrence entirely with self-attention mechanisms.

## Key Components

- **Multi-head attention**: parallel attention functions across subspaces
- **Positional encoding**: sine/cosine position injection
- **Feed-forward layers**: two linear transforms with ReLU
- **Residual connections + layer norm**

## Core Claim

Recurrence is not necessary for sequence modeling. This contradicts [[rnn-claims]].

See also: [[attention-mechanisms]]
