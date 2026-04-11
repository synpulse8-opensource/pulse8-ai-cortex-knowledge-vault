---
authored_by: claude-opus-4-6
created_at: '2026-04-11T19:29:50.133189+00:00'
source_path: raw/openfang-agent-os-2026.txt
tags:
- architecture
- agent-os
- rust
- orchestration
- open-source
title: OpenFang
updated_at: '2026-04-11T19:29:50.133178+00:00'
---

# OpenFang

OpenFang is an open-source Agent Operating System built entirely in Rust by Jaber (RightNow AI). It treats AI agents as autonomous OS-level processes with spawn, suspend, resume, and reclaim semantics — a fundamentally different paradigm from chatbot-wrapper frameworks.

## Architecture

The codebase spans 14 Rust crates and 137,728 lines of code, shipping as a single binary. The modular kernel design breaks down into five subsystems:

- **openfang-kernel**: Orchestration, workflows, metering, RBAC, scheduler, budget tracking
- **openfang-runtime**: Agent loop, 3 LLM drivers, 53 tools, WASM sandbox, MCP client+server, Google A2A
- **openfang-api**: 140+ REST/WS/SSE endpoints, OpenAI-compatible API, dashboard
- **openfang-channels**: 40 messaging adapters with rate limiting
- **openfang-memory**: SQLite-based persistent memory

## Performance

Self-reported benchmarks at v0.1.0 show 180ms cold starts (vs 3–6s for Python frameworks), ~40MB idle memory with linear ~12MB scaling per agent, and ~13x throughput on routing tasks compared to CrewAI and LangGraph.

## Security

16 discrete security layers including WASM dual-metered sandbox, Ed25519 manifest signing, Merkle audit trail, taint tracking, SSRF protection, prompt injection scanning, RBAC enforcement, and SHA256-based tool call loop detection with circuit breaker.

## Hands

Pre-built autonomous capability packages that run on schedules, build knowledge graphs, and report to a dashboard. Seven official Hands ship with v0.1.0: Clip, Lead, Collector, Predictor, Researcher, Twitter, and Browser. Custom Hands are defined via HAND.toml and published to FangHub.

## Protocol Support

Native support for [[Model Context Protocol]] (MCP) as both client and server, Google A2A for agent-to-agent delegation, and OpenFang Protocol for P2P networking. 27 LLM providers supported.

## Relevance to PULSE8.AI

OpenFang serves as the core runtime powering [[Keystone]], replacing LangGraph in the PULSE8.AI 2.0 architecture. Its kernel-level orchestration, WASM sandboxing, and MCP integration align with PULSE8.AI's requirements for enterprise-grade agentic AI in regulated BFSI environments. Key advantages for this use case: Rust performance characteristics, 16-layer security model suitable for [[Boundra]] compliance requirements, and the Hands paradigm for packaging domain-specific autonomous workflows.

## Current Status

v0.1.0 with 1,767+ passing tests. Breaking API changes expected before v1.0. Tool ecosystem approximately 15% of CrewAI's. Best suited for platform teams, edge deployments, and regulated industries.