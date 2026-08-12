"""Idea scraper actor: Reddit + Substack, no dependency on any other Actor.

## WORKING PATH (as of 2026-08-11)

    https://www.reddit.com/r/{sub}/top.rss   (no proxy needed)

Reddit's **Atom feeds work; the JSON listings are blocked.** Confirmed by
run pwewGtcRIBTHZavIe (all five JSON combinations 403) followed by a
successful RSS run on build 0.8.x. Do not "fix" a future breakage by
reaching for the JSON endpoints again - see history below.

## History (read before changing the Reddit path)

Each blocker was hidden behind the previous one.

1. **v0.2-v0.3.2 never ran.** `main()` defined but never invoked. Clean
   exit 0, no output. Fixed in 0.4.
2. **LIMITED_PERMISSIONS.** The scoped run token could not read the account
   proxy password, so `create_proxy_configuration()` raised "Insufficient
   permissions" for *every* group - which is why swapping groups never
   helped. Fixed by setting the Actor to FULL_PERMISSIONS.
3. **httpx incompatibility.** `AsyncClient.__init__() got an unexpected
   keyword argument 'proxies'` - httpx 0.28 removed `proxies=`, which the
   pinned apify SDK 1.x still passes. Fixed by pinning httpx<0.28 in
   requirements.txt. **Do not remove that pin.**
4. **OAuth is unavailable.** Reddit's classic script-app registration at
   reddit.com/prefs/apps redirects to Devvit (confirmed 2026-08-11), so no
   new client_id/secret can be issued. The OAuth path is retained and
   activates by itself if credentials ever exist; nothing depends on it.
5. **The JSON 403 is fingerprint-based, not IP-based.** RESIDENTIAL,
   StaticUS3 and BUYPROXIES94952 all got identical 403s against both
   www.reddit.com/*.json and api.reddit.com. Residential proxy is confirmed
   *working* (real responses, ~7s latency; `maxMonthlyResidentialProxyGbytes:
   10` is the real signal and `RESIDENTIAL availableCount: 0` is a red
   herring). Buying more proxy types will not help. The Atom feeds simply
   sit behind different edge rules.

## Two known limitations of the Atom path

* **Thin summaries on link posts.** Atom `<content>` for a link post is
  literally "submitted by /u/x [link] [comments]" - there is no `selftext`
  equivalent. Self-posts come through in full.
* **No NSFW filtering.** The JSON path filtered `over_18` and `stickied`;
  Atom carries neither. Verified against a live feed: every entry has
  exactly one `<category>` (the subreddit name) and an NSFW post is
  structurally identical to a safe one. `filter_titles` below is a
  best-effort keyword filter, off by default - it is a blunt instrument,
  not a replacement for the flag.

Normalizes every source into one dataset shape so callers (the
SillyTavernPresets Routines) don't need source-specific parsing:

    {source, title, url, summary, published_at, community}
"""
import asyncio
import logging
from datetime import datetime, timezone
import os
import re
import xml.etree.ElementTree as ET

import requests
from apify import Actor

from .extract import (
    from_epoch,
    looks_truncated,
    parse_private_feeds,
    redact_url,
    reddit_content,
    sanitize_feed_url,
    strip_html,
    substack_feed_candidates,
    to_iso,
    truncate,
    within_age,
)

_CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}"
_DEFAULT_USER_AGENT = "python:idea-scraper-actor:0.12"
_ATOM = "{http://www.w3.org/2005/Atom}"

