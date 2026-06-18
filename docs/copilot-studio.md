# Using PULSE8.ai Cortex from Microsoft Copilot Studio

This guide configures a Copilot Studio agent to consume Cortex via MCP
**without any Cortex code change**. The agent is steered into the
token-light [resources-as-tool-inputs pattern][cs-cat-mcp] purely
through Copilot Studio's own settings.

[cs-cat-mcp]: https://microsoft.github.io/mcscatblog/posts/mcp-resources-as-tool-inputs/

> Prerequisite: Cortex must be reachable from Copilot Studio over public
> HTTPS (or via an on-prem data gateway). `http://localhost:8420/mcp/`
> will not work — Copilot Studio runs in Microsoft's cloud, not on your
> machine. See the [Authentication](../README.md#authentication) section
> of the main README for `apikey` / `oidc` setup.

## TL;DR

1. Add Cortex as an **MCP server** in your agent.
2. Enable only the read-side tools you need.
3. Paste the **agent instructions** block below into the agent.
4. Test, iterate on the instructions, ship.

Total time: about 5 minutes. No Cortex changes, no Custom Connector,
no environment variables to flip.

## 1. Add Cortex as an MCP server

In Copilot Studio: open your agent → **Tools** → **Add a tool** →
**Model Context Protocol** → enter:

| Field             | Value                                  |
| ----------------- | -------------------------------------- |
| Server URL        | `https://cortex.your-domain.com/mcp/`  |
| Authentication    | API Key (or Microsoft Entra ID)        |
| Header name       | `x-api-key`                            |
| Header value      | your `API_KEY` from `.env`             |

Copilot Studio performs the MCP discovery handshake; on success it
lists all Cortex tools and registers the `cortex://resource/{id}`
resource template automatically.

## 2. Enable only the tools the agent needs

Less surface = sharper planning. For a typical read-only "knowledge
agent" enable just these four:

| Tool                   | Enable | Why                                                            |
| ---------------------- | :----: | -------------------------------------------------------------- |
| `vault_search`         |   ✅   | Primary discovery channel                                      |
| `vault_context`        |   ✅   | Graph-expanded context windows                                 |
| `vault_read`           |   ✅   | Drill into a specific note by path                             |
| `vault_resource_read`  |   ✅   | Fallback read path — essential for the resources pattern       |
| `vault_list_feedbacks` |   ⚠️   | Only for admin/review agents                                   |
| `vault_feedback`       |   ⚠️   | Only when the agent should submit user feedback                |
| `vault_link`           |   ❌   | Skip unless the agent edits the graph                          |
| `vault_write`          |   ❌   | Skip unless the agent writes notes                             |
| `vault_ingest`         |   ❌   | Skip unless the agent uploads sources                          |
| `vault_compile`        |   ❌   | Skip unless the agent triggers compilation                     |

Adding `vault_write` / `vault_ingest` to a public-facing agent without
authentication is the classic accidental-write footgun. Enable
deliberately, never reflexively.

## 3. Agent instructions (the most important step)

Open your agent → **Overview** → **Instructions** field. Paste the
following verbatim:

```text
You have access to PULSE8.ai Cortex via MCP. Available Cortex tools:
vault_search, vault_context, vault_read, vault_resource_read.

REQUIRED token-discipline rules for every Cortex call:

1. ALWAYS call vault_search with as_resource=true.
2. ALWAYS call vault_context with as_resource=true.
3. After receiving a {resource_id, resource_uri, summary} handle:
   a. Read summary.count and summary.paths FIRST.
   b. If the user's question can be answered from the summary alone
      (counts, lists of paths, presence checks), DO NOT fetch the body.
   c. If you need note content, call vault_read on a SPECIFIC path
      from summary.paths — never read the whole resource just to scan it.
   d. Only call vault_resource_read(resource_id) when you genuinely
      need to inspect the entire stored payload.

4. NEVER ask vault_search or vault_context for a large result set
   without as_resource=true. If a previous call returned an inline
   payload that exceeded 2,000 tokens, retry with as_resource=true.

5. When the user's question is broad ("everything about X", "all notes
   tagged Y"), prefer as_resource=true with top_k=50 over a narrow
   inline search — the summary lets you reason about scope first, then
   drill in.

Style: cite specific note paths (e.g. wiki/foo.md) in your answers
when referencing Cortex content. Do not invent paths.
```

Why this wording works in Copilot Studio specifically:

- **Imperative `ALWAYS` / `NEVER`** — Copilot Studio's planner respects
  strict directives more reliably than soft hints.
- **Explicit naming of `vault_resource_read`** — the Copilot Studio
  planner does not always surface the MCP `resources/read` protocol
  channel to itself, so the fallback tool needs to be addressable by
  name.
- **Concrete numbers (2,000 tokens, top_k=50)** — Copilot Studio is
  much better at picking concrete arguments than at inferring
  "appropriate" ones.
- **Style line** — Copilot Studio is prone to hallucinating paths under
  pressure; the rule cuts that off.

## 4. Test the setup

Open Copilot Studio's **Test** pane and try:

| Prompt                                                                  | What to check                                                                |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| "Search Cortex for everything about wealth management. How many notes?" | Tool call uses `as_resource: true`, answer comes from `summary.count`         |
| "List the paths of all notes mentioning MiFID II."                      | Answer is built from `summary.paths`; no body read                            |
| "Read the wealth management overview note in detail."                   | Planner calls `vault_read("wiki/wealth-mgmt-overview.md")`, not the resource  |
| "Find me five short articles on payments."                              | Inline OK with small `top_k`; do not expect `as_resource` here                |
| "Pull the full graph context around 'derivatives compliance'."          | `vault_context` with `as_resource: true`, then `vault_read` on a specific hit |

If the planner inlines large payloads or omits `as_resource`, the
instructions need a tighter rule — usually adding a concrete number to
the directive helps. Iterate on the instruction block, not on Cortex.

## Fallback — when MCP is not yet enabled in your tenant

Some Copilot Studio tenants do not yet expose the MCP connector. In
that case wire Cortex's REST API as a Power Platform **Custom
Connector** from the OpenAPI spec — this is the **one** place where
you can hard-bake `as_resource=true` without touching Cortex.

1. Fetch the spec: `curl https://cortex.your-domain.com/openapi.json -o cortex.json`
2. **Power Apps portal → Custom Connectors → New → Import an OpenAPI file** → upload `cortex.json`
3. Set host (`cortex.your-domain.com`), base URL (`/api/v1`), auth (`API Key`, header `x-api-key`)
4. **Definition** tab → `search` action → query parameter `as_resource`:
   - **Default value**: `true`
   - **Visibility**: `internal` (hides it from the planner)

The Copilot Studio planner now never sees the flag — every search
through the connector hard-sets `as_resource=true`. Trade-off: you
only expose REST endpoints (`/search`, `/notes/{path}`,
`/resources/{id}`, etc.) rather than the full MCP tool surface.

## Authentication

For any non-trivial deployment, use Microsoft Entra ID (OIDC) so the
agent runs as a real identity instead of a shared API key:

```bash
# .env on the Cortex host
AUTH_METHOD=oidc
OIDC_TENANT_ID=<your-entra-tenant-id>
OIDC_CLIENT_ID=<app-registration-client-id>
OIDC_CLIENT_SECRET=<app-registration-secret>
OIDC_BASE_URL=https://cortex.your-domain.com
```

Configure the same tenant in Copilot Studio's MCP connection. Token
refresh is handled by the connector layer.

API key (`AUTH_METHOD=apikey`) is fine for PoC and single-tenant
demos. `AUTH_METHOD=none` is **never** appropriate for a publicly
reachable Cortex feeding Copilot Studio.

## Common gotchas

- **`localhost:8420` will not work.** Copilot Studio is cloud-hosted;
  Cortex must be reachable over public HTTPS or via an on-premises
  data gateway.
- **Enabling all 10 tools dilutes planning quality.** Stick to the
  read-side four unless the agent specifically needs writes.
- **Topic-based flows with hardcoded `as_resource=true`** work but
  defeat the purpose of having a generative agent — keep the planner
  in charge and steer it through instructions.
- **Resource TTL is wall-clock.** A Copilot Studio session that idles
  for over an hour will see `vault_resource_read` return a 404 for an
  expired resource. Raise `CORTEX_RESOURCE_TTL_SECONDS` if your
  agents have long-running orchestrations.
- **The resource store is per-process.** Restart Cortex → resources
  gone. This is deliberate (no GC, no stale data); agents naturally
  re-query.

## When to revisit a Cortex code change

Keep this configuration in place for at least a few days of real
usage. **Then** consider a server-side change only if both are true:

- The planner consistently ignores `as_resource=true` even with
  sharpened instructions, AND
- You see real cost or latency impact from inlined payloads in the
  Copilot Studio traces (Power Platform → Monitor → Activity).

The cheaper next step is sharpening Cortex's tool descriptions (one
small commit, affects every MCP client at once) — not duplicating
tools.

## Related

- [README.md — MCP resources](../README.md) — what the resource store
  is and how the pattern works
- [.cursor/skills/cortex-mcp/reference.md](../.cursor/skills/cortex-mcp/reference.md)
  — full MCP tool reference including `as_resource` semantics
- [Microsoft Copilot Studio CAT — Free Up Your Context Window][cs-cat-mcp]
  — the source pattern this guide is built on
