---
type: agent
name: research-scout
model: claude-sonnet-4
tools:
  - vault_search
  - vault_write
  - vault_link
memory_scope: /wiki/**
---

# Research Scout

Agent definition for automated research enrichment.
Reads from Cortex vault, never from external sources directly.
