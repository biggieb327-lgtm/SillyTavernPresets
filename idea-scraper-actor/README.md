# idea-scraper-actor

A small Apify Actor that fetches Reddit's own public JSON listings and
Substack RSS feeds directly, for the `improvement-loop-monthly` and
`character-pass-monthly` Routines in `.claude/operating/routines.md`.

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
(routed through Apify's own residential proxy, which *is* available on a
Creator plan since it's the actor's own network egress, not another Actor's
execution) and to each Substack publication's public `/feed` RSS endpoint
(no proxy needed, not blocked). If this ever breaks again, the fix is either
"the proxy stopped getting through Reddit's Cloudflare" (try a different
proxy group, e.g. `RESIDENTIAL` → check Apify Console for others available on
the current plan) or "the plan changed" (check Apify Console → Settings →
billing) — not another architecture pivot.

**Unverified as of 2026-08-07**: whether Apify's residential proxy actually
gets past Reddit's Cloudflare block. The mechanism is sound (that's what
residential proxies are for), but no live run has confirmed it — the first
deploy attempt should be watched via Apify Console's run log before trusting
this in production.

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