# Ordered. The confirmed-working combination is first; the rest are fallbacks
# kept so a future Reddit change is diagnosed in one run rather than five.
#   env:NAME       full proxy URL taken verbatim from env var NAME
#   envgroup:NAME  proxy group whose *name* is in env var NAME
#   group:NAME     literal proxy group name
#   direct         no proxy at all
_STRATEGIES = [
    # `direct` leads as of 0.10: confirmed working with no proxy at all
    # (run with reddit_strategy_override="direct" -> "strategy=direct reddit=5").
    # RESIDENTIAL stays second as automatic failover if Reddit ever starts
    # blocking Apify's shared compute IPs - it costs nothing sitting here.
    ("direct", "https://www.reddit.com/r/{sub}/top.rss"),
    ("group:RESIDENTIAL", "https://www.reddit.com/r/{sub}/top.rss"),
    ("group:BUYPROXIES94952", "https://www.reddit.com/r/{sub}/top.rss"),
    ("env:UNBLOCKER_PROXY_URL", "https://www.reddit.com/r/{sub}/top.rss"),
    ("envgroup:UNBLOCKER_GROUP", "https://www.reddit.com/r/{sub}/top.rss"),
    ("group:RESIDENTIAL", "https://old.reddit.com/r/{sub}/top.json"),
    # Control: 403'd consistently through build 0.7.x. If this ever passes,
    # Reddit changed something rather than the fix working.
    ("group:RESIDENTIAL", "https://www.reddit.com/r/{sub}/top.json"),
]

_REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_REDDIT_OAUTH_BASE = "https://oauth.reddit.com"


def _user_agent() -> str:
    return os.environ.get("REDDIT_USER_AGENT") or _DEFAULT_USER_AGENT


def _proxies(proxy_url: str | None) -> dict | None:
    return {"http": proxy_url, "https": proxy_url} if proxy_url else None


_group_cache: dict[str, str | None] = {}


async def _proxy_for_group(group: str) -> str | None:
    if group in _group_cache:
        return _group_cache[group]
    try:
        configuration = await Actor.create_proxy_configuration(groups=[group])
        url = await configuration.new_url() if configuration else None
    except Exception as exc:  # noqa: BLE001 - a group being unavailable is data
        Actor.log.warning(
            "proxy group %r unusable: %s "
            "('Insufficient permissions' => LIMITED_PERMISSIONS; "
            "unexpected keyword 'proxies' => httpx pin regressed)",
            group, exc,
        )
        url = None
    _group_cache[group] = url
    return url


async def _resolve_proxy(spec: str) -> tuple[str | None, str | None]:
    """Return (proxy_url, skip_reason). skip_reason set => not runnable."""
    kind, _, value = spec.partition(":")
    if kind == "direct":
        return None, None
    if kind == "env":
        url = os.environ.get(value)
        return (url, None) if url else (None, f"{value} not set")
    if kind in ("envgroup", "group"):
        group = os.environ.get(value) if kind == "envgroup" else value
        if not group:
            return None, f"{value} not set"
        url = await _proxy_for_group(group)
        return (url, None) if url else (None, f"group {group!r} unusable")
    return None, f"unknown proxy spec {spec!r}"


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def _parse_json_listing(payload: dict, subreddit: str, limit: int, chars: int) -> list[dict]:
    entries = []
    for child in payload.get("data", {}).get("children", [])[:limit]:
        post = child.get("data", {})
        if post.get("over_18") or post.get("stickied"):
            continue
        permalink = post.get("permalink")
        url = post.get("url")
        entries.append({
            "source": "reddit",
            "title": strip_html(post.get("title", "")),
            "url": f"https://www.reddit.com{permalink}" if permalink else url,
            "external_url": url if url and permalink and permalink not in url else None,
            "summary": truncate(strip_html(post.get("selftext", "")), chars),
            "published_at": from_epoch(post.get("created_utc")),
            "community": f"r/{subreddit}",
        })
    return entries


def _parse_atom(content: bytes, subreddit: str, limit: int, chars: int) -> list[dict]:
    """Reddit's .rss is Atom, not RSS 2.0 - hence <feed>/<entry>, not <item>."""
    root = ET.fromstring(content)
    entries = []
    for entry in root.findall(f"{_ATOM}entry")[:limit]:
        link = entry.find(f"{_ATOM}link")
        content_el = entry.find(f"{_ATOM}content")
        post_url = link.get("href") if link is not None else None
        body, external = reddit_content(content_el.text if content_el is not None else "")
        published = entry.findtext(f"{_ATOM}published") or entry.findtext(f"{_ATOM}updated")
        entries.append({
            "source": "reddit",
            "title": strip_html(entry.findtext(f"{_ATOM}title") or ""),
            "url": post_url,
            # Empty on a text-only post; on a link/image post this is the real
            # destination, which is the only substance such an entry carries.
            "external_url": external if external and external != post_url else None,
            "summary": truncate(body, chars),
            "published_at": to_iso(published),
            "community": f"r/{subreddit}",
        })
    return entries


