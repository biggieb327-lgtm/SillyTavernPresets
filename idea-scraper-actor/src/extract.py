"""Content extraction and normalization, split out of main.py so it can be
tested against real feed fixtures without importing the apify SDK.

Every row from every source ends up in the same shape:

    {source, title, url, external_url, summary, published_at, community}

`published_at` is always ISO 8601 (or None) - Reddit's Atom gives ISO and
Substack's RSS gives RFC 2822, and passing both through unchanged produced a
dataset that could not be sorted chronologically across sources.
"""
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")

# Reddit appends this to every entry's content. On a link/image post it is the
# *entire* content, so stripping it is what distinguishes "no body" from "body".
_BOILERPLATE_RE = re.compile(
    r"\s*submitted\s+by\s*/u/\S+\s*\[link\]\s*\[comments\]\s*$",
    re.IGNORECASE,
)
_LINK_HREF_RE = re.compile(r'<a\s+href="([^"]+)"\s*>\s*\[link\]', re.IGNORECASE)


def strip_html(text: str) -> str:
    """Tags out, entities decoded, whitespace collapsed but newlines kept."""
    text = _HTML_TAG_RE.sub("", unescape(text or ""))
    text = _WHITESPACE_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANKLINES_RE.sub("\n\n", text).strip()


def to_iso(value: str | None) -> str | None:
    """Normalize ISO-8601 or RFC-2822 to ISO 8601. Returns None if unparseable.

    Returning None rather than the raw string is deliberate: a mixed-format
    column is worse than a missing value, because it fails at sort time in the
    consumer instead of here.
    """
    if not value:
        return None
    raw = value.strip()
    try:
        return datetime.fromisoformat(raw).isoformat()
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def from_epoch(seconds) -> str | None:
    if not seconds:
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


def reddit_content(raw_html: str | None) -> tuple[str, str | None]:
    """Return (body_text, external_url) from a Reddit Atom <content> blob.

    Reddit wraps the whole entry in a <table> when the post has a thumbnail, so
    the body cannot be found by splitting on </table> - strip tags first, then
    remove the trailing 'submitted by ... [link] [comments]' boilerplate. What
    survives is the actual selftext, empty for a link or image post.
    """
    raw = unescape(raw_html or "")
    match = _LINK_HREF_RE.search(raw)
    external_url = match.group(1) if match else None
    body = _BOILERPLATE_RE.sub("", strip_html(raw)).strip()
    return body, external_url


def truncate(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit]
    # Prefer a word boundary, but only if one is reasonably near the end.
    space = cut.rfind(" ")
    if space > limit * 0.8:
        cut = cut[:space]
    return cut.rstrip() + "…"


# --- Substack URL handling -------------------------------------------------
# Users paste whatever they have: a publication URL, a custom domain, or a
# reader-profile link with tracking params. Appending "/feed" blindly to
# "https://substack.com/@name?utm_source=share" produces a URL with the query
# string in the middle, which is how this was found.

_PROFILE_RE = re.compile(r"^/@([A-Za-z0-9_.-]+)/?$")


def substack_feed_candidates(raw_url: str) -> list[str]:
    """Ordered feed URLs to try for a user-supplied Substack reference.

    Query strings and fragments are always dropped. A reader-profile link
    (substack.com/@handle) is not a publication and has no feed of its own, so
    the handle is mapped to the conventional publication host as well.
    """
    from urllib.parse import urlsplit

    parsed = urlsplit((raw_url or "").strip())
    scheme = parsed.scheme or "https"
    host = (parsed.netloc or "").lower()
    path = parsed.path.rstrip("/")

    if not host:
        return []

    profile = _PROFILE_RE.match(path or "/")
    if host in ("substack.com", "www.substack.com") and profile:
        handle = profile.group(1)
        return [
            f"https://{handle}.substack.com/feed",
            f"https://substack.com/feed/@{handle}",
        ]

    base = f"{scheme}://{host}{path}"
    return [base if path.endswith("/feed") else f"{base}/feed"]


def within_age(published_iso: str | None, max_age_days: int, now: datetime) -> bool:
    """Age filter. Undated entries are kept - absence of a date is not evidence
    of being old, and dropping them would silently lose rows."""
    if not max_age_days:
        return True
    if not published_iso:
        return True
    try:
        published = datetime.fromisoformat(published_iso)
    except ValueError:
        return True
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return (now - published).days <= max_age_days


# --- Private (subscriber) Substack feeds -----------------------------------
# A Substack private RSS URL carries a token that grants access to paid content.
# It is a credential: it must never reach the repo, the Actor input, the run log,
# or the output dataset. It is read from a secret env var, and every row it
# produces is labelled with the sanitized publication origin instead.

def parse_private_feeds(raw: str | None) -> list[str]:
    """Split a secret env var into feed URLs. Accepts comma/newline/space."""
    if not raw:
        return []
    parts = re.split(r"[,\s]+", raw.strip())
    return [p for p in parts if p.startswith(("http://", "https://"))]


def sanitize_feed_url(url: str) -> str:
    """scheme://host, dropping path, query and fragment.

    Used for the `community` field so a token embedded in a private feed path
    or query string never lands in the dataset that callers read and quote.
    """
    from urllib.parse import urlsplit

    parsed = urlsplit((url or "").strip())
    if not parsed.netloc:
        return "(unknown publication)"
    return f"{parsed.scheme or 'https'}://{parsed.netloc}"


def redact_url(text, url: str, origin: str, limit: int = 240) -> str:
    """Strip a credential URL out of an error message.

    `requests` puts the full request URL in its HTTPError text
    ("404 Client Error: Not Found for url: https://host/feed/p/TOKEN"), so
    interpolating an exception into a message leaks the token into the run log
    and the run's status message. This removes it. Added in 0.14 after exactly
    that happened on run pVRaNhKrEbRgsxgVJ.
    """
    out = str(text)
    for form in (url, (url or "").rstrip("/")):
        if form:
            out = out.replace(form, f"{origin}/<redacted>")
    return out[:limit]


def looks_truncated(url: str) -> bool:
    """A private feed URL carries a long opaque token. A short one is a fragment.

    A long URL pasted into a phone terminal can acquire a line break, leaving a
    prefix that still parses as a URL - which is how two feeds 404'd at '.../p'
    while the configured count looked healthy.
    """
    parsed_path = (url or "").split("://", 1)[-1]
    return len(url or "") < 45 or "/" not in parsed_path.strip("/")
