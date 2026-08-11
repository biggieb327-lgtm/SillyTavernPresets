# Apify access — what reaches Reddit and Substack, and what blocks it

Owns one question: how a Claude Code session in this repo reaches Apify, and
through it Reddit and Substack. The Reddit *history* — the four approaches tried
and abandoned on 2026-08-07 — stays in `idea-scraper-actor/README.md`; read that
before touching Reddit access again. This file covers the access layer above it.

## The integration

`.mcp.json` (repo root) registers Apify's hosted MCP server:

```json
{ "mcpServers": { "apify": {
    "type": "http",
    "url": "https://mcp.apify.com?tools=actors",
    "headers": { "Authorization": "Bearer ${APIFY_API_TOKEN}" } } } }
```

- `${APIFY_API_TOKEN}` is expanded by Claude Code from the environment, so no
  token is committed. `[observed]` Claude Code's own docs
  (`code.claude.com/docs/en/mcp.md`) document `${VAR}` expansion in `.mcp.json`,
  headers included.
- **If the variable is unset, the config still loads** and the literal
  `${APIFY_API_TOKEN}` text is sent as the bearer token — the server fails
  authentication rather than being skipped. An unset token looks like an Apify
  auth error, not like "Apify is not configured".
- `tools=actors` is pinned deliberately. Apify's README says the default tool
  set may change between versions and tells production callers to pin. `actors`
  gives `search-actors`, `fetch-actor-details`, and `call-actor`, and Apify
  auto-injects `get-dataset-items` alongside them — which is the whole flow:
  `call-actor` returns a `datasetId`, not rows, and the rows come from a second
  `get-dataset-items` call.

## What MCP does and does not change

**It is a transport, not a fix for Reddit.** It replaces one `curl` to
`api.apify.com/v2/acts/.../run-sync-get-dataset-items` with typed tool calls
against the same account, the same plan, and the same Actor. Every blocker in
`idea-scraper-actor/README.md` survives it unchanged:

- The Creator plan's refusal to run public/store Actors applies to `call-actor`
  exactly as it applied to the REST call — running a store Actor through MCP is
  still running a store Actor.
- The owner's own Actor still gets a 403 from Reddit when it fetches unproxied,
  and still cannot build a proxy configuration without the account's Apify Proxy
  permission.

MCP becomes a genuine win for Reddit only if the plan can run store Actors —
then a store scraper (or `apify/rag-web-browser`) replaces the custom Actor's
broken Reddit half outright. That single fact decides whether this integration
is worth more than the `curl` it replaces, and it is not settled below.

## Two environments, not one

`[observed 2026-08-11]` The cloud session that a person starts from the app and
the session a Routine fires into are **not necessarily the same environment**,
and this repo has two:

| Environment | ID | Role |
|---|---|---|
| SillyTavernPresets | `env_013KxczVfcQicP87yAYmHtKj` | where the Routines fire; where `APIFY_API_TOKEN` / `APIFY_ACTOR_ID` were provisioned |
| Default Cloud Environment | `env_012hEHsXNiwNcgJTtkZy9JRd` | where an ad-hoc session can land instead |

A session started from the app landed in the Default environment, where
`APIFY_API_TOKEN` is **unset** and Apify is **unreachable**. Reading either fact
there and reporting it as "Apify is broken" would have been wrong about the
environment that actually matters. Check `environment_id` before generalising a
network or env-var finding — this is C1 (confirm the host) in a new costume.

## Egress is an allowlist

`[observed 2026-08-11, Default environment]` The egress gateway answers 403 to
CONNECT for `api.apify.com`, `mcp.apify.com`, `www.reddit.com` and
`substack.com`. It answers 403 for `example.com` too, while `api.github.com` and
`raw.githubusercontent.com` succeed — so this is an **allowlist**, and an Apify
refusal there means "not on the list", not "Apify is down". The proxy records the
reason at `$HTTPS_PROXY/__agentproxy/status` under `recentRelayFailures`.

Consequence worth naming: **Substack needs Apify only because of this
allowlist.** A Substack feed is public RSS that plain `curl` could fetch in one
line; the Actor exists for it purely because the session cannot reach
`substack.com`. Allowlisting `substack.com` would remove Apify from the Substack
path entirely. Reddit is not like this — Reddit blocks the datacenter IP itself,
so allowlisting `reddit.com` would change a proxy 403 into a Cloudflare 403.

## The unattended-session trap

`[observed]` Claude Code's docs state that a project `.mcp.json` needs approval,
and that `enabledMcpjsonServers` / `enableAllProjectMcpServers` **committed to
the repo's own `.claude/settings.json` are ignored in an untrusted folder** — "a
cloned repository can't approve its own servers". Approvals still apply from
`~/.claude/settings.json`, managed settings, or `--settings`.

A Routine fires into a fresh container with a fresh clone and nobody to accept a
trust dialog. So the committed config may leave the server at
`⏸ Pending approval`: the tools simply are not there, and a Routine that assumed
them would report an empty scan rather than an error. **Whether a fired session
in `env_013Kxcz…` actually trusts its own clone is unverified** — it is a
property of the runner, not of the docs. Any Routine step that uses the Apify
MCP tools must therefore branch on the tools being present, never assume them.

## Open questions — none of these are settled

Each needs a run inside `env_013KxczVfcQicP87yAYmHtKj`, not the Default one:

1. Are `api.apify.com` and `mcp.apify.com` on that environment's allowlist?
2. Does the Apify plan still refuse to run public/store Actors? (Recorded
   2026-08-07 from a verbatim Apify error; not re-tested since.)
3. Has Apify Proxy permission been granted on the account? Until it is,
   `create_proxy_configuration()` fails for every group and the Actor falls back
   to an unproxied fetch that Reddit refuses.
4. Does a fired session load the `apify` MCP server, or leave it pending?

Until 1 and 4 are answered, the Routines keep their existing order: the `curl`
path first, and the WebSearch-only scan when Apify is unreachable. Nothing in
`routines.md` or the live Routine prompts was changed by this work — changing
one without the other trips the drift-stop those prompts open with.