def _fetch_listing(
    url: str, timeframe: str, limit: int, proxy_url: str | None, subreddit: str,
    headers: dict | None = None, chars: int = 1500,
) -> list[dict]:
    request_headers = {"User-Agent": _user_agent()}
    if headers:
        request_headers.update(headers)
    resp = requests.get(
        url,
        params={"t": timeframe, "limit": limit, "raw_json": 1},
        headers=request_headers,
        proxies=_proxies(proxy_url),
        timeout=45,
    )
    resp.raise_for_status()
    if ".rss" in url or "xml" in resp.headers.get("Content-Type", ""):
        return _parse_atom(resp.content, subreddit, limit, chars)
    return _parse_json_listing(resp.json(), subreddit, limit, chars)


def _apply_filters(
    entries: list[dict], patterns: list[str], max_age_days: int, now: datetime
) -> list[dict]:
    """Keyword filter (best-effort; Atom carries no over_18 flag) plus age cut.

    Reddit enforces age server-side via t=month, but Substack's RSS has no
    equivalent - it just serves the most recent N entries however old they are.
    Applying the cut here keeps both sources on the same definition of "recent".
    """
    compiled = [re.compile(p, re.IGNORECASE) for p in (patterns or [])]
    kept = []
    for entry in entries:
        haystack = f"{entry.get('title','')} {entry.get('summary','')}"
        if any(rx.search(haystack) for rx in compiled):
            Actor.log.info("dropped (pattern): %s", (entry.get("title") or "")[:60])
            continue
        if not within_age(entry.get("published_at"), max_age_days, now):
            Actor.log.info(
                "dropped (older than %dd): %s", max_age_days, (entry.get("title") or "")[:60]
            )
            continue
        kept.append(entry)
    return kept


# --------------------------------------------------------------------------
# OAuth path - inert unless credentials exist (see history note 4)
# --------------------------------------------------------------------------

def _reddit_oauth_token(client_id: str, client_secret: str, proxy_url: str | None) -> str:
    resp = requests.post(
        _REDDIT_TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": _user_agent()},
        proxies=_proxies(proxy_url),
        timeout=30,
    )
    if resp.status_code == 401:
        raise RuntimeError("Reddit rejected the client credentials (401)")
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"Reddit returned no access_token: {resp.text[:200]}")
    return token


async def _try_oauth(timeframe: str, limit: int, subreddit: str, chars: int):
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not (client_id and client_secret):
        return None
    proxy_url = await _proxy_for_group("RESIDENTIAL")
    try:
        token = _reddit_oauth_token(client_id, client_secret, proxy_url)
        entries = _fetch_listing(
            f"{_REDDIT_OAUTH_BASE}/r/{subreddit}/top", timeframe, limit, proxy_url,
            subreddit, headers={"Authorization": f"bearer {token}"}, chars=chars,
        )
        return (token, proxy_url, entries)
    except Exception as exc:  # noqa: BLE001 - fall through to the strategy list
        Actor.log.warning("OAuth path failed: %s", exc)
        return None


# --------------------------------------------------------------------------
# Substack
# --------------------------------------------------------------------------

