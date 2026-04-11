---
authored_by: google/gemini-3-flash-preview
created_at: '2026-04-11'
model: google/gemini-3-flash-preview
source_path: raw/meeting-2026-04-11.txt
tags:
- pipeline
- llm
- automation
- data-processing
title: Knowledge Compiler Pipeline
updated_at: '2026-04-11T19:08:01.297870+00:00'
---

# Knowledge Compiler Pipeline

The Knowledge Compiler is the automated process responsible for transforming raw data into structured assets within the [[Cortex Architecture]].

## Workflow
1. **Extraction**: Monitoring raw source directories (e.g., meeting notes, transcripts, or research papers).
2. **Synthesis**: Utilizing an LLM (specifically Claude) to identify key entities, claims, and links.
3. **Wiki Generation**: Producing structured Markdown files featuring YAML frontmatter and [[wikilinks]].

## Technical Implementation
- **Backend**: Python-based automation.
- **Intelligence**: Claude-powered synthesis.
- **Output**: Markdown files stored in the local filesystem, indexed for [[QMD]] search.