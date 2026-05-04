---
title: "Attention Is All You Need"
tags: [ml, attention, nlp, transformer, deep-learning]
authored_by: markitdown
created_at: 2026-05-04T20:14:18Z
source_path: raw/attention-is-all-you-need-2017.txt
---

# Attention Is All You Need

Authors: Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N. Gomez, Łukasz Kaiser, Illia Polosukhin
Affiliation: Google Brain, Google Research, University of Toronto
Published: NIPS 2017

## Abstract

The dominant sequence transduction models are based on complex recurrent or convolutional neural networks. This paper proposes the [[transformer-architecture]], based solely on [[self-attention]] mechanisms, dispensing with recurrence and convolutions entirely.

## Key Architecture Components

1. **Encoder-Decoder Structure**: The encoder maps input sequences to continuous representations; the decoder generates output sequences auto-regressively.

2. **Encoder**: Stack of N=6 identical layers, each with [[multi-head-attention]] and position-wise [[feed-forward-network]]. Residual connections and [[layer-normalisation]] around each sub-layer.

3. **Decoder**: Stack of N=6 identical layers with masked [[multi-head-attention]], encoder-decoder attention, and position-wise [[feed-forward-network]].

4. **Scaled Dot-Product Attention**: `Attention(Q, K, V) = softmax(QK^T / sqrt(dk)) * V`

5. **[[multi-head-attention]]**: h=8 parallel attention heads with dk=dv=64, allowing the model to jointly attend to information from different representation subspaces.

6. **[[positional-encoding]]**: Sine and cosine functions of different frequencies to inject position information.

## Results

- EN-DE: 28.4 BLEU (big model), surpassing all previous models including ensembles
- EN-FR: 41.0 BLEU (big model), new single-model state-of-the-art
- Training cost: a fraction of previous best models

## Significance

First sequence transduction model based entirely on attention. Significantly faster training than recurrent/convolutional architectures. This work laid the foundation for [[large-language-models]] including GPT and BERT.
