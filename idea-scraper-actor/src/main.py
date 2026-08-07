"""Idea scraper actor: Reddit + Substack, no dependency on any other Actor.

An Apify Creator-tier plan cannot run public Actors (confirmed 2026-08-07: a
direct run-sync call against trudax/reddit-scraper-lite was rejected with
"The Creator plan does not include permission to run public Actors"). This
actor works around that by fetching Reddit's own public JSON listings and
Substack's public RSS feeds directly - neither is "running a public Actor",
both are this actor's own HTTP requests. Reddit is meant to go through one
of Apify's own proxy groups to bypass the Cloudflare block that stops a
fired Claude Code session from reaching reddit.com directly; **as of
2026-08-07 that proxy step itself fails with an account permission error
on every group**, and a fail-soft fallback to an unproxied request gets a
genuine 403 from Reddit - so Reddit fetching does not currently work end
to end. Substack needs no proxy and is unaffected. See README.md.

Normalizes both sources into one dataset shape so callers (the
SillyTavernPresets Routines) don't need source-specific parsing:

    {source, title, url, summary, published_at, community}
"""
import asyncio
import re
from datetime import datetime, timezone
from html import unescape

import requests
from apify import Actor

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_USER_AGENT = "python:idea-scraper-actor:0.4 (by /u/SillyTavernPresetsBot)"
# create_proxy_configuration() currently fails for EVERY group on this account
# with "Insufficient permissions" (confirmed 2026-08-07) - the failure is inside
# apify-client's user().get() call that fetches the proxy password, before group
# choice is even relevant, so this is an account/token permission gap, not a
# group-availability one (RESIDENTIAL's availableCount:0, checked the same day
# via GET /v2/users/me, turned out to be a red herring - BUYPROXIES94952's 27
# available proxies didn't help either, same error). Kept as the target group
# for whenever that permission is granted; see main()'s try/except for the
# fail-soft fallback to an unproxied fetch, which itself gets a genuine Reddit
# 403 ("Blocked") - so as of 2026-08-07 there is no working path to Reddit from
# this actor, proxied or not. See README.md.
_REDDIT_PROXY_GROUP = "BUYPROXIES94952"


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", unescape(text or "")).strip()


def _fetch_subreddit(subreddit: str, timeframe: str, limit: int, proxy_url: str | None) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/top.json"
    resp = requests.get(
        url,
        params={"t": timeframe, "limit": limit, "raw_json": 1},
        headers={"User-Agent": _USER_AGENT},
        proxies={"http": proxy_url, "https": proxy_url} if proxy_url else None,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    entries = []
    for child in payload.get("data", {}).get("children", [])[:limit]:
        post = child.get("data", {})
        if post.get("over_18") or post.get("stickied"):
            continue
        permalink = post.get("permalink")
        entries.append({
            "source": "reddit",
            "title": _strip_html(post.get("title", "")),
            "url": f"https://www.reddit.com{permalink}" if permalink else post.get("url"),
            "summary": _strip_html(post.get("selftext", ""))[:500],
            "published_at": datetime.fromtimestamp(
                post.get("created_utc", 0), tz=timezone.utc
            ).isoformat() if post.get("created_utc") else None,
            "community": f"r/{subreddit}",
        })
    return entries


def _fetch_substack_rss(pub_url: str, limit: int) -> list[dict]:
    import xml.etree.ElementTree as ET

    pub_url = pub_url.rstrip("/")
    feed_url = pub_url if pub_url.endswith("/feed") else f"{pub_url}/feed"
    resp = requests.get(feed_url, timeout=30, headers={"User-Agent": _USER_AGENT})
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    entries = []
    for item in root.findall("./channel/item")[:limit]:
        entries.append({
            "source": "substack",
            "title": (item.findtext("title") or "").strip(),
            "url": (item.findtext("link") or "").strip(),
            "summary": _strip_html(item.findtext("description") or "")[:500],
            "published_at": (item.findtext("pubDate") or "").strip(),
            "community": pub_url,
        })
    return entries


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        subreddits = actor_input.get("subreddits") or []
        substack_publications = actor_input.get("substack_publications") or []
        max_items = int(actor_input.get("max_items_per_source") or 25)
        timeframe = actor_input.get("reddit_timeframe") or "month"

        if subreddits:
            proxy_url = None
            try:
                proxy_configuration = await Actor.create_proxy_configuration(groups=[_REDDIT_PROXY_GROUP])
                proxy_url = await proxy_configuration.new_url() if proxy_configuration else None
            except Exception as exc:  # noqa: BLE001 - proxy is a nice-to-have, not load-bearing
                Actor.log.warning(
                    "Proxy configuration failed (%s) - fetching Reddit directly from "
                    "Apify's own compute IP instead of group %r", exc, _REDDIT_PROXY_GROUP,
                )
            if not proxy_url:
                Actor.log.warning("No proxy URL - fetching Reddit directly, may hit a Cloudflare block")
            for subreddit in subreddits:
                try:
                    entries = _fetch_subreddit(subreddit, timeframe, max_items, proxy_url)
                except Exception as exc:  # noqa: BLE001 - one bad subreddit shouldn't kill the run
                    Actor.log.warning("Reddit fetch failed for r/%s: %s", subreddit, exc)
                    continue
                Actor.log.info("r/%s: fetched %d entries", subreddit, len(entries))
                for entry in entries:
                    await Actor.push_data(entry)

        for pub_url in substack_publications:
            try:
                entries = _fetch_substack_rss(pub_url, max_items)
            except Exception as exc:  # noqa: BLE001 - one bad feed shouldn't kill the run
                Actor.log.warning("Substack fetch failed for %s: %s", pub_url, exc)
                continue
            for entry in entries:
                await Actor.push_data(entry)


if __name__ == "__main__":
    # This was missing entirely through v0.2 and v0.3.0-0.3.2: `main()` was defined
    # but never invoked, so `python3 -m src.main` ran to a clean exit (0) having
    # done nothing - no input read, no fetch, no log line - which looks identical
    # to a real empty result. Confirmed 2026-08-07 by adding a log line as the very
    # first statement in main() and finding it never appears in any run's log.
    asyncio.run(main())
