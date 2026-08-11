# idea-scraper-actor

A small Apify Actor that fetches Reddit's own public JSON listings and
Substack RSS feeds directly, for the `improvement-loop-monthly` and
`character-pass-monthly` Routines in `.claude/operating/routines.md`.

How a session reaches Apify at all — the `.mcp.json` server, the egress
allowlist, and which environment the Routines actually fire into — is
`.claude/operating/apify-access.md`. This file owns the Actor and the Reddit
history; that one owns the access layer above it.

## Why this exists (read before touching Reddit access again)

Three approaches were tried in one day (2026-08-07) before this one:

1. **Direct `curl` from a fired Claude Code session to `reddit.com`.** Blocked:
   Cloudflare returns a 403 after a completed TLS handshake, and `WebFetch`/
   `WebSearch` both refuse the domain outright. No workaround from inside a
   fired session.
2. **A custom Actor wrapping `trudax/reddit-scraper-lite`** (calling it via
   `Actor.call()`). Retired the same day it was built, in favor of:
3. **Calling `trudax/reddit-scraper-lite` directly** via Apify's
   `run-sync-get-dataset-items` REST endpoint, no custom Actor. **Blocked**:
   the owner's Apify plan (Creator) returned `"The Creator plan does not
   include permission to run public Actors"` — a billing-tier restriction,
   not a network or token problem. This applies to *any* public Actor,
   called *any* way (direct REST call or `Actor.call()` from inside your own
   Actor) — approach 2 would have hit the identical wall had it still been
   live.

**This actor is approach 4**: it never runs anyone else's Actor. It makes its
own HTTP requests — to Reddit's public `{subreddit}/top.json` listing
(meant to be routed through one of Apify's own proxy groups, since that's
the actor's own network egress, not another Actor's execution) and to each
Substack publication's public `/feed` RSS endpoint (no proxy needed, not
blocked).

**Status as of 2026-08-07: Reddit fetching does not work end to end.**
Three real bugs found and fixed in sequence on live runs, in order of how
they were uncovered — read this before assuming a new one is the same as
an old one:

1. **v0.2 through v0.3.2 never actually ran.** `main.py` defined
   `async def main()` but nothing ever called it — no `asyncio.run(main())`,
   no `if __name__ == "__main__":` block. `CMD ["python3", "-m", "src.main"]`
   just imported the module, defined some functions, and exited 0. Every
   "SUCCEEDED, 0 items" run through v0.3.2 (including the `RESIDENTIAL`
   group findings below) reflects this, not a real Reddit-access attempt —
   confirmed by adding a log line as the literal first statement in `main()`
   and finding it never appeared in any run's log. Fixed in v0.3.3 by adding
   the entrypoint.
2. **Once `main()` actually ran, `create_proxy_configuration()` failed with
   `ApifyApiError: Insufficient permissions`** — for *every* proxy group, not
   just one. The traceback shows the failure inside `apify-client`'s
   `user().get()` call (fetching the account's proxy password), before group
   selection is even relevant. This is an account/token permission gap, not
   a group-availability one. (`RESIDENTIAL`'s `availableCount: 0`, found via
   `GET /v2/users/me` while investigating, is real but turned out to be a
   red herring — `BUYPROXIES94952`'s 27 available proxies hit the identical
   permission error.) Fixed in v0.3.4/v0.4 by wrapping proxy setup in a
   try/except that falls back to an unproxied fetch instead of crashing the
   run — but this does not fix Reddit access, it only stops the permission
   error from being fatal.
3. **The unproxied fallback gets a genuine Reddit 403.** With no proxy,
   `_fetch_subreddit`'s `requests.get()` against `reddit.com` returns
   `403 Client Error: Blocked` — confirmed live, not inferred. Apify's own
   compute IPs are blocked by the same Cloudflare rule that blocks a fired
   Claude Code session's `WebFetch`/direct `curl`.

**Net result: there is currently no working path from this actor to
Reddit**, proxied or not. Substack needs no proxy and should work now that
`main()` actually runs, but is untested — no `substack_publications` URL was
in any test call. **To actually fix Reddit access**, the account's Apify
Proxy permission needs to be granted (Console/Apify support, not something
an API token can self-serve) — and even then, whether any given group's
egress IPs get past Cloudflare is still unverified; that's the next open
question, not this one. Do not "fix" the group name again without checking
`create_proxy_configuration()` actually succeeds first — a plausible-looking
group swap will look identical to the v0.2 fix and still not work.

## Input

See `.actor/input_schema.json`. Key fields: `subreddits` (bare names, no
`r/` prefix), `reddit_timeframe` (Reddit's own `t=` param), `substack_publications`
(full URLs), `max_items_per_source` (bounds cost/runtime - do not raise
casually, this is called from unattended monthly Routines).

## Output

One dataset row per item: `{source, title, url, summary, published_at, community}`.
`source` is `"reddit"` or `"substack"`.

## Deploying

Requires Node.js (for the Apify CLI) and an Apify account/token. From this
directory:

```bash
npm install -g apify-cli
apify login -t <your Apify API token>
apify push
```

This builds and deploys under your account as `<username>/idea-scraper`. The
actor ID (needed for `APIFY_ACTOR_ID`, see below) is shown in the push output
or on the Actor's page in Apify Console.

## Wiring into the Routines

Both Routines call this actor synchronously via Apify's REST API:

```bash
curl -sS -X POST \
  "https://api.apify.com/v2/acts/$APIFY_ACTOR_ID/run-sync-get-dataset-items?token=$APIFY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subreddits": ["SillyTavernAI"], "reddit_timeframe": "month", "substack_publications": [], "max_items_per_source": 25}'
```

Requires `APIFY_API_TOKEN` and `APIFY_ACTOR_ID` set as environment variables
on the Claude Code Remote environment the Routines fire into (`SillyTavernPresets`,
`env_013KxczVfcQicP87yAYmHtKj` as of 2026-08-07) — set them under that
environment's settings at claude.ai/code, not in this repo. See
`.claude/operating/routines.md` for the exact prompts and the SKIP fallback
(WebSearch-only) when Apify isn't configured or reachable.
