---
name: cortex-contributing
description: >-
  Contributing to Cortex — tests, adding MCP tools, conventions, AGENTS.md and
  skills maintenance. Use when extending the codebase or opening a PR.
---

# Contributing to Cortex

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Example vault: `example_vault/` (or set `VAULT_PATH`).

## Test layout

| Area | Path |
|------|------|
| API | `tests/test_api.py` |
| MCP | `tests/test_mcp.py` |
| Feedback | `tests/test_feedback.py` |
| Teams | `tests/test_teams_notify.py` |
| Graph | `tests/test_graph*.py` |

Run focused: `pytest tests/test_feedback.py -v`

## Adding an MCP tool

1. Implement handler in `cortex/mcp/tools.py`
2. Register in `cortex/mcp/http_server.py` and `cortex/mcp/server.py`
3. Add REST route in `cortex/api/routes.py` if mirrored
4. Tests in `tests/test_mcp.py` (+ `test_api.py` if REST)
5. Update `.cursor/skills/cortex-mcp/reference.md` and README MCP table
6. Mention in `AGENTS.md` skill index if user-facing

## Code conventions

- Match existing logging: `logger = logging.getLogger(__name__)`
- Config via `get_settings()` from `cortex/config.py`
- Vault paths always relative to vault root
- Minimize scope; no drive-by refactors

## Agent documentation

| File | Purpose |
|------|---------|
| `AGENTS.md` | Always-on repo map for agents |
| `.cursor/skills/cortex/SKILL.md` | Master router skill |
| `.cursor/skills/cortex-*/SKILL.md` | Topic skills |

Do **not** install project skills under `~/.cursor/skills-cursor/` (reserved for Cursor built-ins).

## Pre-commit / CI

Follow project hooks if configured. Fix test failures before claiming done.

## Related skills

- Master index: `cortex`
- Full spec: `docs/superpowers/specs/2026-05-29-cursor-skills-design.md`
