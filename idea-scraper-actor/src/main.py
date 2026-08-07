"""Idea scraper actor: Reddit (via trudax/reddit-scraper-lite) + Substack (public RSS).

Normalizes both sources into one dataset shape so callers (the
SillyTavernPresets Routines) don't need source-specific parsing:

    {source, title, url, summary, published_at, community}
"""
import re
import xml.etree.ElementTree as ET

import requests
from apify import Actor

REDDIT_SCRAPER_ACTOR_ID = "trudax/reddit-scraper-lite"
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_USER_AGENT = "idea-scraper-actor/0.1 (+https://github.com/biggieb327-lgtm/sillytavernpresets)"


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", text or "").strip()


def _normalize_reddit_item(item: dict) -> dict:
    # trudax/reddit-scraper-lite's exact field names are unverified against a
    # live run (no network access at build time) - fall back across the
    # plausible names so a schema drift degrades instead of KeyErrors.
    title = item.get("title") or _strip_html(item.get("body", ""))[:120]
    url = item.get("url") or item.get("permalink") or item.get("link")
    summary = _strip_html(item.get("body") or item.get("selftext") or "")[:500]
    community = (
        item.get("communityName")
        or item.get("parsedCommunityName")
        or item.get("subreddit")
    )
    published_at = item.get("createdAt") or item.get("createdAtIso") or item.get("date")
    return {
        "source": "reddit",
        "title": title,
        "url": url,
        "summary": summary,
        "published_at": published_at,
        "community": community,
    }


def _fetch_substack_rss(pub_url: str, limit: int) -> list[dict]:
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
        reddit_urls = actor_input.get("reddit_urls") or []
        substack_publications = actor_input.get("substack_publications") or []
        max_items = int(actor_input.get("max_items_per_source") or 25)
        reddit_sort = actor_input.get("reddit_sort") or "top"

        if reddit_urls:
            run_input = {
                "startUrls": [{"url": u} for u in reddit_urls],
                "sort": reddit_sort,
                "maxItems": max_items,
                "maxPostCount": max_items,
                "maxComments": 0,
                "skipComments": True,
                "skipUserPosts": True,
                "skipCommunity": True,
                "searchPosts": True,
                "searchComments": False,
                "searchCommunities": False,
                "searchUsers": False,
                "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
            }
            Actor.log.info(
                "Calling %s for %d start URL(s)", REDDIT_SCRAPER_ACTOR_ID, len(reddit_urls)
            )
            run = await Actor.call(REDDIT_SCRAPER_ACTOR_ID, run_input)
            if run is None:
                Actor.log.warning("Reddit scraper sub-run failed to start; skipping Reddit")
            else:
                dataset = await Actor.open_dataset(id=run.default_dataset_id)
                async for item in dataset.iterate_items():
                    await Actor.push_data(_normalize_reddit_item(item))

        for pub_url in substack_publications:
            try:
                entries = _fetch_substack_rss(pub_url, max_items)
            except Exception as exc:  # noqa: BLE001 - one bad feed shouldn't kill the run
                Actor.log.warning("Substack fetch failed for %s: %s", pub_url, exc)
                continue
            for entry in entries:
                await Actor.push_data(entry)