def _substack_items(items, community: str, limit: int, chars: int) -> list[dict]:
    """Shared by the public and private-feed paths - identical row shape.

    `community` is always a sanitized origin for private feeds, never the feed
    URL itself, so a subscriber token cannot reach the dataset.
    """
    entries = []
    for item in items[:limit]:
        # <description> is the editorial subtitle - short and high signal.
        # <content:encoded> is the full article. On a paywalled publication the
        # public feed carries only the free preview here; a subscriber feed
        # carries the whole post, which is the entire point of using one.
        subtitle = strip_html(item.findtext("description") or "")
        body = strip_html(item.findtext(f"{_CONTENT_NS}encoded") or "")
        if body.startswith(subtitle):
            summary = body
        elif subtitle and body:
            summary = f"{subtitle}\n\n{body}"
        else:
            summary = subtitle or body
        entries.append({
            "source": "substack",
            "title": (item.findtext("title") or "").strip(),
            "url": (item.findtext("link") or "").strip(),
            "external_url": None,
            "summary": truncate(summary, chars),
            "published_at": to_iso(item.findtext("pubDate")),
            "community": community,
        })
    return entries


def _fetch_substack_private(feed_url: str, limit: int, chars: int) -> list[dict]:
    """Fetch one subscriber feed URL verbatim - no candidate derivation.

    The URL is a credential. It is never logged, never raised in an exception,
    and never written to a row; only its sanitized origin is. Callers must pass
    it in from a secret env var, never from Actor input, because Actor input is
    echoed into the run record and into whatever prompt invoked the run.
    """
    origin = sanitize_feed_url(feed_url)
    try:
        resp = requests.get(feed_url, timeout=30, headers={"User-Agent": _user_agent()})
        resp.raise_for_status()
        items = ET.fromstring(resp.content).findall("./channel/item")
    except Exception as exc:  # noqa: BLE001 - re-raise with the URL redacted
        # Do NOT interpolate `exc` directly: requests embeds the full request
        # URL in its HTTPError text, which would put the subscriber token into
        # the run log and the run's status message.
        raise RuntimeError(
            f"private feed for {origin} failed: "
            f"{redact_url(exc, feed_url, origin)}"
        ) from None
    if not items:
        raise RuntimeError(
            f"private feed for {origin} parsed but contained no <item> elements "
            "(is the token still valid?)"
        )
    Actor.log.info("private feed OK: %s -> %d items", origin, len(items))
    return _substack_items(items, origin, limit, chars)


