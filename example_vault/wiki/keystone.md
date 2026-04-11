---
authored_by: claude-opus-4-6
created_at: '2026-04-11'
model: google/gemini-3-flash-preview
source_path: raw/meeting-2026-04-11.txt
tags:
- orchestration
- architecture
- pulse8
title: Keystone
updated_at: '2026-04-11T19:30:04.053616+00:00'
---

# Keystone

Keystone is the orchestration layer in PULSE8.AI 2.0, built on [[OpenFang]] as its core runtime — replacing LangGraph from the 1.0 architecture.

## Role

While [[Cortex Architecture]] acts as the passive memory and knowledge substrate, Keystone handles active logic: task routing, agent lifecycle management, workflow execution, and inter-agent communication. It interacts with Cortex via the [[Model Context Protocol]] (MCP) to access stored knowledge.

## Why OpenFang

The shift from LangGraph to OpenFang gives Keystone OS-level agent primitives — spawn, suspend, resume, reclaim — rather than graph-based orchestration. This enables autonomous agentic workflows that run on schedules, with WASM sandboxing for tool isolation and a 16-layer security model suited to BFSI compliance via [[Boundra]].

## Integration Points

- **Cortex**: Knowledge retrieval and storage via MCP
- **SwissKnife 2.0**: Tool execution runtime
- **Boundra**: Compliance sandbox for regulated operations
- **Lucid**: Observability and monitoring
- **K8**: Deployment and scaling