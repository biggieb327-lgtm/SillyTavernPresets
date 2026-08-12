# idea-scraper

An Apify Actor that collects recent posts from Reddit and Substack into one
normalized dataset, for the `improvement-loop-monthly` and
`character-pass-monthly` Routines in `.claude/operating/routines.md`.

It never runs anyone else's Actor. This account's plan has
`ACTORS_PUBLIC_ALL` disabled (`GET /v2/users/me` →
*"The 'All public Actors' feature isn't enabled for your account"*), so it can
only run Actors it owns. Everything here is this Actor's own HTTP requests.

---

## Working path (as of 2026-08-11)

```
Reddit    →  https://www.reddit.com/r/{sub}/top.rss     (Atom, no proxy)
Substack  →  https://{publication}/feed                 (RSS, no proxy)
```

Neither source needs a proxy. Apify residential proxy stays in the strategy
list as automatic failover, second after `direct`.

**Reddit's Atom feeds work. Reddit's JSON listings are blocked.** Both
`www.reddit.com/r/{sub}/top.json` and `api.reddit.com/r/{sub}/top` return
`403 Blocked` from every proxy group available to this account *and* from
Apify's bare compute IP. The Atom feeds are reachable from all of those. The
exit IP was never the variable in either direction - the endpoint was.

---

## Read this before "fixing" Reddit again

Four things look like the problem and are not. Each cost a deploy-and-test
cycle to rule out:

| Don't | Why |
|---|---|
| Remove the `httpx>=0.24,<0.28` pin | httpx 0.28 dropped the `proxies=` kwarg the pinned apify SDK 1.x still passes. Every proxy call dies with `AsyncClient.__init__() got an unexpected keyword argument 'proxies'`. |
| Switch back to the JSON endpoints | They are blocked by client fingerprinting, not by IP. See history #5. |
| Buy more proxy types | Residential, static-datacenter and rotating-datacenter IPs all got identical 403s on JSON. The exit IP is not the variable. |
| Set the Actor to `LIMITED_PERMISSIONS` | The scoped run token cannot read the account proxy password, so *every* proxy group fails with "Insufficient permissions". The Actor must stay `FULL_PERMISSIONS`. |

---

## Input

| Field | Type | Default | Notes |
|---|---|---|---|
| `subreddits` | string[] | `[]` | Names without `r/`. Empty skips Reddit. |
| `reddit_timeframe` | enum | `month` | Reddit's `t` param. |
| `substack_publications` | string[] | `[]` | Publication URLs, custom domains, or `substack.com/@handle` profile links. Empty skips Substack. |
| `max_items_per_source` | int | `25` | Caps both sources. Keeps unattended runs bounded. |
| `max_age_days` | int | `31` | Drop items older than N days. `0` disables. |
| `summary_max_chars` | int | `1500` | Characters kept per summary. Was hard-coded to 500. |
| `filter_titles` | string[] | `[]` | Case-insensitive regexes; matching entries dropped. |
| `fail_on_empty_source` | bool | `true` | Fail if **any** requested source returned zero rows. |
| `require_reddit` | bool | `true` | Deprecated — set `false` to exempt Reddit from the check above. |
| `reddit_strategy_override` | enum | `""` | Force one strategy, for diagnostics. |

## Output

Every row, from either source, has the same shape:

```json
{
  "source": "reddit",
  "title": "…",
  "url": "https://www.reddit.com/r/SillyTavernAI/comments/…",
  "external_url": "https://streamable.com/xjbaqm",
  "summary": "… (≤ summary_max_chars, default 1500)",
  "published_at": "2026-07-28T07:12:46+00:00",
  "community": "r/SillyTavernAI"
}
```

`source` is `reddit` or `substack`. `community` is `r/{subreddit}` or the
publication URL.

`published_at` is **always ISO 8601, or `null`** — never a raw feed string.
Reddit's Atom gives ISO and Substack's RSS gives RFC 2822, and passing both
through unchanged (as v0.10 did) produced a column that could not be sorted
across sources. An unparseable date becomes `null` rather than raw text, on
the reasoning that a missing value fails visibly here instead of at sort time
in the consumer.

`external_url` is where a link/image post actually points — `i.redd.it/…`,
`streamable.com/…`, a gallery. It is `null` for text posts and for Substack.
On a link post it is the only substance the row carries, because those have
no body at all.

---

## How a strategy is chosen

The Actor walks an ordered `(proxy, endpoint)` list against the **first**
subreddit, and reuses whatever works for the rest. One run diagnoses the
whole matrix instead of one deploy per guess.

Log lines, all four meaningful:

| Line | Meaning |
|---|---|
| `STRATEGY SKIP` | Not runnable — an env var is unset, or a proxy group is unusable. Not a failure. |
| `STRATEGY FAILED` | The request was made and rejected. The error text is the diagnosis. |
| `STRATEGY EMPTY` | HTTP 200 but zero entries parsed. Usually a feed-format change. |
| `STRATEGY OK` | Winner. Used for all remaining subreddits. |

