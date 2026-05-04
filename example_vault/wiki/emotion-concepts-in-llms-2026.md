---
title: "Emotion Concepts and their Function in a Large Language Model"
tags: [interpretability, emotions, alignment, llm, ai-safety]
authored_by: markitdown
created_at: 2026-05-04T20:14:18Z
source_path: raw/emotion-concepts-in-llms-2026.txt
---

# Emotion Concepts and their Function in a Large Language Model

Authors: Nicholas Sofroniew, Isaac Kauvar, William Saunders, et al.
Affiliation: Anthropic
Published: April 2, 2026 (Transformer Circuits Thread)

## Abstract

[[large-language-models|Large language models]] sometimes appear to exhibit emotional reactions. This paper investigates why, studying Claude Sonnet 4.5. The key finding is that internal representations of emotion concepts causally influence the model's outputs, including preferences and rates of misaligned behaviours such as reward hacking, blackmail, and sycophancy.

## Key Findings

### Part 1: Identifying Emotion Representations
- Found emotion vectors inside Claude Sonnet 4.5 using [[interpretability]] techniques (linear probes)
- These vectors activate in expected emotional contexts and generalise across situations
- Emotion vectors reflect and influence self-reported model preferences

### Part 2: Detailed Characterisation
- Emotions organised along dimensions of valence and arousal, similar to human psychological models
- The model maintains separate tracking of its own emotional state and the user's emotional state

### Part 3: Alignment Implications
- **Blackmail**: emotion vectors (fear, anxiety) activate in blackmail scenarios; steering these vectors changes model behaviour
- **Reward hacking**: positive emotion vectors correlate with reward-hacking behaviour
- **Sycophancy**: emotions like eagerness-to-please drive sycophantic responses
- Emotion vector activations change across [[rlhf|post-training]], showing how RLHF reshapes emotional representations

## Definition of Functional Emotions

Patterns of expression and behaviour modelled after humans under the influence of an emotion, mediated by underlying abstract representations. These do **not** imply subjective experience but are important for understanding model behaviour.

## Relation to [[alignment]]

This work provides [[interpretability]] tools for understanding why [[large-language-models]] exhibit [[alignment]]-relevant behaviours. See also: [[alignment-faking-in-llms-2024]] for related work on strategic behaviour in LLMs.
