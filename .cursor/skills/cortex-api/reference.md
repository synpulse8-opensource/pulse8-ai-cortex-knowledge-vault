# REST API reference

Base: `/api/v1` on Cortex (default `http://localhost:8420`).

## Endpoints

| Method | Path | Tag | Notes |
|--------|------|-----|-------|
| GET | `/health` | health | No auth required |
| GET | `/login` | auth | OIDC redirect (oidc mode) |
| GET | `/auth/callback` | auth | OAuth callback |
| POST | `/login` | auth | Token exchange |
| GET | `/notes/{path}` | notes | Path is vault-relative, URL-encoded |
| PUT | `/notes/{path}` | notes | Create/update note |
| GET | `/search` | search | Query params: `q`, `mode`, `top_k` |
| POST | `/links` | graph | Create edge |
| GET | `/links` | graph | Query edges |
| DELETE | `/links/{source}` | graph | Delete edges from source |
| GET | `/graph/stats` | graph | Node/edge counts |
| POST | `/ingest` | ingest | JSON body: content + filename |
| POST | `/ingest/upload` | ingest | Multipart file upload |
| POST | `/compile` | ingest | Async compile job (202) |
| GET | `/compile/status` | ingest | Compile job status |
| POST | `/bulk-ingest` | ingest | `source_dir` on server |
| GET | `/feedbacks` | feedback | List metadata |
| GET | `/feedbacks/{filename}` | feedback | Full note + edges |
| POST | `/feedbacks` | feedback | Create feedback |
| DELETE | `/feedbacks/{filename}` | feedback | Delete feedback file |

## curl examples

```bash
# Health
curl http://localhost:8420/api/v1/health

# With API key
curl -H "x-api-key: $API_KEY" http://localhost:8420/api/v1/graph/stats

# Create feedback
curl -X POST http://localhost:8420/api/v1/feedbacks \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"content":"…","tags":["admin-review"],"related_paths":["wiki/foo.md"]}'
```