Every successful run also sets a status message —
`strategy=group:RESIDENTIAL reddit=5 substack=0` — readable via
`GET /v2/actor-runs/{id}` no matter what the log level is doing.

`direct` was tested on 2026-08-11 and **succeeded** (`strategy=direct
reddit=5`), so as of 0.10 it leads the list and no proxy is used in normal
operation. `group:RESIDENTIAL` sits second and takes over automatically if
Reddit ever starts blocking Apify's shared compute IPs. Apify's compute IPs
are shared and their reputation drifts, so keep the fallback rather than
deleting it.

---

## Substack URL handling

Users paste whatever they have, so the input is normalized rather than trusted:

* **Tracking params are stripped.** `https://substack.com/@name?utm_source=share`
  with `/feed` appended naively produces a URL with the query string in the
  middle. This was a live bug through 0.11.
* **Reader-profile links are not publications.** `substack.com/@handle` has no
  feed of its own, so the handle is also tried as `handle.substack.com/feed`.
  Check the log for `substack: fell back to` to see which candidate served.
* **Each candidate must parse and contain `<item>` elements** to be accepted —
  an HTML error page or an empty feed falls through to the next candidate
  rather than counting as success.

If every candidate fails, the error names each URL tried.

## Recency

Reddit enforces recency server-side through `reddit_timeframe` (`t=month`).
Substack's RSS has no equivalent — it serves the most recent entries however
old they are, so a dormant publication would contribute year-old posts. The
`max_age_days` filter is applied client-side to **both** sources so they share
one definition of "recent". Items with no parseable date are kept: a missing
date is not evidence of being old.

## Substack subscriber feeds (paywalled publications)

A paywalled publication's **public** RSS carries only the free preview. Two
independent Routine runs on 2026-08-11 confirmed this is a hard ceiling, not a
tuning problem — `practice-scan-weekly` judged the posts "paid-newsletter teasers
with no concrete extractable technique in the free text," and no setting on this
Actor changes what the feed contains.

**Substack does not issue subscriber RSS feeds** (confirmed 2026-08-12). The
`/p` in a Substack URL marks a private publication; it is not a token. Two runs
failed 404 against invented URL shapes before this was established. The support
below is kept for a future publication that offers such a feed — it is tested
and correct — but nothing is configured for the current two, and
`substack_publications` carries their public URLs instead. Paid posts arrive as
free previews; the consuming Routine researches the topic from primary sources.

Where a publication *does* offer one, the URL contains a token and is a credential.

**It is never Actor input.** Actor input is echoed into the run record and into
whatever prompt invoked the run, and this repo is public. Private feeds are read
from a secret environment variable instead:

    SUBSTACK_PRIVATE_FEEDS   one or more subscriber feed URLs,
                             separated by commas, spaces or newlines

Set it as an `isSecret` env var on the Actor version (`deploy_v014.py` does this
from your shell environment). Three guarantees, each covered by a test:

* **Rows** carry only the sanitized origin (`https://learnaiwithme.com`) in
  `community` — never the feed URL.
* **Logs** print only that origin (`private feed OK: https://… -> N items`).
* **Errors** are redacted before they are raised.

**The error guarantee was broken in 0.13 and fixed in 0.14.** The handler
interpolated the caught exception, and `requests` embeds the full request URL in
its `HTTPError` text — so a 404 produced `... Not Found for url:
https://host/feed/p/TOKEN`, which reached the run log and the run's status
message. Run `pVRaNhKrEbRgsxgVJ` did exactly that. The 0.13 test only exercised
the empty-feed branch, which never touches the URL; the HTTP-error branch, the
one that fires in practice, was untested. 0.14 redacts before raising and tests
all three branches — HTTP error, connection error, empty feed.

If a private feed URL ever appears in a run log, **regenerate it at the
publication** rather than only fixing the code: the log has already been written.

**Truncation.** A long URL pasted into a phone terminal can pick up a line
break. The prefix still parses as a URL, so the configured count looks right and
the failure surfaces three layers later as a 404 on a nonsense path. 0.14 warns
when a fragment is discarded, and when a stored entry is too short to carry a
token.

**Do not list the same publication in both `substack_publications` and
`SUBSTACK_PRIVATE_FEEDS`.** Rows are deduplicated by post URL and public jobs run
first, so the paywalled teaser would win over the full text — the exact opposite
of the point. A publication with a subscriber feed should be removed from
`substack_publications` entirely.

## Known limitations of the Atom path

**Link posts have no body, by construction.** Atom `<content>` for a link or
image post is *only* `submitted by /u/x [link] [comments]` boilerplate. As of
0.11 that boilerplate is stripped, so `summary` is empty rather than
misleading, and `external_url` carries the destination instead. Expect roughly
half of a typical `top` listing to have an empty summary — that is accurate,
not a regression. Self-posts come through in full: one measured post carried
14,360 characters of body, of which v0.10 kept 500.

