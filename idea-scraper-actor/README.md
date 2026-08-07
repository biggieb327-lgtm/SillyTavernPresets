# idea-scraper-actor

A custom Apify actor for the two monthly Routines in this repo
(`improvement-loop-monthly`, `character-pass-monthly`) that scan Reddit (and
now Substack) for external ideas. It replaces the old approach of `curl`-ing
`reddit.com`'s public JSON API directly from a Routine session, which the
environment's network egress policy blocks (`CONNECT 403`, since 2026-07-20 -
see `.claude/operating/routines.md`).

**This is a separate project, like `voicekit-starter/` — none of the bot
fleet's rules (BOT_VERSION, changelog gate, deploy path) apply here.**

## What it does

- **Reddit:** wraps the existing, mature `trudax/reddit-scraper-lite` actor
  (pay-per-result, ~$4.00/1,000 results as of 2026-08) via `Actor.call()`,
  rather than reimplementing Reddit scraping. Give it `reddit_urls` (subreddit
  or search URLs) and it forwards them as `startUrls`.
- **Substack:** reads each given publication's public RSS feed
  (`<pub>.substack.com/feed`) directly with `requests` — no anti-bot wall, no
  extra Apify actor, no extra cost.
- Both sources are normalized into one dataset shape:
  `{source, title, url, summary, published_at, community}`.

## Known gap — verify before trusting Reddit field names

`src/main.py`'s `_normalize_reddit_item()` guesses at
`trudax/reddit-scraper-lite`'s output field names (`title`, `url`/`permalink`,
`body`/`selftext`, `communityName`/`subreddit`, `createdAt`) from the actor's
description page — **not from a live run**, since this environment currently
has no network path to `api.apify.com` or `console.apify.com` to test against.
Before relying on this in production: run it once with a small `reddit_urls`
list, inspect the resulting dataset items against the sub-actor's real output
schema (Actors tab → Runs → a completed run → Dataset), and fix any field
names that don't match. The fallback chain degrades to `None`/truncated
values rather than crashing, so a mismatch will produce thin records, not an
error — check for that too.

## Deploy

Requires an Apify account and the Apify CLI, neither of which this session
has credentials for — deploy from your own machine:

```bash
npm install -g apify-cli
apify login                 # paste your Apify API token
cd idea-scraper-actor
apify push                  # builds and deploys; prints the actor's ID
```

The printed actor ID (e.g. `your-username/idea-scraper`) is what goes into
`APIFY_ACTOR_ID` below.

## Wiring into the Routines

The two Routine prompts in `.claude/operating/routines.md` call this actor
synchronously via Apify's REST API and expect two environment variables set
on the Claude Code Remote **environment** (not this repo's `.env` — that's
the bot fleet's, unrelated):

- `APIFY_API_TOKEN` — from Apify Console → Settings → Integrations.
- `APIFY_ACTOR_ID` — the ID printed by `apify push` above.

If either is unset, or the call to `api.apify.com` itself gets a
`CONNECT`/tunnel 403 (same network-policy class as the old `reddit.com`
block), the Routine step self-reports SKIPPED rather than failing the run —
see the "Reddit access" bullets in `routines.md` for the exact skip message.

## Cost bound

`max_items_per_source` (default 25, capped at 100 by the input schema) bounds
both the Reddit sub-actor's `maxItems`/`maxPostCount` and the number of
Substack RSS entries read per publication per Routine firing. At the default,
two Routines firing monthly across ~3 Reddit sources is on the order of a few
dollars a year at `trudax/reddit-scraper-lite`'s pay-per-result pricing —
Substack RSS is free. Don't raise the bound without the owner's approval;
it's the only thing standing between an unattended monthly Routine and an
unbounded Apify bill.

## Local test (no deploy)

```bash
cd idea-scraper-actor
pip install -r requirements.txt apify-cli
apify run --input '{"reddit_urls": [], "substack_publications": ["https://example.substack.com"], "max_items_per_source": 5}'
```

Substack-only input needs no Apify token. Any `reddit_urls` entry does, since
it calls the sub-actor.
