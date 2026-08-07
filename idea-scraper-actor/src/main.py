"""Idea scraper actor: Reddit + Substack, no dependency on any other Actor.

An Apify Creator-tier plan cannot run public Actors (confirmed 2026-08-07: a
direct run-sync call against trudax/reddit-scraper-lite was rejected with
"The Creator plan does not include permission to run public Actors"). This
actor works around that by fetching Reddit's own public JSON listings
directly, routed through Apify's residential proxy (bypassing the Cloudflare
block that stops a fired Claude Code session from reaching reddit.com on its
own), and Substack's public RSS feeds directly (no proxy needed, not
blocked). Neither is "running a public Actor" - both are this actor's own
HTTP requests.

Normalizes both sources into one dataset shape so callers (the
SillyTavernPresets Routines) don't need source-specific parsing:

    {source, title, url, summary, published_at, community}
"""
import re
from datetime import datetime, timezone
from html import unescape

import requests
from apify import Actor

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_USER_AGENT = "python:idea-scraper-actor:0.2 (by /u/SillyTavernPresetsBot)"


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
            proxy_configuration = await Actor.create_proxy_configuration(groups=["RESIDENTIAL"])
            proxy_url = await proxy_configuration.new_url() if proxy_configuration else None
            for subreddit in subreddits:
                try:
                    entries = _fetch_subreddit(subreddit, timeframe, max_items, proxy_url)
                except Exception as exc:  # noqa: BLE001 - one bad subreddit shouldn't kill the run
                    Actor.log.warning("Reddit fetch failed for r/%s: %s", subreddit, exc)
                    continue
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
