---
authored_by: google/gemini-3-flash-preview
created_at: '2026-04-11'
model: google/gemini-3-flash-preview
source_path: raw/meeting-2026-04-11.txt
tags:
- architecture
- knowledge-management
- mcp
- design-decisions
title: Cortex Architecture
updated_at: '2026-04-11T19:08:01.291573+00:00'
---

# Cortex Architecture

Cortex is designed as a **passive knowledge substrate** rather than an active agent or orchestrator. Its primary function is the structured storage and retrieval of information to support higher-level systems.

## Core Principles
- **Separation of Concerns**: Cortex focuses strictly on knowledge storage and retrieval. Orchestration logic is deferred to [[Keystone]].
- **Filesystem-First**: The system avoids traditional databases, utilizing a filesystem-based approach with JSON graph persistence for metadata and relationships.
- **Search Strategy**: Rather than building custom search infrastructure, Cortex integrates [[QMD]] for local hybrid search capabilities.
- **LLM-Native Compilation**: Raw data is processed into curated wiki articles using an [[LLM-powered Knowledge Compiler]].

## Interface and Integration
The primary interface for Cortex is the [[Model Context Protocol]] (MCP) tool surface. The initial implementation includes a server providing seven tools, with core functionality centered on:
- `vault:read`
- `vault:write`
- `vault:search`

## Deployment
Cortex is designed to be containerized using **Docker** for consistent environment management across different infrastructures.