def _fetch_substack_rss(pub_url: str, limit: int, chars: int) -> list[dict]:
    """Fetch one publication, trying each candidate feed URL in order.

    A reader-profile link (substack.com/@handle) has no feed of its own, so the
    handle is also tried against the conventional publication host. Tracking
    query params are stripped - appending "/feed" to a URL that still carries
    "?utm_source=share" produces a broken path.
    """
    candidates = substack_feed_candidates(pub_url)
    if not candidates:
        raise ValueError(f"could not derive a feed URL from {pub_url!r}")

    last_error: Exception | None = None
    for feed_url in candidates:
        try:
            resp = requests.get(
                feed_url, timeout=30, headers={"User-Agent": _user_agent()}
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            items = root.findall("./channel/item")
            if not items:
                raise ValueError("feed parsed but contained no <item> elements")
        except Exception as exc:  # noqa: BLE001 - try the next candidate
            Actor.log.info("substack candidate failed: %s -> %s", feed_url, exc)
            last_error = exc
            continue

        if feed_url != candidates[0]:
            Actor.log.info("substack: fell back to %s", feed_url)
        return _substack_items(items, pub_url, limit, chars)

    raise RuntimeError(
        f"no candidate feed worked for {pub_url!r} "
        f"(tried {', '.join(candidates)}): {last_error}"
    )


async def main() -> None:
    async with Actor:
        # Info-level logging was silently suppressed through 0.8, which is why
        # STRATEGY OK / SKIP lines never appeared and every diagnosis had to be
        # inferred from which *warnings* were absent. Force it on.
        logging.getLogger("apify").setLevel(logging.INFO)
        Actor.log.setLevel(logging.INFO)

        actor_input = await Actor.get_input() or {}
        subreddits = actor_input.get("subreddits") or []
        substack_publications = actor_input.get("substack_publications") or []
        max_items = int(actor_input.get("max_items_per_source") or 25)
        timeframe = actor_input.get("reddit_timeframe") or "month"
        filter_titles = actor_input.get("filter_titles") or []
        override = (actor_input.get("reddit_strategy_override") or "").strip()
        chars = int(actor_input.get("summary_max_chars") or 1500)
        max_age_days = int(actor_input.get("max_age_days") or 0)
        now = datetime.now(timezone.utc)

        # One guard covering every requested source. The old input was
        # require_reddit, which only protected Reddit - so a total Substack
        # failure still exited 0 with an empty dataset (observed 2026-08-11).
        # require_reddit is still honoured as a deprecated per-source opt-out.
        fail_on_empty = actor_input.get("fail_on_empty_source")
        if fail_on_empty is None:
            fail_on_empty = True
        legacy_require_reddit = actor_input.get("require_reddit")

        strategies = _STRATEGIES
        if override:
            strategies = [s for s in _STRATEGIES if s[0] == override]
            if not strategies:
                Actor.log.warning(
                    "reddit_strategy_override=%r matches no strategy; using full list",
                    override,
                )
                strategies = _STRATEGIES

        reddit_rows = 0
        reddit_errors: list[str] = []
        winner: tuple[str, str] | None = None
        oauth = None

        if subreddits:
            first, rest = subreddits[0], subreddits[1:]
            entries: list[dict] = []

            oauth = await _try_oauth(timeframe, max_items, first, chars)
            if oauth:
                winner, entries = ("OAUTH", ""), oauth[2]
            else:
                for spec, template in strategies:
                    proxy_url, skip_reason = await _resolve_proxy(spec)
                    url = template.format(sub=first)
                    if skip_reason:
                        Actor.log.info("STRATEGY SKIP    %-26s %s (%s)", spec, url, skip_reason)
                        continue
                    try:
                        entries = _fetch_listing(
                            url, timeframe, max_items, proxy_url, first, chars=chars
                        )
                    except Exception as exc:  # noqa: BLE001 - try the next strategy
                        Actor.log.warning("STRATEGY FAILED  %-26s %s -> %s", spec, url, exc)
                        reddit_errors.append(f"{spec} {url}: {exc}")
                        continue
                    if not entries:
                        Actor.log.warning(
                            "STRATEGY EMPTY   %-26s %s -> HTTP 200 but 0 entries", spec, url
                        )
                        reddit_errors.append(f"{spec} {url}: 200 but 0 entries")
                        continue
                    Actor.log.info(
                        "STRATEGY OK      %-26s %s -> %d entries", spec, url, len(entries)
                    )
                    winner = (spec, template)
                    break

            if winner:
                for entry in _apply_filters(entries, filter_titles, max_age_days, now):
                    await Actor.push_data(entry)
                    reddit_rows += 1

                for subreddit in rest:
                    try:
                        if winner[0] == "OAUTH":
                            more = _fetch_listing(
                                f"{_REDDIT_OAUTH_BASE}/r/{subreddit}/top", timeframe,
                                max_items, oauth[1], subreddit,
                                headers={"Authorization": f"bearer {oauth[0]}"},
                                chars=chars,
                            )
                        else:
                            proxy_url, _ = await _resolve_proxy(winner[0])
                            more = _fetch_listing(
                                winner[1].format(sub=subreddit), timeframe, max_items,
                                proxy_url, subreddit, chars=chars,
                            )
                    except Exception as exc:  # noqa: BLE001 - one bad subreddit is not fatal
                        Actor.log.warning("Reddit fetch failed for r/%s: %s", subreddit, exc)
                        reddit_errors.append(f"r/{subreddit}: {exc}")
                        continue
                    Actor.log.info("r/%s: fetched %d entries", subreddit, len(more))
                    for entry in _apply_filters(more, filter_titles, max_age_days, now):
                        await Actor.push_data(entry)
                        reddit_rows += 1
            else:
                Actor.log.warning("Every Reddit strategy failed or was skipped")

        substack_rows = 0
        substack_errors: list[str] = []
        seen_urls: set[str] = set()

        # Subscriber feeds come from a SECRET env var, never from Actor input:
        # the URL carries a token, and input is echoed into the run record and
        # into whatever prompt invoked the run. Only sanitized origins are ever
        # logged or stored.
        raw_feeds = os.environ.get("SUBSTACK_PRIVATE_FEEDS")
        private_feeds = parse_private_feeds(raw_feeds)
        if private_feeds:
            Actor.log.info(
                "%d private Substack feed(s) configured: %s", len(private_feeds),
                ", ".join(sanitize_feed_url(f) for f in private_feeds),
            )
            # A long URL pasted into a phone terminal can pick up a line break.
            # The prefix still parses as a URL and the configured count still
            # looks right, so the failure surfaces three layers away as a 404 on
            # a nonsense path. Say it here instead.
            dropped = len([p for p in re.split(r"[,\s]+", raw_feeds.strip()) if p]) - len(private_feeds)
            if dropped > 0:
                Actor.log.warning(
                    "SUBSTACK_PRIVATE_FEEDS: ignored %d fragment(s) that are not URLs. "
                    "A long URL split by a paste looks exactly like this.", dropped,
                )
            for feed in private_feeds:
                if looks_truncated(feed):
                    Actor.log.warning(
                        "SUBSTACK_PRIVATE_FEEDS: the entry for %s is only %d characters "
                        "and has no token-bearing path. A subscriber feed URL carries a "
                        "long opaque token - this one looks truncated.",
                        sanitize_feed_url(feed), len(feed),
                    )

        substack_jobs = [("public", p) for p in substack_publications]
        substack_jobs += [("private", f) for f in private_feeds]

        for kind, ref in substack_jobs:
            label = ref if kind == "public" else sanitize_feed_url(ref)
            try:
                if kind == "private":
                    entries = _fetch_substack_private(ref, max_items, chars)
                else:
                    entries = _fetch_substack_rss(ref, max_items, chars)
            except Exception as exc:  # noqa: BLE001 - one bad feed is not fatal
                Actor.log.warning("Substack fetch failed for %s: %s", label, exc)
                substack_errors.append(f"{label}: {exc}")
                continue
            for entry in _apply_filters(entries, filter_titles, max_age_days, now):
                # The same post arrives twice if a publication is listed both as
                # a public URL and as a subscriber feed. Keep the first, which is
                # whichever job ran first - public jobs are ordered first, so a
                # paywalled teaser would win. Prefer configuring one or the other.
                url = entry.get("url") or ""
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                await Actor.push_data(entry)
                substack_rows += 1

        # The run's status message is visible via GET /v2/actor-runs/{id} and in
        # the Console regardless of log level - so the winning strategy is
        # recoverable even if info logging is suppressed again.
        summary = (
            f"strategy={winner[0] if winner else 'NONE'} "
            f"reddit={reddit_rows} substack={substack_rows}"
        )
        Actor.log.info("Done: %s", summary)

        empty_sources = []
        if subreddits and reddit_rows == 0 and legacy_require_reddit is not False:
            detail = "; ".join(reddit_errors) or "no error recorded"
            empty_sources.append(
                f"{len(subreddits)} subreddit(s) requested, 0 rows: {detail}"
            )
        if (substack_publications or private_feeds) and substack_rows == 0:
            detail = "; ".join(substack_errors) or "no error recorded"
            empty_sources.append(
                f"{len(substack_publications) + len(private_feeds)} Substack "
                f"source(s) requested, 0 rows: {detail}"
            )

        if empty_sources:
            message = " | ".join(empty_sources)
            if fail_on_empty:
                await Actor.fail(status_message=message[:1000])
                return
            Actor.log.warning("%s (fail_on_empty_source=false)", message)
        await Actor.set_status_message(summary[:1000])


if __name__ == "__main__":
    asyncio.run(main())
