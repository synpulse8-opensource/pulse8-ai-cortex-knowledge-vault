---
name: cortex-feedback
description: >-
  Cortex feedback — create/list feedback notes, status OPEN, related_paths validation,
  Teams notifications. Use for feedback API, vault_feedback MCP, or admin review.
---

# Cortex feedback

## Storage

- **Folder:** `{vault}/feedback/`
- **Filename:** `YYYY-MM-DDTHH-MM-SS.md` (UTC timestamp)
- **Module:** `cortex/vault/feedback.py`

## Frontmatter

| Field | Value |
|-------|-------|
| `type` | `feedback` |
| `status` | `OPEN` on create |
| `tags` | list from request |
| `related_paths` | list of vault-relative `.md` paths |
| `created_at` | ISO timestamp |

## Validation

`related_paths` entries must:

1. Exist under vault root
2. Be files (not directories)
3. End with `.md`

Raw `.txt` or missing paths → error. Put filename mentions in `content` instead.

## API

| Method | Path |
|--------|------|
| POST | `/api/v1/feedbacks` |
| GET | `/api/v1/feedbacks` |
| GET | `/api/v1/feedbacks/{filename}` |
| DELETE | `/api/v1/feedbacks/{filename}` |

Response includes `status: "OPEN"` (not legacy `"created"`).

## MCP

- `vault_feedback` — same body as REST
- `vault_list_feedbacks` — metadata only (no full body)

## Teams notification

After successful create, `notify_new_feedback()` in `cortex/notify/teams.py` posts an Adaptive Card if `TEAMS_WEBHOOK_URL` is set. Link uses `TEAMS_APP_BASE_URL` when configured.

Failures to notify are logged; feedback file still created.

## Graph

Feedback notes become graph nodes (`NodeType.feedback`). Edges from `related_paths` where applicable.

## Related skills

- Vault layout: `cortex-vault`
- API reference: `cortex-api`
- Deploy Teams env: `cortex-deploy`