**No NSFW filtering.** (unchanged in 0.11) The old JSON path filtered `over_18` and `stickied`.
Atom carries neither. Verified against a live feed: every `<entry>` has
exactly one `<category>` (the subreddit name), and an NSFW post is
structurally identical to a safe one — absence of `media:thumbnail` is not a
signal either, since safe link posts also lack it. `filter_titles` is a blunt
keyword substitute, not an equivalent. It is empty by default: on an
AI-roleplay subreddit, adult content may be signal rather than noise. Decide
deliberately before leaving an unattended Routine running.

---

## History: five blockers, each hidden behind the last

1. **v0.2–v0.3.2 never ran.** `main()` was defined but never invoked — no
   `asyncio.run()`. `python3 -m src.main` exited 0 having done nothing, which
   is indistinguishable from a genuinely empty result. Fixed in 0.4.

2. **Runs executed under `LIMITED_PERMISSIONS`.** Confirmed via
   `GET /v2/acts/{id}` → `actorPermissionLevel`. The scoped run token could not
   read the account proxy password, so `create_proxy_configuration()` raised
   *"Insufficient permissions"* for **every** group — which is why swapping
   groups never helped. Fixed by setting the Actor to `FULL_PERMISSIONS`.

3. **httpx incompatibility.** With permissions fixed, the same call failed with
   `AsyncClient.__init__() got an unexpected keyword argument 'proxies'`
   (run `jCU5ds7tavTAdoySy`, build 0.5.1). `requirements.txt` had no httpx pin,
   so the build pulled httpx ≥ 0.28, which removed `proxies=`. Fixed by pinning
   `httpx>=0.24,<0.28`.

4. **Proxy attached, Reddit still refused.** Run `vFWSyk0LIsrO6gWic`,
   build 0.5.3: no `create_proxy_configuration failed` line, and the status
   message no longer said *"no proxy URL could be obtained"* — the request went
   out through `BUYPROXIES94952` and came back `403 Blocked`.

5. **The 403 is fingerprint-based, not IP-based.** Run `pwewGtcRIBTHZavIe`
   tried five combinations — `RESIDENTIAL`, `StaticUS3` and `BUYPROXIES94952`
   against both `www.reddit.com/*.json` and `api.reddit.com` — and every one
   returned an identical `403 Blocked`. Residential proxy is confirmed
   *working* (real responses, ~7 s latency, no "unusable" warning);
   `maxMonthlyResidentialProxyGbytes: 10` is the real capability signal and
   `RESIDENTIAL availableCount: 0` is a red herring, since residential is
   metered by traffic rather than IP count. A block that ignores exit IP
   entirely is Cloudflare fingerprinting the client — `python-requests`' TLS
   handshake and thin header set. **Switching to the Atom feeds cleared it.**

**OAuth is not available as a fallback.** Reddit's classic script-app
registration at `reddit.com/prefs/apps` redirects to Devvit (checked
2026-08-11), so no new `client_id`/`client_secret` can be issued. The OAuth
code path is retained and activates automatically if credentials ever exist,
but nothing depends on it.

---

## Operations

**Deploying without the apify CLI.** The Actor's source is stored as
`SOURCE_FILES`, and `deploy_v09.py` pushes a version and triggers a build using
only Python's stdlib — no Node, no Docker, no CLI. Unchanged files are
inherited from the previous version, so only edited files need to exist
locally. Secrets are uploaded as `isSecret` env vars on the version, which is
how to set them without the CLI's secret store.

**Never put a token in a URL or a non-secret env var.** Both have happened
here. Apify's API takes `Authorization: Bearer`; `?token=` leaks into logs,
history and referrers. A credential pasted into a plain env var is stored in
cleartext and readable by anyone who can `GET` the version.

**Verifying a run:**

```bash
curl -sS -H "Authorization: Bearer $APIFY_API_TOKEN" \
  "https://api.apify.com/v2/actor-runs/$RID" \
  | python3 -c "import json,sys;d=json.load(sys.stdin)['data'];print(d['status']);print(d.get('statusMessage'))"
```

**Troubleshooting:**

| Symptom | Cause |
|---|---|
| Run SUCCEEDED, dataset empty | Only possible with `fail_on_empty_source: false`. Otherwise the run fails with a status message naming which source came back empty and why. |
| Info-level log lines missing | `APIFY_LOG_LEVEL` is not `INFO` on the version. Setting the logger level in code is not enough — the handler threshold wins. The deploy script ships `APIFY_LOG_LEVEL=INFO` by default. |
| `published_at` is `null` | The feed served a date in neither ISO 8601 nor RFC 2822. Check the raw feed; the parse is deliberately strict. |
| `Insufficient permissions` | Actor reverted to `LIMITED_PERMISSIONS`. |
| `unexpected keyword argument 'proxies'` | The httpx pin was dropped from `requirements.txt`. |
| `403 Blocked` on every strategy | Reddit extended fingerprinting to the Atom feeds. Nothing short of browser impersonation will help — decide deliberately. |
| `STRATEGY EMPTY` | Feed still served but the Atom shape changed; check `_parse_atom`. |
| API calls return 404 for a known-good Actor | Almost always a bad or wrong-account token — Apify returns 404 rather than 403 for Actors a token cannot see. Check `users/me` first. |
