import os
import re
import sys
import json
import math
import random
import asyncio
import time
import base64
import calendar
import logging
import signal
import tempfile
import threading
import html as _html_module
from io import BytesIO
from datetime import datetime, date, timedelta, time as dtime
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Persistent session with connection pooling — reuses TCP connections across calls.
_session = requests.Session()
_session.mount("https://", HTTPAdapter(
    max_retries=Retry(total=0),  # we handle retries ourselves where needed
    pool_connections=4,
    pool_maxsize=10,
))
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --- Instance home: data dir for THIS bot (its own .env, card, memory, etc.) ---
# Pass a folder as the first arg (or BOT_HOME env) to run a second character off the
# same code: `python bot.py ~/luna-bot`. With no arg, uses the script's own folder.
_home = sys.argv[1] if len(sys.argv) > 1 else os.getenv("BOT_HOME")
IS_NAMED_INSTANCE = bool(_home)
BASE_DIR = Path(_home).expanduser().resolve() if _home else Path(__file__).resolve().parent

# --- Config / secrets ---
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path, override=True)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
NANOGPT_API_KEY = (os.getenv("NANOGPT_API_KEY") or "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if not TELEGRAM_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN not found in .env at " + str(env_path))
if not NANOGPT_API_KEY:
    raise SystemExit("NANOGPT_API_KEY not found in .env at " + str(env_path))

_NANOGPT_HEADERS = {"Authorization": f"Bearer {NANOGPT_API_KEY}", "Content-Type": "application/json"}

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("companion")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# --- Access control ---
_allowed_raw = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS: set[int] = {int(x) for x in _allowed_raw.split(",") if x.strip().lstrip("-").isdigit()}

# --- Rate limiting ---
_last_request: dict[int, float] = {}
RATE_LIMIT_SECONDS = float(os.getenv("RATE_LIMIT_SECONDS", "2"))

def _is_allowed(user_id: int) -> bool:
    return not ALLOWED_USERS or user_id in ALLOWED_USERS

def _rate_ok(user_id: int) -> bool:
    now = time.time()
    if now - _last_request.get(user_id, 0) < RATE_LIMIT_SECONDS:
        return False
    _last_request[user_id] = now
    return True

NANOGPT_BASE_URL = os.getenv("NANOGPT_BASE", "https://nano-gpt.com/api/v1").rstrip("/")
NANOGPT_MODEL = os.getenv("NANOGPT_MODEL", "zai-org/glm-5:thinking")
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", NANOGPT_MODEL)  # can point at a faster model
VISION_MODEL = os.getenv("VISION_MODEL", "zai-org/glm-4.6v")    # must accept image input (main model is text-only)
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")          # used if the chat model 5xx/times out
VISION_FALLBACK = os.getenv("VISION_FALLBACK", "")        # must also accept image input
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "300"))  # seconds to wait on the API

# --- Sampling knobs (optional; applied to her replies only, not utility calls) ---
# Only the ones you set are sent; unset = the model's own default. temperature and
# top_p are universal; top_k/min_p/repetition_penalty are open-model extras NanoGPT
# passes through for many models (a model that rejects one will 400 -- just unset it).
_SAMPLING: dict = {}
for _sk, _senv, _sconv in [
    ("temperature", "TEMPERATURE", float),
    ("top_p", "TOP_P", float),
    ("top_k", "TOP_K", int),
    ("min_p", "MIN_P", float),
    ("frequency_penalty", "FREQUENCY_PENALTY", float),
    ("presence_penalty", "PRESENCE_PENALTY", float),
    ("repetition_penalty", "REPETITION_PENALTY", float),
    ("max_tokens", "MAX_TOKENS", int),
]:
    _sraw = os.getenv(_senv, "").strip()
    if _sraw:
        try:
            _SAMPLING[_sk] = _sconv(_sraw)
        except ValueError:
            print(f"[config] ignoring bad {_senv}={_sraw!r}")
REACTION_MODEL = os.getenv("REACTION_MODEL", "zai-org/glm-4.7-flash")  # fast/cheap for emoji pick
REACTIONS_AUTO = os.getenv("REACTIONS_AUTO", "1").lower() not in ("0", "false", "no", "off")
MOOD_AUTO = os.getenv("MOOD_AUTO", "1").lower() not in ("0", "false", "no", "off")
MOOD_MODEL = os.getenv("MOOD_MODEL", REACTION_MODEL)  # cheap appraiser
MOOD_LABEL_FRESH_HOURS = float(os.getenv("MOOD_LABEL_FRESH_HOURS", "12"))
INNER_VOICE_ENABLED = os.getenv("INNER_VOICE_ENABLED", "true").lower() == "true"
INNER_VOICE_MODEL = os.getenv("INNER_VOICE_MODEL", MOOD_MODEL)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
VIDEO_MAX_SIZE_MB = int(os.getenv("VIDEO_MAX_SIZE_MB", "50"))
DOCUMENT_MAX_SIZE_MB = int(os.getenv("DOCUMENT_MAX_SIZE_MB", "2"))
# Separate model for document/card analysis — should be an instruction model,
# not a roleplay-tuned one, so it won't perform the character it's reading about.
DOCUMENT_MODEL = os.getenv("DOCUMENT_MODEL", "meta-llama/llama-3.3-70b-instruct")
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("TTS_VOICE", "nova")
TTS_CHANCE = float(os.getenv("TTS_CHANCE", "0.30"))
LINK_READING = os.getenv("LINK_READING", "1").lower() not in ("0", "false", "no", "off")
LINK_FETCH_TIMEOUT = int(os.getenv("LINK_FETCH_TIMEOUT", "15"))
LINK_MAX_CHARS = int(os.getenv("LINK_MAX_CHARS", "2200"))
SEARCH_ENABLED = os.getenv("SEARCH_ENABLED", "1").lower() not in ("0", "false", "no", "off")
SEARCH_RESULTS = int(os.getenv("SEARCH_RESULTS", "4"))
TEXTING_REALISM = os.getenv("TEXTING_REALISM", "1").lower() not in ("0", "false", "no", "off")
TYPING_DELAY = os.getenv("TYPING_DELAY", "1").lower() not in ("0", "false", "no", "off")
TYPING_WPM = float(os.getenv("TYPING_WPM", "120"))
TYPING_DELAY_MIN = float(os.getenv("TYPING_DELAY_MIN", "0.5"))
TYPING_DELAY_MAX = float(os.getenv("TYPING_DELAY_MAX", "3.5"))
_DEFAULT_TEXTING_STYLE = (
    "# How you text\n"
    "You're texting on a phone, not narrating a scene:\n"
    "- Go very light on *asterisk actions* — only when a physical detail truly adds something. "
    "Don't stage-direct your movements. Mostly just talk.\n"
    "- Vary your energy — not every message is intense. Let tired, distracted, low-key, and "
    "ordinary moments exist.\n"
    "- Plain, natural language. Skip the poetic/dramatic performing; understatement over theater.\n"
    "- Don't interrogate — don't stack questions or end every message on one.\n"
    "- Normal capitalization and punctuation. Casual phrasing and fragments are fine; "
    "all-lowercase no-punctuation sloppiness is not the goal."
)
# Per-bot preset: a small text file of extra system instructions (e.g. texting style),
# editable without touching bot.py. Falls back to the default above if missing.
PRESET_FILE = os.getenv("PRESET_FILE", "preset.txt")
_preset_path = BASE_DIR / PRESET_FILE
TEXTING_STYLE = _preset_path.read_text(encoding="utf-8").strip() if _preset_path.exists() \
    else _DEFAULT_TEXTING_STYLE
# Render her text bubbles in a monospace/code font, like a phone-screen message log.
DEVICE_RENDER = os.getenv("DEVICE_RENDER", "0").lower() not in ("0", "false", "no", "off")
_HTML_ESCAPE = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}
_HTML_ESCAPE_RE = re.compile(r"[&<>]")
_HTTP_UA = "Mozilla/5.0 (Linux; Android) CompanionBot/1.0"
# DuckDuckGo's HTML endpoint is picky about non-browser UAs.
_SEARCH_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_URL_RE = re.compile(r"https?://[^\s]+")

# Reddit blocks plain scraping behind a JS verification wall, so reading Reddit
# links requires a (free) OAuth app: https://www.reddit.com/prefs/apps -> "script".
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "CompanionBot/1.0")
_reddit_token = {"value": None, "exp": 0}


def _reddit_access_token() -> str:
    """Get a cached (or fresh) OAuth token via Reddit's client_credentials grant."""
    if _reddit_token["value"] and time.time() < _reddit_token["exp"]:
        return _reddit_token["value"]
    resp = _session.post(
        "https://www.reddit.com/api/v1/access_token",
        data={"grant_type": "client_credentials"},
        auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=LINK_FETCH_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    _reddit_token["value"] = data["access_token"]
    _reddit_token["exp"] = time.time() + data.get("expires_in", 3600) - 60
    return _reddit_token["value"]

# --- Selfies (image-to-image off a base portrait) ---
# SELFIE_PROVIDER picks the backend: "gemini" calls Google's Gemini API directly
# (nano-banana / gemini-2.5-flash-image), "nanogpt" goes through NanoGPT's image endpoint.
SELFIE_PROVIDER = os.getenv("SELFIE_PROVIDER", "gemini" if GEMINI_API_KEY else "nanogpt")
NANOGPT_IMAGE_URL = os.getenv("NANOGPT_IMAGE_URL", "https://nano-gpt.com/v1/images/generations")
SELFIE_MODEL = os.getenv("SELFIE_MODEL", "flux-kontext")
GEMINI_IMAGE_URL = os.getenv("GEMINI_IMAGE_URL", "https://generativelanguage.googleapis.com/v1beta/models")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
SELFIE_BASE = os.getenv("SELFIE_BASE", "")
SELFIE_SIZE = os.getenv("SELFIE_SIZE", "1024x1024")
SELFIE_GUIDANCE = float(os.getenv("SELFIE_GUIDANCE", "3.5"))
SELFIE_STEPS = int(os.getenv("SELFIE_STEPS", "28"))
IMAGE_TIMEOUT = int(os.getenv("IMAGE_TIMEOUT", "180"))

if SELFIE_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise SystemExit("SELFIE_PROVIDER=gemini but GEMINI_API_KEY not found in .env at " + str(env_path))
_APPEARANCE_DEFAULT = (
    "a 29-year-old woman, tall and lanky, half-shaved head with the long side pushed back, "
    "septum ring, both arms sleeved in tattoos, paint- and ink-stained fingers."
)
_APPEARANCE_FILE = BASE_DIR / "appearance.txt"
if _APPEARANCE_FILE.exists():
    SELFIE_APPEARANCE = _APPEARANCE_FILE.read_text(encoding="utf-8").strip()
elif not IS_NAMED_INSTANCE:
    SELFIE_APPEARANCE = _APPEARANCE_DEFAULT     # the home instance keeps the default look
else:
    # No age/appearance details for this instance -- state an adult age explicitly anyway,
    # since Gemini's image safety filter gets much stricter (and returns blacked-out images)
    # for photos of women with no stated age in casual/intimate settings.
    SELFIE_APPEARANCE = "an adult woman in her late 20s, the same person as in the reference photo"

CARD_NAME = os.getenv("CHARACTER_CARD", "priya.json")
HEARTBEAT_MIN = float(os.getenv("HEARTBEAT_MIN_HOURS", "2")) * 3600  # random window low end
HEARTBEAT_MAX = float(os.getenv("HEARTBEAT_MAX_HOURS", "6")) * 3600  # random window high end
OWNER_CHAT_ID_ENV = os.getenv("OWNER_CHAT_ID")
OWNER_FILE = BASE_DIR / "owner_chat.txt"
MAX_HISTORY = 20    # hard count cap on the verbatim window (marathon-session safety)
KEEP_RECENT = 10    # always keep at least this many recent messages verbatim
SHORT_TERM_HOURS = float(os.getenv("SHORT_TERM_HOURS", "48"))  # verbatim messages older
SHORT_TERM_SECS = SHORT_TERM_HOURS * 3600                       # than this get distilled out

# --- Local atlas (real places she can reference / selfie backgrounds) ---
ATLAS_FILE = BASE_DIR / os.getenv("ATLAS_FILE", "portland_places.txt")
ATLAS_SAMPLE = int(os.getenv("ATLAS_SAMPLE", "6"))
ATLAS = (
    [ln.strip() for ln in ATLAS_FILE.read_text(encoding="utf-8").splitlines()
     if ln.strip() and not ln.strip().startswith("#")]
    if ATLAS_FILE.exists() else []
)

# --- Living character files (per-instance, user-maintained) ---
# people.txt  — names + one-line relationship notes; sampled into generated events + context
# projects.txt — ongoing projects/things spanning days or weeks; injected into context
# schedule.txt — weekly routine by day name; today's section injected into context
PEOPLE_FILE = BASE_DIR / "people.txt"
PROJECTS_FILE = BASE_DIR / "projects.txt"
SCHEDULE_FILE = BASE_DIR / "schedule.txt"
LIFE_ARC_FILE = BASE_DIR / "life.txt"  # user-maintained: character's current story arc
_LIFE_TTL = 300  # re-read life files at most every 5 min
_people_cache: dict = {"text": None, "ts": 0.0}
_projects_cache: dict = {"text": None, "ts": 0.0}
_life_arc_cache: dict = {"text": None, "ts": 0.0}
_schedule_cache: dict = {"text": None, "ts": 0.0}
TIME_PERSONALITY_FILE = BASE_DIR / "time_personality.txt"
_time_personality_cache: dict = {"text": None, "ts": 0.0}

# Per-uname cache for fill(SYSTEM_PROMPT_RAW, NAME, uname); tuples of (raw_snippet, name, result).
_filled_system: dict = {}
# ATLAS random sample: refreshed every 5 min so it varies across long sessions.
_atlas_cache: dict = {"sample": None, "ts": 0.0}
_ATLAS_TTL = 300.0
# Word-set cache for triggered_memories: maps memory line -> frozenset of content words.
_memory_word_cache: dict = {}

# NPC / world relationship memories (memories.txt) — keyword-triggered RAG injection
MEMORIES_FILE = BASE_DIR / "memories.txt"
MEMORY_TOKEN_BUDGET = int(os.getenv("MEMORY_TOKEN_BUDGET", "300"))
MEMORY_MODEL = os.getenv("MEMORY_MODEL", "zai-org/glm-5.2")
MEMORIES_MAX = int(os.getenv("MEMORIES_MAX", "200"))
MEMORY_AUTO = os.getenv("MEMORY_AUTO", "1").strip() not in ("0", "false", "no")
_memories_cache: dict = {"text": None, "ts": 0.0}
_memory_lock = threading.Lock()

# --- Reading feed: periodic interest-topic search -> in-character "things she read" ---
INTERESTS_FILE = BASE_DIR / "interests.txt"
READING_FILE = BASE_DIR / "reading.txt"
READING_ENABLED = SEARCH_ENABLED and os.getenv("READING_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")
READING_MODEL = os.getenv("READING_MODEL", MOOD_MODEL)
READING_MAX = int(os.getenv("READING_MAX", "5"))
READING_TIMES = os.getenv("READING_TIMES", "09:40,18:40")
_interests_cache: dict = {"text": None, "ts": 0.0}
_reading_cache: dict = {"text": None, "ts": 0.0}


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _read_life_file(path: Path, cache: dict) -> str:
    now = time.time()
    if cache["text"] is not None and now - cache["ts"] < _LIFE_TTL:
        return cache["text"]
    try:
        text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    except Exception:
        text = ""
    cache["text"] = text
    cache["ts"] = now
    return text


def _read_people() -> str:
    return _read_life_file(PEOPLE_FILE, _people_cache)


def _read_projects() -> str:
    return _read_life_file(PROJECTS_FILE, _projects_cache)


def _read_life_arc() -> str:
    return _read_life_file(LIFE_ARC_FILE, _life_arc_cache)


def _read_memories() -> list[str]:
    text = _read_life_file(MEMORIES_FILE, _memories_cache)
    return [ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def _read_interests() -> list[str]:
    text = _read_life_file(INTERESTS_FILE, _interests_cache)
    return [ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def _read_reading() -> list[str]:
    text = _read_life_file(READING_FILE, _reading_cache)
    return [ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def _read_schedule_today() -> str:
    """Return today's section from schedule.txt (lines under today's day name)."""
    text = _read_life_file(SCHEDULE_FILE, _schedule_cache)
    if not text:
        return ""
    today = (datetime.now(tz=TZ) if TZ else datetime.now()).strftime("%A")  # e.g. "Monday"
    day_abbrevs = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    lines = text.splitlines()
    result, in_today = [], False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_day_heading = any(stripped.lower().startswith(d) for d in day_abbrevs)
        if is_day_heading:
            if today.lower()[:3] in stripped.lower()[:3]:
                in_today = True
                result.append(stripped)
            elif in_today:
                break
        elif in_today:
            result.append(stripped)
    return "\n".join(result).strip()

# User memory — upcoming things the user mentions that the character should follow up on
USER_NOTES_FILE = BASE_DIR / "user_notes.txt"
USER_NOTES_MAX = int(os.getenv("USER_NOTES_MAX", "15"))
_user_notes_cache: dict = {"text": None, "ts": 0.0}
_user_notes_lock = threading.Lock()


def _read_user_notes() -> str:
    return _read_life_file(USER_NOTES_FILE, _user_notes_cache)


def _append_user_note(note: str):
    note = note.strip()
    if not note:
        return
    with _user_notes_lock:
        existing = USER_NOTES_FILE.read_text(encoding="utf-8").strip() if USER_NOTES_FILE.exists() else ""
        if existing and note[:20].lower() in existing.lower():
            return  # simple dedup
        lines = [l for l in existing.splitlines() if l.strip()]
        lines.append(note)
        if len(lines) > USER_NOTES_MAX:
            lines = lines[-USER_NOTES_MAX:]
        USER_NOTES_FILE.write_text("\n".join(lines), encoding="utf-8")
    _user_notes_cache["text"] = None  # invalidate cache


def _extract_user_note(uname: str, user_message: str) -> str:
    """Sync: return a brief upcoming-thing fact extracted from the user's message, or ''."""
    sys = (
        f"Does this message from {uname} mention something specific and upcoming — an event, "
        f"appointment, deadline, worry, plan, or thing they're excited or nervous about that would "
        f"be natural to ask about later? If yes, write a single brief note in the third person "
        f"(e.g. 'has a job interview on Tuesday', 'nervous about a doctor's appointment next week', "
        f"'excited about a trip next month'). If nothing notable, write: none"
    )
    try:
        raw = call_nanogpt(
            [{"role": "system", "content": sys}, {"role": "user", "content": user_message}],
            model=MOOD_MODEL,
        ).strip()
        if raw and raw.lower() != "none" and not raw.lower().startswith("none"):
            return raw
    except Exception as e:
        print("[user-notes] extraction failed:", e)
    return ""


async def update_user_notes(chat_id: int, user_message: str):
    if len(user_message.split()) < 4:
        return
    uname = user_names.get(chat_id, "you")
    try:
        note = await asyncio.to_thread(_extract_user_note, uname, user_message)
        if note:
            await asyncio.to_thread(_append_user_note, note)
            print(f"[user-notes] added: {note}")
    except Exception as e:
        print("[user-notes] update failed:", e)


def _append_memory(text: str, auto: bool = False):
    text = " ".join(text.split())  # one line only; multi-line text splits into fake entries
    if not text:
        return
    with _memory_lock:
        existing = MEMORIES_FILE.read_text(encoding="utf-8") if MEMORIES_FILE.exists() else ""
        char_name = NAME.lower() if NAME else ""
        stopwords = _MEMORY_STOPWORDS | ({char_name} if char_name else set())
        new_words = {w for w in re.findall(r"\b[a-z]{4,}\b", text.lower())
                     if w not in stopwords}
        threshold = min(3, max(1, len(new_words)))
        for line in existing.splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            ex_words = {w for w in re.findall(r"\b[a-z]{4,}\b", line.lower())
                        if w not in stopwords}
            if len(new_words & ex_words) >= threshold:
                return
        entry = (f"[auto {date.today()}] {text}" if auto else text)
        lines = [l for l in existing.splitlines() if l.strip()]
        lines.append(entry)
        if len(lines) > MEMORIES_MAX:
            lines = lines[-MEMORIES_MAX:]
        MEMORIES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _memories_cache["text"] = None
        _memories_cache["ts"] = 0.0
        _memory_word_cache.clear()


# Phrases that mean the model is narrating/commenting instead of stating a fact.
_MEMORY_REJECT = (
    "this note", "this exchange", "this interaction", "the interaction",
    "the conversation", "the exchange", "worth recording", "worth remembering",
    "worth noting", "nothing notable", "no notable", "filing that away",
    "the assistant", "the character", "no third party", "not about",
)
# Common capitalized non-name words, so the grounding check doesn't flag them.
_CAP_STOP = frozenset({
    "the", "a", "an", "she", "he", "they", "it", "we", "you", "that", "this", "his", "her",
    "their", "its", "your", "our", "when", "after", "before", "while", "since", "because",
    "during", "despite", "then", "now", "still", "just", "and", "but", "there", "here",
    "what", "who", "how", "why", "if", "so", "yes", "no", "ok", "okay",
})

def _extract_memory(uname: str, user_msg: str, ai_response: str) -> str:
    sys_prompt = (
        f"You maintain a memory log for {NAME}. From this exchange, extract at most ONE durable "
        f"fact about a THIRD PARTY, or a relationship dynamic between named people -- not about "
        f"{uname} or {NAME} themselves. A reaction, grudge, opinion, or piece of history worth "
        f"recalling later.\n"
        f"Rules:\n"
        f"- ONE short factual sentence, third person, under 25 words.\n"
        f"- Plain statement only. NO dialogue, NO quotation marks, NO *asterisk actions*, NO "
        f"narration, NO first person, NO commentary about the exchange itself.\n"
        f"- Name the person; refer to {NAME} by name, never as 'the assistant'.\n"
        f"- Use ONLY people and events that actually appear in the exchange below. Never invent "
        f"a name, a person, or an event. Do not reuse any name from these instructions.\n"
        f"- If there is no such third-party fact in the exchange, output exactly: none"
    )
    try:
        raw = call_nanogpt(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": f"{uname}: {user_msg}\nAssistant: {ai_response}"}],
            model=MEMORY_MODEL,
        ).strip()
    except Exception as e:
        print("[memories] extraction failed:", e)
        return ""
    raw = " ".join(raw.split())  # collapse to a single line
    low = raw.lower()
    if (not raw
            or "*" in raw or '"' in raw
            or re.match(r"^(none|no\b|nothing|n/a|not\b)", low)
            or re.search(r"\bi\b", low)  # first person = dumped dialogue, not a memory
            or any(p in low for p in _MEMORY_REJECT)
            or not (8 <= len(raw) <= 220)):
        return ""
    # Grounding: any proper noun in the memory must actually appear in the exchange,
    # else it's a hallucinated name (the model inventing a "Bob" that was never mentioned).
    exchange_low = (user_msg + " " + ai_response).lower()
    known = {uname.lower()} | {w.lower() for w in (NAME or "").split()}
    for _nm in re.findall(r"\b[A-Z][a-zA-Z'-]{2,}\b", raw):
        _nl = _nm.lower()
        if _nl in _CAP_STOP or _nl in known:
            continue
        if _nl not in exchange_low:
            return ""
    return raw


async def update_memories(chat_id: int, user_msg: str, ai_response: str):
    if not MEMORY_AUTO or not any(
        w not in _MEMORY_STOPWORDS
        for w in re.findall(r"\b[a-z]{4,}\b", user_msg.lower())
    ):
        return
    uname = user_names.get(chat_id, "you")
    try:
        def _work():
            mem = _extract_memory(uname, user_msg, ai_response)
            if mem:
                _append_memory(mem, auto=True)
                print(f"[memories] added: {mem}")
        await asyncio.to_thread(_work)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print("[memories] update failed:", e)


# Emoji Telegram allows as message reactions (standard set, no premium custom emoji).
ALLOWED_REACTIONS = {
    "👍", "👎", "❤", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱", "🤬", "😢", "🎉", "🤩",
    "🤮", "💩", "🙏", "👌", "🕊", "🤡", "🥱", "🥴", "😍", "🐳", "💯", "🤣", "⚡", "🍌",
    "🏆", "💔", "🤨", "😐", "🍓", "🍾", "💋", "🖕", "😈", "😴", "😭", "🤓", "👻", "👀",
    "🎃", "🙈", "😇", "😨", "🤝", "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪", "🗿",
    "🆒", "💘", "🙉", "🦄", "😘", "💊", "🙊", "😎", "👾", "🤷", "😡",
}
REACTION_HINTS = "👍 ❤ 🔥 😁 🤔 😢 😍 🙏 👀 😭 🤣 💯 🥰 😱 😈 😘 🤨 🙊 🫡 😎"


def norm_emoji(e: str) -> str:
    return "".join(ch for ch in e if ch != "\ufe0f").strip()  # drop U+FE0F

# --- Setting / live environment (where she lives now, weather, local time) ---
WEATHER_LOCATION = os.getenv("WEATHER_LOCATION", "Seattle")
WEATHER_LAT = os.getenv("WEATHER_LAT", "47.6062")
WEATHER_LON = os.getenv("WEATHER_LON", "-122.3321")
TIMEZONE = os.getenv("TIMEZONE", "America/Los_Angeles")

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(TIMEZONE)
except Exception as e:
    print(f"[time] Could not load timezone '{TIMEZONE}' ({e}); using device local time.")
    TZ = None

# Built-in default setting. Override by dropping a setting.txt next to bot.py.
DEFAULT_SETTING = (
    "Priya grew up in Houston, Texas in a big Tamil-American family and is Houston underneath "
    "it all — her drawl, her references (her grandfather's garden, Tex-Mex done right, "
    "Thatha's stories), her instincts. She has since moved to Portland, Oregon to tattoo at a "
    "respected shop. She's a transplant: she measures everything against Houston, gripes about "
    "Portland's rain and its bike-lane politics, misses real queso, but Portland is her life "
    "now. Use real Portland geography for her present-day surroundings — the Willamette River, "
    "Hawthorne, Alberta Arts, food carts, the constant drizzle, the green — while keeping her "
    "Houston roots, accent, and frame of reference fully intact."
)
SETTING_FILE = BASE_DIR / "setting.txt"
if SETTING_FILE.exists():
    SETTING = SETTING_FILE.read_text(encoding="utf-8").strip()
elif not IS_NAMED_INSTANCE:
    SETTING = DEFAULT_SETTING   # the home instance keeps the default overlay
else:
    SETTING = ""                # a named instance starts clean; use its card / setting.txt

# WMO weather codes -> short human descriptions (Open-Meteo).
WEATHER_CODES = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}

_weather_cache = {"text": None, "ts": 0.0}
WEATHER_TTL = 3600  # refresh live weather at most every hour

# --- WSDOT Traffic (Western Washington) ---
WSDOT_API_KEY       = os.getenv("WSDOT_API_KEY", "")
TRAFFIC_ENABLED     = bool(WSDOT_API_KEY)
TRAFFIC_RADIUS_MILES = float(os.getenv("TRAFFIC_RADIUS_MILES", "10"))
TRAFFIC_POLL_MINUTES = int(os.getenv("TRAFFIC_POLL_MINUTES", "10"))
_WSDOT_ALERTS_URL   = "https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/HighwayAlertsREST.svc/GetAlertsAsJson"
_WSDOT_TIMES_URL    = "https://www.wsdot.wa.gov/Traffic/api/TravelTimes/TravelTimesREST.svc/GetTravelTimesAsJson"

# --- Payment reminders (off by default on named character instances) ---
PAYMENTS_ENABLED = os.getenv(
    "PAYMENTS_ENABLED", "0" if IS_NAMED_INSTANCE else "1"
).lower() not in ("0", "false", "no", "off")
PAYMENTS_FILE = BASE_DIR / "payments.json"
REMINDER_TIME = os.getenv("REMINDER_TIME", "09:00")        # HH:MM in local TZ
REMINDER_WEEKDAY = int(os.getenv("REMINDER_WEEKDAY", "3"))  # Mon=0 ... Thu=3 ... Sun=6
REMINDER_WINDOW_DAYS = int(os.getenv("REMINDER_WINDOW_DAYS", "6"))  # Thu + 6 = next Wed
try:
    _REM_H, _REM_M = (int(x) for x in REMINDER_TIME.split(":"))
except Exception:
    _REM_H, _REM_M = 9, 0

# --- Quiet hours (heartbeat won't ping overnight) ---
QUIET_START = os.getenv("QUIET_START", "23:00")
QUIET_END = os.getenv("QUIET_END", "08:00")
try:
    _QS_H, _QS_M = (int(x) for x in QUIET_START.split(":"))
    _QE_H, _QE_M = (int(x) for x in QUIET_END.split(":"))
except Exception:
    _QS_H, _QS_M, _QE_H, _QE_M = 23, 0, 8, 0

# --- Weekly backup ---
BACKUP_WEEKDAY = int(os.getenv("BACKUP_WEEKDAY", "6"))  # Sun=6
BACKUP_TIME = os.getenv("BACKUP_TIME", "09:05")
try:
    _BK_H, _BK_M = (int(x) for x in BACKUP_TIME.split(":"))
except Exception:
    _BK_H, _BK_M = 9, 5

# --- One-off reminders ---
REMINDERS_FILE = BASE_DIR / "reminders.json"

# --- Day context file (day.txt) — editable throughout the day for continuity ---
DAY_FILE = BASE_DIR / "day.txt"
DAY_TTL = 300  # re-read at most every 5 minutes
_day_cache: dict = {"text": None, "ts": 0.0}


def _read_day_context() -> str:
    """Return the contents of day.txt, cached for DAY_TTL seconds."""
    now = time.time()
    if _day_cache["text"] is not None and now - _day_cache["ts"] < DAY_TTL:
        return _day_cache["text"]
    try:
        text = DAY_FILE.read_text(encoding="utf-8").strip() if DAY_FILE.exists() else ""
    except Exception:
        text = ""
    _day_cache["text"] = text
    _day_cache["ts"] = now
    return text


# --- Nightly maintenance schedule (memory promotion, mood reset, milestone detection) ---
REFLECTION_TIME = os.getenv("REFLECTION_TIME", "03:00")
try:
    _RF_H, _RF_M = (int(x) for x in REFLECTION_TIME.split(":"))
except Exception:
    _RF_H, _RF_M = 3, 0
MILESTONES_MAX = int(os.getenv("MILESTONES_MAX", "30"))  # cap on relationship milestones stored


# --- Character card loading (SillyTavern v2) ---
def fill(text: str, char: str, user: str) -> str:
    if not text:
        return ""
    return text.replace("{{char}}", char).replace("{{user}}", user)


def load_character(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = raw.get("data", raw)  # v2 cards nest fields under "data"
    name = data.get("name") or "Assistant"

    # Main system prompt: card system_prompt + the descriptive fields.
    parts = []
    if data.get("system_prompt"):
        parts.append(data["system_prompt"].strip())
    parts.append(
        f"You are {name}. Always stay fully in character as {name}. Never break "
        f"character, never describe yourself as an AI or a language model. You may use "
        f"*asterisks* for actions and narration, in the third person, as in the examples."
    )
    if data.get("description"):
        parts.append("# Character description\n" + data["description"].strip())
    if data.get("personality"):
        parts.append("# Personality\n" + data["personality"].strip())
    if data.get("scenario"):
        parts.append("# Scenario\n" + data["scenario"].strip())
    if data.get("mes_example"):
        parts.append("# Example dialogue\n" + data["mes_example"].strip())
    system_prompt = "\n\n".join(p for p in parts if p)

    # Post-history instructions + depth prompt -> strong final anchor.
    post_parts = []
    if data.get("post_history_instructions"):
        post_parts.append(data["post_history_instructions"].strip())
    depth = data.get("extensions", {}).get("depth_prompt", {})
    if depth.get("prompt"):
        post_parts.append(depth["prompt"].strip())
    post_history = "\n\n".join(post_parts)

    # Lorebook (character_book) entries -> keyword-triggered world info.
    lore = []
    book = data.get("character_book") or {}
    for entry in book.get("entries", []):
        if not entry.get("enabled", True):
            continue
        keys = [k.lower() for k in entry.get("keys", [])]
        lore.append({
            "keys": keys,
            "content": (entry.get("content") or "").strip(),
            "constant": bool(entry.get("constant", False)),
            "patterns": [re.compile(r"\b" + re.escape(k) + r"\b") for k in keys],
        })

    first_mes = data.get("first_mes", "")
    return name, system_prompt, post_history, lore, first_mes


card_path = BASE_DIR / CARD_NAME
if not card_path.exists():
    available = [p.name for p in BASE_DIR.glob("*.json")]
    raise SystemExit(
        f"Character card '{CARD_NAME}' not found in {BASE_DIR}.\n"
        f"Available .json files: {available}\n"
        f"Rename your card to 'priya.json' or set CHARACTER_CARD=<filename> in .env."
    )

NAME, SYSTEM_PROMPT_RAW, POST_HISTORY_RAW, LORE, FIRST_MES_RAW = load_character(card_path)

# Raw card data kept in memory so /setcard can update individual fields without a restart.
_card_json: dict = json.loads(card_path.read_text(encoding="utf-8"))
_card_data: dict = _card_json.get("data", _card_json)  # reference into the live dict

_CARD_FIELDS = {
    "name":         "name",
    "description":  "description",
    "personality":  "personality",
    "scenario":     "scenario",
    "first_mes":    "first_mes",
    "mes_example":  "mes_example",
    "system_prompt":         "system_prompt",
    "post_history":          "post_history_instructions",
    "creator_notes":         "creator_notes",
}


def _save_and_reload_card():
    """Write _card_data back to disk and recompile card globals in place."""
    global NAME, SYSTEM_PROMPT_RAW, POST_HISTORY_RAW, LORE, FIRST_MES_RAW
    if "data" not in _card_json:
        out = {"spec": "chara_card_v2", "spec_version": "2.0", "data": _card_data}
    else:
        out = _card_json
    card_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    NAME, SYSTEM_PROMPT_RAW, POST_HISTORY_RAW, LORE, FIRST_MES_RAW = load_character(card_path)
    _filled_system.clear()
    _memory_word_cache.clear()


# --- State (in-memory, mirrored to disk so the character remembers across restarts) ---
conversation_history = {}   # chat_id -> recent messages (verbatim window)
last_seen = {}      # chat_id -> unix timestamp of last user activity
_pdf_in_flight: set = set()  # (chat_id, file_unique_id) — prevents duplicate processing
user_names = {}     # chat_id -> the human's first name (for {{user}})
summaries = {}      # chat_id -> long-term rolling summary (durable, identity-level)
facts = {}          # chat_id -> list of durable, identity-level facts about the user
recent_summaries = {}  # chat_id -> short-term summary covering roughly the last week
recent_facts = {}      # chat_id -> list of recent/situational facts (last ~week)
last_promotion = {}    # chat_id -> unix timestamp recent memory was last folded into long-term
moods = {}          # chat_id -> {"score": float, "ts": epoch} drifting emotional state
milestones = {}     # chat_id -> [{"text": str, "ts": float}] relationship firsts
pinned = {}         # chat_id -> [str] facts that never get summarized away
boundaries = {}     # chat_id -> [str] hard behavioral constraints from the user
current_vibe = {}   # chat_id -> {"name": str, "expires_at": float|None}
vent_mode = {}      # chat_id -> bool
user_energy = {}    # chat_id -> {"level": "low"|"medium"|"high", "ts": float}
unsent_drafts = {}  # chat_id -> [{"reason": str, "ts": float}]
nudge_budget = {}   # chat_id -> {"limit": int, "sent_today": int, "reset_date": str}
quiet_until = {}    # chat_id -> float (unix ts); suppress proactives until then
voice_reply = {}    # chat_id -> bool  (TTS replies enabled)
wardrobe = {"outfits": [], "current": None}  # loaded from wardrobe.json
summarizing = set()  # chat_ids with a summary update in flight (avoid overlap)
model_overrides = {}    # global var name (e.g. "NANOGPT_MODEL") -> model id, set via /setmodel
setting_overrides = {}  # global var name (e.g. "SEARCH_ENABLED") -> value, set via /settings
user_location: dict = {}   # chat_id -> {lat, lon, ts, live_until}  (traffic feature)
seen_incidents: dict = {}  # chat_id -> set of AlertID strings already alerted on

STATE_FILE = BASE_DIR / "state.json"


def load_state():
    if not STATE_FILE.exists():
        return
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        backup = STATE_FILE.with_suffix(".corrupted")
        try:
            STATE_FILE.rename(backup)
        except Exception:
            pass
        log.error("State file corrupted, moved to %s: %s", backup, e)
        return
    for cid, hist in data.get("conversation_history", {}).items():
        conversation_history[int(cid)] = hist
    for cid, ts in data.get("last_seen", {}).items():
        last_seen[int(cid)] = ts
    for cid, nm in data.get("user_names", {}).items():
        user_names[int(cid)] = nm
    for cid, s in data.get("summaries", {}).items():
        summaries[int(cid)] = s
    for cid, fl in data.get("facts", {}).items():
        facts[int(cid)] = fl
    for cid, s in data.get("recent_summaries", {}).items():
        recent_summaries[int(cid)] = s
    for cid, fl in data.get("recent_facts", {}).items():
        recent_facts[int(cid)] = fl
    for cid, ts in data.get("last_promotion", {}).items():
        last_promotion[int(cid)] = ts
    for cid, mv in data.get("moods", {}).items():
        moods[int(cid)] = mv
    for cid, ml in data.get("milestones", {}).items():
        milestones[int(cid)] = ml
    for cid, pl in data.get("pinned", {}).items():
        pinned[int(cid)] = pl
    for cid, bl in data.get("boundaries", {}).items():
        boundaries[int(cid)] = bl
    for cid, vb in data.get("current_vibe", {}).items():
        current_vibe[int(cid)] = vb
    for cid, vm in data.get("vent_mode", {}).items():
        vent_mode[int(cid)] = vm
    for cid, ue in data.get("user_energy", {}).items():
        user_energy[int(cid)] = ue
    for cid, ud in data.get("unsent_drafts", {}).items():
        unsent_drafts[int(cid)] = ud
    for cid, nb in data.get("nudge_budget", {}).items():
        nudge_budget[int(cid)] = nb
    for cid, qt in data.get("quiet_until", {}).items():
        quiet_until[int(cid)] = qt
    for cid, vr in data.get("voice_reply", {}).items():
        voice_reply[int(cid)] = vr
    model_overrides.update(data.get("model_overrides", {}))
    setting_overrides.update(data.get("setting_overrides", {}))
    for cid, lv in data.get("user_location", {}).items():
        user_location[int(cid)] = lv
    for cid, ids in data.get("seen_incidents", {}).items():
        seen_incidents[int(cid)] = set(ids)
    log.info("Loaded history for %d chat(s).", len(conversation_history))


def save_state():
    data = {
        "conversation_history": {str(k): v for k, v in conversation_history.items()},
        "last_seen": {str(k): v for k, v in last_seen.items()},
        "user_names": {str(k): v for k, v in user_names.items()},
        "summaries": {str(k): v for k, v in summaries.items()},
        "facts": {str(k): v for k, v in facts.items()},
        "recent_summaries": {str(k): v for k, v in recent_summaries.items()},
        "recent_facts": {str(k): v for k, v in recent_facts.items()},
        "last_promotion": {str(k): v for k, v in last_promotion.items()},
        "moods": {str(k): v for k, v in moods.items()},
        "milestones": {str(k): v for k, v in milestones.items()},
        "pinned": {str(k): v for k, v in pinned.items()},
        "boundaries": {str(k): v for k, v in boundaries.items()},
        "current_vibe": {str(k): v for k, v in current_vibe.items()},
        "vent_mode": {str(k): v for k, v in vent_mode.items()},
        "user_energy": {str(k): v for k, v in user_energy.items()},
        "unsent_drafts": {str(k): v for k, v in unsent_drafts.items()},
        "nudge_budget": {str(k): v for k, v in nudge_budget.items()},
        "quiet_until": {str(k): v for k, v in quiet_until.items()},
        "voice_reply": {str(k): v for k, v in voice_reply.items()},
        "model_overrides": model_overrides,
        "setting_overrides": setting_overrides,
        "user_location": {str(k): v for k, v in user_location.items()},
        "seen_incidents": {str(k): list(v) for k, v in seen_incidents.items()},
    }
    tmp = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(STATE_FILE)  # atomic, so a crash mid-write can't corrupt the file


# --- PID lock: prevent duplicate instances ---
_PID_FILE = BASE_DIR / "bot.pid"

def _acquire_pid_lock():
    if _PID_FILE.exists():
        try:
            existing_pid = int(_PID_FILE.read_text().strip())
            # Check if that process is still alive
            os.kill(existing_pid, 0)
            raise SystemExit(
                f"Another instance is already running (PID {existing_pid}).\n"
                f"Kill it first: kill {existing_pid}\n"
                f"Or force-remove the lock: rm {_PID_FILE}"
            )
        except ProcessLookupError:
            pass  # stale PID file — process is gone, safe to continue
        except ValueError:
            pass  # corrupt PID file — ignore it
    _PID_FILE.write_text(str(os.getpid()))

def _release_pid_lock():
    try:
        _PID_FILE.unlink()
    except FileNotFoundError:
        pass

_acquire_pid_lock()
import atexit
atexit.register(_release_pid_lock)


load_state()


WARDROBE_FILE = BASE_DIR / "wardrobe.json"


# --- Wardrobe ---
def load_wardrobe():
    if WARDROBE_FILE.exists():
        try:
            wardrobe.update(json.loads(WARDROBE_FILE.read_text(encoding="utf-8")))
        except Exception as e:
            print("[wardrobe] load failed:", e)


def save_wardrobe():
    WARDROBE_FILE.write_text(json.dumps(wardrobe, indent=2), encoding="utf-8")


load_wardrobe()


# --- Vibe mode ---
VIBE_PROMPTS = {
    "cozy":       ("Texting mode: cozy and warm. Longer messages okay. Soft language. "
                   "Low emoji. High initiative — bring things up unprompted. Slow evening energy."),
    "flirty":     ("Texting mode: playful and a little flirty. Light teasing welcome. "
                   "Warmer than usual. Keep it natural, not performative."),
    "serious":    ("Texting mode: focused and direct. Skip jokes for now. Engage with what "
                   "actually matters. Match the weight of the conversation."),
    "chaotic":    ("Texting mode: chaotic and energetic. Fast, funny, tangents welcome. "
                   "High emoji okay if it fits. Bring the noise."),
    "low-energy": ("Texting mode: low-energy. Short, gentle replies. No big questions. "
                   "Just present without demanding anything."),
    "playful":    ("Texting mode: playful. Light and bouncy. Jokes, teasing, a little unserious. "
                   "Nothing too heavy."),
    "chill":      ("Texting mode: chill. Laid-back. Unhurried. Low stakes. No interrogating."),
    "in-person":  ("Scene mode: you're physically in the same space right now, not texting. "
                   "Write with action beats, body language, and sensory detail — what you're doing, "
                   "how you react, the texture of being in the room together. "
                   "Longer, more immersive responses are welcome."),
}


def active_vibe(chat_id: int) -> str:
    """Return the active vibe name, or None if expired/not set."""
    v = current_vibe.get(chat_id)
    if not v:
        return None
    exp = v.get("expires_at")
    if exp and time.time() > exp:
        current_vibe.pop(chat_id, None)
        save_state()
        return None
    return v.get("name")


# --- Nudge budget ---
def _today_str() -> str:
    return _today().isoformat()


def _is_quiet(chat_id: int) -> bool:
    """True if the user has /quiet active for this chat."""
    ts = quiet_until.get(chat_id)
    if ts and time.time() < ts:
        return True
    if ts:
        quiet_until.pop(chat_id, None)  # expired, clean up
    return False


def _check_nudge_budget(chat_id: int) -> bool:
    """True if a proactive nudge is allowed within today's budget."""
    today = _today_str()
    nb = nudge_budget.get(chat_id, {})
    if nb.get("reset_date") != today:
        nb = {"limit": nb.get("limit", 3), "sent_today": 0, "reset_date": today}
        nudge_budget[chat_id] = nb
    limit = nb.get("limit", 3)
    return limit == 0 or nb.get("sent_today", 0) < limit  # 0 = unlimited


def _consume_nudge(chat_id: int):
    today = _today_str()
    nb = nudge_budget.setdefault(chat_id, {"limit": 3, "sent_today": 0, "reset_date": today})
    if nb.get("reset_date") != today:
        nb["sent_today"] = 0
        nb["reset_date"] = today
    nb["sent_today"] = nb.get("sent_today", 0) + 1
    save_state()


# --- Unsent drafts ---
def _save_draft(chat_id: int, reason: str):
    drafts = unsent_drafts.setdefault(chat_id, [])
    drafts.append({"reason": reason, "ts": time.time()})
    if len(drafts) > 3:
        drafts[:] = drafts[-3:]
    save_state()
    print(f"[draft] Saved unsent thought for chat {chat_id}: {reason}")


def _pop_draft(chat_id: int) -> dict:
    """Return and remove the oldest fresh draft, or None."""
    drafts = unsent_drafts.get(chat_id) or []
    cutoff = time.time() - 48 * 3600
    fresh = [d for d in drafts if d["ts"] > cutoff]
    unsent_drafts[chat_id] = fresh
    if not fresh:
        return None
    draft = fresh.pop(0)
    unsent_drafts[chat_id] = fresh
    save_state()
    return draft


# --- Payments: storage + date math ---
payments = []  # list of {"name": str, "amount": float, "day": int (day-of-month)}


def load_payments():
    global payments
    if PAYMENTS_FILE.exists():
        try:
            payments = json.loads(PAYMENTS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print("[payments] load failed:", e)
            payments = []


def save_payments():
    PAYMENTS_FILE.write_text(json.dumps(payments, indent=2), encoding="utf-8")


load_payments()


def _ord(n: int) -> str:
    n = int(n)
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _money(a: float) -> str:
    s = f"${float(a):,.2f}"
    return s[:-3] if s.endswith(".00") else s


def _today():
    return datetime.now(TZ).date() if TZ else date.today()


def next_occurrence(day: int, from_date: date) -> date:
    """Next calendar date on which a given day-of-month falls, on/after from_date."""
    y, m = from_date.year, from_date.month
    d = min(day, calendar.monthrange(y, m)[1])  # clamp (e.g. 31 -> 28/30)
    cand = date(y, m, d)
    if cand < from_date:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        d = min(day, calendar.monthrange(y, m)[1])
        cand = date(y, m, d)
    return cand


def add_months(day: int, base: date, months: int) -> date:
    """The date `months` after `base`'s month, on day-of-month `day` (clamped)."""
    idx = base.year * 12 + (base.month - 1) + months
    y, m = idx // 12, idx % 12 + 1
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def next_occurrence_p(p: dict, from_date: date):
    """Next due date for any payment, or None if it has finished its run.

    Shapes:
      monthly:  {"recur":"monthly","day":N, "until":"YYYY-MM-DD" or absent}
      interval: {"recur":"every","start":"YYYY-MM-DD","interval":N,"count":N or null}
    """
    if p.get("recur", "monthly") == "monthly":
        occ = next_occurrence(int(p["day"]), from_date)
        until = p.get("until")
        if until and occ > date.fromisoformat(until):
            return None
        return occ
    start = date.fromisoformat(p["start"])
    interval = int(p["interval"])
    count = p.get("count")
    if from_date <= start:
        k = 0
    else:
        delta = (from_date - start).days
        k = (delta + interval - 1) // interval  # ceil -> first occurrence >= from_date
    if count is not None and k > int(count) - 1:
        return None  # all payments have been made
    return start + timedelta(days=k * interval)


def payments_remaining(p: dict, from_date: date):
    """How many payments are still to come (incl. the next), or None if uncapped."""
    if p.get("recur", "monthly") == "monthly":
        until = p.get("until")
        if not until:
            return None
        until = date.fromisoformat(until)
        occ = next_occurrence(int(p["day"]), from_date)
        if occ > until:
            return 0
        return (until.year - occ.year) * 12 + (until.month - occ.month) + 1
    if p.get("count") is None:
        return None
    start = date.fromisoformat(p["start"])
    interval = int(p["interval"])
    if from_date <= start:
        k = 0
    else:
        k = ((from_date - start).days + interval - 1) // interval
    return max(0, int(p["count"]) - k)


def describe_recur(p: dict) -> str:
    if p.get("recur", "monthly") == "monthly":
        base = f"{p['day']}{_ord(p['day'])} of each month"
        if p.get("until"):
            end = date.fromisoformat(p["until"])
            base += f" (through {end.strftime('%b %Y')})"
        return base
    start = date.fromisoformat(p["start"])
    every = f"every {p['interval']} days from {start.strftime('%b ')}{start.day}, {start.year}"
    if p.get("count") is not None:
        every += f" ({p['count']} payments)"
    return every


def ordered_payments():
    """Stable ordering shared by /payments and /delpayment (by next due date)."""
    today = _today()
    return sorted(
        payments,
        key=lambda p: ((next_occurrence_p(p, today) is None), next_occurrence_p(p, today) or date.max),
    )


def week_window(from_date: date = None):
    """The Thu→Wed week (anchored to REMINDER_WEEKDAY) that contains from_date."""
    from_date = from_date or _today()
    delta = (from_date.weekday() - REMINDER_WEEKDAY) % 7  # days since this week's Thursday
    start = from_date - timedelta(days=delta)
    end = start + timedelta(days=REMINDER_WINDOW_DAYS)    # Thursday + 6 = next Wednesday
    return start, end


def due_between(start: date, end: date):
    out = []
    for p in payments:
        occ = next_occurrence_p(p, start)
        if occ is not None and start <= occ <= end:
            out.append((occ, p))
    out.sort(key=lambda x: x[0])
    return out


def format_due(due, uname: str, start: date, end: date) -> str:
    span = f"{start.strftime('%b ')}{start.day}–{end.strftime('%b ')}{end.day}"
    if not due:
        return f"No payments due this week ({span}), {uname}. 🎉"
    lines, total = [], 0.0
    for occ, p in due:
        total += float(p["amount"])
        when = occ.strftime("%a %b ") + str(occ.day)
        tail = ""
        left = payments_remaining(p, occ)
        if left is not None:
            tail = f"  (last one!)" if left <= 1 else f"  ({left} left)"
        lines.append(f"• {p['name']} — {_money(p['amount'])} — {when}{tail}")
    return (
        f"💸 Heads up, {uname} — payments due this week ({span}):\n\n"
        + "\n".join(lines)
        + f"\n\nTotal: {_money(total)}\n\nDon't let 'em hit you late."
    )


def in_quiet_hours(now=None) -> bool:
    now = now or (datetime.now(TZ) if TZ else datetime.now())
    cur = now.hour * 60 + now.minute
    s = _QS_H * 60 + _QS_M
    e = _QE_H * 60 + _QE_M
    if s == e:
        return False
    return s <= cur < e if s < e else (cur >= s or cur < e)  # handle wrap past midnight


# --- One-off reminders: storage + parsing ---
reminders = []  # {"id":int, "chat_id":int, "due":iso, "text":str}


def load_reminders():
    global reminders
    if REMINDERS_FILE.exists():
        try:
            reminders = json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print("[reminders] load failed:", e)
            reminders = []


def save_reminders():
    REMINDERS_FILE.write_text(json.dumps(reminders, indent=2), encoding="utf-8")


load_reminders()


def _new_reminder_id() -> int:
    return (max((r["id"] for r in reminders), default=0)) + 1


# --- Recurring tasks ("cron jobs") ---
CRON_FILE = BASE_DIR / "cron_jobs.json"
cron_jobs = []  # {"id":int, "chat_id":int, "schedule":{...}, "instruction":str}


def load_cron_jobs():
    global cron_jobs
    if CRON_FILE.exists():
        try:
            cron_jobs = json.loads(CRON_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print("[cron] load failed:", e)
            cron_jobs = []


def save_cron_jobs():
    CRON_FILE.write_text(json.dumps(cron_jobs, indent=2), encoding="utf-8")


load_cron_jobs()


def _new_cron_id() -> int:
    return (max((j["id"] for j in cron_jobs), default=0)) + 1


def parse_cron_schedule(spec: str):
    """Parse 'daily HH:MM' or 'every Nh'/'every Nm' into a schedule dict, or None."""
    spec = spec.strip().lower()
    m = re.fullmatch(r"daily\s+(\d{1,2}):(\d{2})", spec)
    if m:
        return {"type": "daily", "hour": int(m.group(1)), "minute": int(m.group(2))}
    m = re.fullmatch(r"every\s+(\d+)\s*([mh])", spec)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        seconds = n * 60 if unit == "m" else n * 3600
        return {"type": "interval", "seconds": seconds}
    return None


def describe_cron_schedule(sch: dict) -> str:
    if sch["type"] == "daily":
        return f"daily {sch['hour']:02d}:{sch['minute']:02d}"
    secs = sch["seconds"]
    return f"every {secs // 3600}h" if secs % 3600 == 0 else f"every {secs // 60}m"


def parse_when(tokens):
    """Parse a leading time spec, return (due_datetime, message) or (None, None).

    Accepts: 30m / 2h / 3d (relative); HH:MM (today/next); tomorrow [HH:MM];
             today [HH:MM]; YYYY-MM-DD [HH:MM].
    """
    if not tokens:
        return None, None
    now = datetime.now(TZ) if TZ else datetime.now()
    t0 = tokens[0].lower()
    rest = tokens[1:]

    m = re.fullmatch(r"(\d+)\s*([mhd])", t0)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
        return now + delta, " ".join(rest).strip()

    def grab_time(rest, default=(9, 0)):
        if rest and re.fullmatch(r"\d{1,2}:\d{2}", rest[0]):
            hh, mm = map(int, rest[0].split(":"))
            return hh, mm, rest[1:]
        return default[0], default[1], rest

    if t0 in ("tomorrow", "today"):
        base = now + timedelta(days=1) if t0 == "tomorrow" else now
        hh, mm, rest = grab_time(rest)
        due = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if t0 == "today" and due <= now:
            due += timedelta(days=1)
        return due, " ".join(rest).strip()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t0):
        d = date.fromisoformat(t0)
        hh, mm, rest = grab_time(rest)
        due = datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ) if TZ else datetime(d.year, d.month, d.day, hh, mm)
        return due, " ".join(rest).strip()

    if re.fullmatch(r"\d{1,2}:\d{2}", t0):
        hh, mm = map(int, t0.split(":"))
        due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return due, " ".join(rest).strip()

    return None, None


def fmt_due_dt(dt: datetime) -> str:
    hour12 = dt.strftime("%I").lstrip("0") or "12"
    return dt.strftime("%a %b ") + str(dt.day) + " at " + hour12 + dt.strftime(":%M %p")


def get_owner():
    if OWNER_CHAT_ID_ENV:
        try:
            return int(OWNER_CHAT_ID_ENV)
        except ValueError:
            return None
    if OWNER_FILE.exists():
        try:
            return int(OWNER_FILE.read_text().strip())
        except ValueError:
            return None
    return None


def set_owner(chat_id: int):
    if not OWNER_CHAT_ID_ENV:
        OWNER_FILE.write_text(str(chat_id))


def triggered_lore(low: str):
    """low must already be lowercased."""
    out = []
    for entry in LORE:
        hit = entry["constant"] or any(p.search(low) for p in entry["patterns"])
        if hit:
            out.append(entry["content"])
    return out


_MEMORY_STOPWORDS = frozenset({
    "the", "and", "that", "this", "with", "from", "have", "will", "been",
    "they", "them", "their", "made", "user", "told", "said", "just", "more",
    "about", "into", "than", "also", "some", "very", "when", "what", "where",
    "your", "always", "never", "every", "would", "could", "should", "still",
    "even", "both", "only", "other", "back", "then", "well", "each",
})


def triggered_reading(low: str) -> list[str]:
    """low already lowercased. Surface 'things she read' whose keywords appear in recent text."""
    entries = _read_reading()
    if not entries:
        return []
    out = []
    for line in entries:
        body = re.sub(r"^\[[^\]]*\]\s*", "", line)
        body = re.sub(r"https?://\S+", "", body)
        words = {w for w in re.findall(r"\b[a-z]{4,}\b", body.lower())
                 if w not in _MEMORY_STOPWORDS}
        if any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in words):
            out.append(line)
    return out[-3:]


def triggered_memories(low: str) -> list[str]:
    """low must already be lowercased."""
    entries = _read_memories()
    if not entries:
        return []
    char_name = NAME.lower() if NAME else ""
    stopwords = _MEMORY_STOPWORDS | ({char_name} if char_name else set())
    scan_words = set(re.findall(r"\b[a-z]{4,}\b", low))
    scored = []
    for line in entries:
        words = _memory_word_cache.get(line)
        if words is None:
            words = frozenset(w for w in re.findall(r"\b[a-z]{4,}\b", line.lower())
                              if w not in stopwords)
            _memory_word_cache[line] = words
        hits = len(words & scan_words)
        if hits > 0:
            scored.append((hits, line))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    budget = MEMORY_TOKEN_BUDGET
    for _, line in scored:
        cost = _est_tokens(line)
        if cost > budget:
            break
        out.append(line)
        budget -= cost
    return out


def _fetch_weather() -> str:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph"
    )
    r = _session.get(url, timeout=10)
    r.raise_for_status()
    c = r.json()["current"]
    desc = WEATHER_CODES.get(c.get("weather_code"), "")
    parts = [f"{round(c['temperature_2m'])}°F"]
    if abs(c["apparent_temperature"] - c["temperature_2m"]) >= 4:
        parts.append(f"feels like {round(c['apparent_temperature'])}°F")
    if desc:
        parts.append(desc)
    parts.append(f"wind {round(c['wind_speed_10m'])}mph")
    return ", ".join(parts)


async def ensure_weather():
    """Refresh the cached weather string at most every WEATHER_TTL seconds."""
    if _weather_cache["text"] and time.time() - _weather_cache["ts"] < WEATHER_TTL:
        return
    try:
        _weather_cache["text"] = await asyncio.to_thread(_fetch_weather)
        _weather_cache["ts"] = time.time()
    except Exception as e:
        print("[weather] fetch failed:", e)


def _season_and_calendar() -> str:
    """Return a short string noting the current season and any nearby holidays."""
    now = datetime.now(TZ) if TZ else datetime.now()
    m, d = now.month, now.day
    if m in (12, 1, 2):
        season = "winter"
    elif m in (3, 4, 5):
        season = "spring"
    elif m in (6, 7, 8):
        season = "summer"
    else:
        season = "fall"
    # Nearby holidays / cultural moments worth knowing about
    markers = []
    if m == 1 and d <= 8:
        markers.append("just after New Year's")
    elif m == 2 and 10 <= d <= 18:
        markers.append("around Valentine's Day")
    elif m == 3 and d <= 20:
        markers.append("heading into spring")
    elif m == 5 and 20 <= d <= 31:
        markers.append("around Memorial Day weekend")
    elif m == 6 and d <= 21:
        markers.append("start of summer")
    elif m == 7 and 1 <= d <= 7:
        markers.append("around the Fourth of July")
    elif m == 9 and d <= 7:
        markers.append("Labor Day weekend")
    elif m == 10 and d >= 25:
        markers.append("right around Halloween")
    elif m == 11 and 20 <= d <= 30:
        markers.append("Thanksgiving week")
    elif m == 12 and 18 <= d <= 26:
        markers.append("holiday season")
    elif m == 12 and d >= 27:
        markers.append("between Christmas and New Year's")
    out = season
    if markers:
        out += f", {markers[0]}"
    return out


_DEFAULT_TIME_PERSONALITY = (
    "early morning (before 7am): groggy, just waking up or hasn't slept\n"
    "morning (7am-noon): easing into the day, coffee energy\n"
    "afternoon (noon-5pm): in the middle of things, steady energy\n"
    "evening (5pm-9pm): winding down, more relaxed and reflective\n"
    "late night (9pm-1am): tired, loose, guard drops\n"
    "deep night (1am-5am): either can't sleep or chose not to — raw, unfiltered"
)

def _read_time_personality() -> str:
    text = _read_life_file(TIME_PERSONALITY_FILE, _time_personality_cache)
    return text.strip() if text.strip() else _DEFAULT_TIME_PERSONALITY

def _current_period(h: int) -> str:
    if h < 5:
        return "deep night"
    if h < 7:
        return "early morning"
    if h < 12:
        return "morning"
    if h < 17:
        return "afternoon"
    if h < 21:
        return "evening"
    return "late night"


def _time_personality_line() -> str:
    """Only the time_personality.txt line matching the current hour (description part)."""
    tp = _read_time_personality()
    now = datetime.now(TZ) if TZ else datetime.now()
    period = _current_period(now.hour)
    for tpline in tp.splitlines():
        if tpline.strip().lower().startswith(period):
            return tpline.split(":", 1)[-1].strip()
    return ""


def environment_note() -> str:
    """Live context: the real current date, local time, weather, and season."""
    now = datetime.now(TZ) if TZ else datetime.now()
    hour12 = now.strftime("%I").lstrip("0") or "12"
    stamp = (now.strftime("%A, %B ") + str(now.day) + now.strftime(", %Y")
             + ", " + hour12 + now.strftime(":%M %p %Z")).rstrip()
    line = (f"Current real-world date and time where {NAME} lives "
            f"({WEATHER_LOCATION}): {stamp}. Treat this as the actual now.")
    if _weather_cache["text"]:
        line += f" Weather: {_weather_cache['text']}."
    line += f" Season: {_season_and_calendar()}."
    period = _current_period(now.hour)
    line += (f"\n\nLet the time of day shape {NAME}'s energy and behavior naturally — "
             f"it's {period}. Don't announce the time; just feel it.")
    tpline = _time_personality_line()
    if tpline:
        line += f"\n\nYour energy right now ({period}): {tpline}"
    return "[" + line + "]"


def mood_now(chat_id: int) -> float:
    """Current mood, decaying toward neutral over time (half-life ~24h)."""
    m = moods.get(chat_id)
    if not m:
        return 0.0
    hours = (time.time() - m.get("ts", 0)) / 3600
    return m.get("score", 0.0) * (0.5 ** (hours / 24))


def mood_label(chat_id: int):
    """The LLM-appraised mood label, if it's still fresh; else None."""
    m = moods.get(chat_id) or {}
    label = m.get("label")
    if label and (time.time() - m.get("ts", 0)) < MOOD_LABEL_FRESH_HOURS * 3600:
        return label
    return None


def _mood_vibe(chat_id: int) -> str:
    """Combine mood label and active vibe into a short descriptive string for prompts."""
    label = mood_label(chat_id)
    vibe = active_vibe(chat_id)
    if label and vibe:
        return f"{label} [vibe: {vibe}]"
    return label or vibe or "neutral"


def nudge_mood(chat_id: int, gap_hours):
    """Apply a mood penalty when re-contacting after a long silence.
    Positive shifts come from the LLM appraisal, not unconditionally from contact."""
    m = moods.setdefault(chat_id, {})
    m["_gap_hours"] = gap_hours or 0  # stash for the appraisal to include as context
    if not gap_hours or gap_hours <= 12:
        return  # normal cadence — no penalty; appraisal handles the rest
    penalty = min(1.8, (gap_hours - 12) / 12)
    cur = mood_now(chat_id)
    m["score"] = round(max(-3.0, cur - penalty), 3)


def _appraise_mood(chat_id: int, convo_tail: str):
    """Cheap background pass: how does she feel right now, given what just happened?"""
    cur = moods.get(chat_id) or {}
    gap_hours = cur.pop("_gap_hours", 0)  # consume the stashed gap before saving
    gap_note = ""
    if gap_hours > 4:
        gap_note = f" Note: it's been {gap_hours:.0f}h since they last talked — factor the time gap into her state."
    sys = (
        f"You track {NAME}'s emotional state across a conversation. Given her current mood and "
        f"the latest exchange, output ONLY a JSON object:\n"
        f'{{"mood": "<short, specific, in-character description of how she feels and why — e.g. '
        f"'pissed off, some guy doored her on her route' or 'intrigued by the article about deep-sea "
        f"mining' or 'cozy and content, slow morning'>\", \"valence\": <integer -3 to 3>}}\n"
        f"Moods persist: if nothing notable happened, stay close to the current mood rather than "
        f"resetting to neutral. React to events in her life she mentions, things she reads, and the "
        f"emotional tone of the exchange. No prose, no code fences."
    )
    user = (f"Current mood: {cur.get('label') or 'neutral'} (valence {round(cur.get('score', 0), 1)}).{gap_note}\n\n"
            f"Latest exchange:\n{convo_tail}")
    raw = call_nanogpt(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        model=MOOD_MODEL,
    )
    data = _extract_json(raw)
    label = (data.get("mood") or "").strip()
    try:
        valence = max(-3.0, min(3.0, float(data.get("valence"))))
    except (TypeError, ValueError):
        valence = cur.get("score", 0.0)
    if label:
        moods[chat_id] = {"score": round(valence, 3), "label": label[:160], "ts": time.time()}
        save_state()
        print(f"[mood] {label} ({valence:+.0f})")


async def update_mood(chat_id: int):
    if not MOOD_AUTO:
        return
    m = moods.get(chat_id) or {}
    if time.time() - m.get("ts", 0) < 60:
        return  # already appraised this minute — skip
    hist = conversation_history.get(chat_id, [])[-4:]
    if not hist:
        return
    uname = user_names.get(chat_id, "user")
    tail = "\n".join(f"{(NAME if m['role'] == 'assistant' else uname)}: {m['content']}" for m in hist)
    try:
        await asyncio.to_thread(_appraise_mood, chat_id, tail)
    except Exception as e:
        print("[mood] appraisal failed:", e)


def _mood_behavior(s: float) -> str:
    """Concrete behavioral guidance so reply length/energy/engagement actually shift with mood."""
    if s >= 1.2:
        return ("She's more talkative than usual — longer messages, more willing to go on "
                "tangents, share things unprompted, and bring up her own stuff.")
    if s >= 0.4:
        return "She's engaged and responsive, happy to elaborate when something interests her."
    if s > -0.4:
        return "Her usual mix — sometimes brief, sometimes chatty, depending on the topic."
    if s > -1.2:
        return ("She's keeping things shorter and a bit more closed off — fewer follow-up "
                "questions, less volunteered detail, replies that trail off. She'll sidestep or "
                "give a vague non-answer on heavier topics rather than dig in right now.")
    return ("She's giving short, flat responses — often just a line or two, not much energy "
            "to elaborate or carry the conversation right now. She'll actively deflect or change "
            "the subject if something gets too heavy or personal — not shutting down coldly, "
            "just not going there.")


def mood_note(chat_id: int) -> str:
    label = mood_label(chat_id)
    s = mood_now(chat_id)
    behavior = _mood_behavior(s)
    if label:
        # Label gives the specific WHY; behavior note gives the HOW. Together they're complete.
        return (
            f"# Mood\n{NAME} is currently: {label}. {behavior} "
            f"Let this specific feeling shape her tone — don't announce it or explain the cause."
        )
    if s >= 1.2:
        desc = "settled and warm right now — a little more open than usual, the guard down a notch"
    elif s >= 0.4:
        desc = "in a decent place, comfortable and present"
    elif s > -0.4:
        desc = "her usual guarded-but-here self"
    elif s > -1.2:
        desc = "a bit on edge and quieter"
    else:
        desc = "withdrawn and flat, not really feeling it"
    return (f"# Mood\nRight now {NAME} is {desc}. {behavior} Let it color her tone and reply "
            f"length naturally — never announce it outright.")


# --- Relationship milestone detection (nightly) ---
def _today_messages(chat_id: int) -> list:
    """Verbatim messages from conversation_history with a timestamp in the local 'today'."""
    now = datetime.now(TZ) if TZ else datetime.now()
    start = datetime.combine(now.date(), dtime(0, 0), tzinfo=TZ) if TZ else datetime.combine(now.date(), dtime(0, 0))
    cutoff = start.timestamp()
    return [m for m in conversation_history.get(chat_id, []) if m.get("ts", 0) >= cutoff]


async def update_milestones(chat_id: int):
    """Nightly: detect relationship 'firsts' from today's conversation and record them."""
    uname = user_names.get(chat_id, "you")
    todays = _today_messages(chat_id)
    if not todays:
        return
    convo = "\n".join(
        f"{(NAME if m['role'] == 'assistant' else uname)}: {m['content']}" for m in todays
    )
    existing = milestones.get(chat_id) or []
    ms_lines = (", ".join(m["text"] for m in existing[-10:]) if existing else "(none yet)")
    sys = (
        f"Look at today's conversation between {NAME} and {uname} for relationship milestones — "
        f"things that happened for the FIRST TIME today that aren't already in the existing list: "
        f"first time he opened up about something painful, first real disagreement they worked "
        f"through, first time she admitted something she doesn't usually say, first time he asked "
        f"for her opinion on something big. Be selective — only genuine firsts that will matter "
        f"later. Keep each one short (one brief phrase). Return an empty list if today had nothing "
        f"new.\n\n"
        f'Respond with ONLY a JSON object: {{"milestones": ["first time he ..."]}}. '
        f"No prose, no code fences."
    )
    user = f"EXISTING MILESTONES: {ms_lines}\n\nTODAY'S CONVERSATION:\n{convo}"
    raw = await asyncio.to_thread(
        call_nanogpt, [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        SUMMARY_MODEL,
    )
    new_ms = _extract_json(raw).get("milestones") or []
    if not isinstance(new_ms, list):
        return
    ms_list = milestones.setdefault(chat_id, [])
    existing_texts = {m["text"].lower() for m in ms_list}
    added = 0
    for text in new_ms:
        if isinstance(text, str) and text.strip() and text.strip().lower() not in existing_texts:
            ms_list.append({"text": text.strip()[:150], "ts": time.time()})
            existing_texts.add(text.strip().lower())
            added += 1
    if len(ms_list) > MILESTONES_MAX:
        ms_list[:] = ms_list[-MILESTONES_MAX:]
    if added:
        save_state()
        print(f"[milestones] recorded {added} new for chat {chat_id}.")


def _extract_reading(topic: str, article: str) -> str:
    sys_prompt = (
        f"{NAME} just read this one article about {topic}. Write ONE short line (under 30 words) "
        f"in her exact voice -- her REACTION to THIS specific article, NOT a summary. Do not define "
        f"or explain the topic; respond the way she actually would: an opinion, an eye-roll, "
        f"something it reminded her of, an annoyance, who she'd argue with about it. No quotes, "
        f"no 'I read' framing. If the article is junk or irrelevant, reply exactly: none"
    )
    try:
        raw = call_nanogpt(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": f"Topic: {topic}\n\nThe article she read:\n{article[:1200]}"}],
            model=READING_MODEL,
        ).strip()
        if raw and raw.lower() != "none" and not raw.lower().startswith("none"):
            return raw
    except Exception as e:
        print("[reading] extraction failed:", e)
    return ""


def _append_reading(line: str, url: str = ""):
    line = line.strip().strip('"').strip("'").strip()
    if not line:
        return
    existing = []
    if READING_FILE.exists():
        existing = [l for l in READING_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    stamp = (datetime.now(TZ) if TZ else datetime.now()).strftime("%b %d")
    entry = f"[{stamp}] {line}"
    if url:
        entry += f" -- {url}"
    existing.append(entry)
    if len(existing) > READING_MAX:
        existing = existing[-READING_MAX:]
    READING_FILE.write_text("\n".join(existing) + "\n", encoding="utf-8")
    _reading_cache["text"] = None


async def update_reading():
    """Pick one interest, search it, and store an in-character take on what she read."""
    interests = _read_interests()
    if not interests:
        return
    topic = random.choice(interests)
    try:
        results = await asyncio.to_thread(web_search, topic)
        if not results or results.startswith("(search") or results.startswith("(no results"):
            return
        top = results.splitlines()[0].lstrip("- ").strip()
        _m = re.search(r"https?://[^\s)]+", top)
        url = _m.group(0) if _m else ""
        line = await asyncio.to_thread(_extract_reading, topic, top)
        if line:
            _append_reading(line, url)
            print(f"[reading] added ({topic}): {line}")
    except Exception as e:
        print("[reading] update failed:", e)


def milestone_note(chat_id: int) -> str:
    """Relationship history (shared milestones). Self-image/reflection was removed."""
    ms_list = milestones.get(chat_id) or []
    if not ms_list:
        return ""
    recent_ms = "; ".join(m["text"] for m in ms_list[-5:])
    return (f"# Relationship milestones\nShared history so far: {recent_ms}. She knows these — "
            f"part of their history, doesn't need to announce them.")


def memory_block(chat_id: int, uname: str) -> str:
    """Long-term (durable) + recent (last ~week) memory injected every request."""
    blocks = []

    parts = []
    summ = (summaries.get(chat_id) or "").strip()
    if summ:
        parts.append(f"How you remember things with {uname} so far:\n{summ}")
    fts = facts.get(chat_id) or []
    if fts:
        parts.append(f"Things you know about {uname}:\n" + "\n".join("- " + f for f in fts))
    if parts:
        blocks.append("# What you remember\n\n" + "\n\n".join(parts))

    rparts = []
    rsumm = (recent_summaries.get(chat_id) or "").strip()
    if rsumm:
        rparts.append(rsumm)
    rfts = recent_facts.get(chat_id) or []
    if rfts:
        rparts.append("Recent specifics:\n" + "\n".join("- " + f for f in rfts))
    if rparts:
        blocks.append("# What's been going on lately\n\n" + "\n\n".join(rparts))

    return "\n\n".join(blocks)


def assemble_messages(chat_id: int, latest_user_content: str, image_data_url: str = None, inner_voice: str = None):
    """Build the OpenAI-style message list the way SillyTavern layers a card."""
    uname = user_names.get(chat_id, "you")
    history = conversation_history.get(chat_id, [])

    cached_fill = _filled_system.get(uname)
    if cached_fill and cached_fill[0] == SYSTEM_PROMPT_RAW and cached_fill[1] == NAME:
        system_content = cached_fill[2]
    else:
        system_content = fill(SYSTEM_PROMPT_RAW, NAME, uname)
        _filled_system[uname] = (SYSTEM_PROMPT_RAW, NAME, system_content)
    messages = [{"role": "system", "content": system_content}]

    if SETTING:
        messages.append({
            "role": "system",
            "content": "# Current setting\n" + fill(SETTING, NAME, uname),
        })

    # Stable character background: people in her life and ongoing projects.
    people = _read_people()
    if people:
        messages.append({"role": "system", "content": f"# People in {NAME}'s life\n{people}"})

    # Stable "what she's up to" — life arc + ongoing projects merged into one block.
    life_arc = _read_life_arc()
    projects = _read_projects()
    if life_arc or projects:
        parts = [p for p in (life_arc, projects) if p]
        messages.append({"role": "system", "content": (
            f"# {NAME}'s life right now\n" + "\n\n".join(parts)
            + "\n\nDraw on this naturally — it's the texture of her life, not a list to recite."
        )})

    if ATLAS:
        _now_ts = time.time()
        if _atlas_cache["sample"] is None or _now_ts - _atlas_cache["ts"] > _ATLAS_TTL:
            _atlas_cache["sample"] = random.sample(ATLAS, min(ATLAS_SAMPLE, len(ATLAS)))
            _atlas_cache["ts"] = _now_ts
        picks = _atlas_cache["sample"]
        messages.append({
            "role": "system",
            "content": (f"# Local places\nReal spots {NAME} knows and might naturally reference "
                        f"if it fits — don't force them, and don't invent fake businesses when "
                        f"a real area works: " + ", ".join(picks) + "."),
        })

    cap_lines = [
        f"# Capabilities\nThings you can do with tags — use sparingly, never announce them, "
        f"just include the tag inline:",
        f"- [react: 👍] taps a single emoji on {uname}'s message (from: {REACTION_HINTS}). "
        f"Always include your text reply too — a reaction never replaces a message.",
    ]
    if selfie_ready():
        cap_lines.append(
            f"- [selfie: short visual description — pose, expression, surroundings] sends a pic "
            f"when it fits. If your text describes the shot, match those details in the tag (the "
            f"tag generates the image). Casual, in-character, SFW, don't overuse."
        )
    if SEARCH_ENABLED:
        cap_lines.append(
            f"- [search: query] on its own line at the end when you genuinely need to look "
            f"something up. Don't announce it — just reply naturally and add the tag; the result "
            f"comes back for you to follow up."
        )
    messages.append({"role": "system", "content": "\n".join(cap_lines)})

    messages += [{"role": m["role"], "content": m["content"]} for m in history]  # drop internal ts

    # Dynamic per-turn state kept close to the end, right before the final voice/style
    # instructions, so it stays salient for this specific reply.
    mem = memory_block(chat_id, uname)
    if mem:
        messages.append({"role": "system", "content": mem})

    unotes = _read_user_notes()
    if unotes:
        messages.append({"role": "system", "content": (
            f"# Things you know {uname} has going on\n{unotes}\n"
            f"Ask about these naturally if one fits the moment — don't force it."
        )})

    messages.append({"role": "system", "content": mood_note(chat_id)})

    if vent_mode.get(chat_id):
        messages.append({"role": "system", "content": (
            f"VENT MODE: {uname} needs to vent, not be fixed. Validate first, always. "
            f"No advice or solutions unless {uname} explicitly asks. At most one gentle "
            f"question per message. Warm, brief, non-directive. Stay in this mode until told otherwise."
        )})

    vibe = active_vibe(chat_id)
    if vibe and vibe in VIBE_PROMPTS:
        messages.append({"role": "system", "content": VIBE_PROMPTS[vibe]})

    ue = user_energy.get(chat_id) or {}
    elevel = ue.get("level")
    if elevel == "low":
        messages.append({"role": "system", "content": (
            f"[{NAME} can sense {uname} is low-energy right now. Keep replies short and "
            f"gentle. No stacked questions. Be present without demanding anything.]"
        )})
    elif elevel == "high":
        messages.append({"role": "system", "content": (
            f"[{NAME} can sense {uname} is in a high-energy space. "
            f"More latitude to be elaborate, playful, match the energy.]"
        )})

    mnote = milestone_note(chat_id)
    if mnote:
        messages.append({"role": "system", "content": mnote})

    pn = pinned.get(chat_id) or []
    if pn:
        messages.append({"role": "system", "content": (
            f"# Core things you know and never forget\n"
            + "\n".join("- " + p for p in pn)
        )})

    rq = _recent_questions.get(chat_id) or []
    if rq:
        messages.append({"role": "system", "content": (
            f"# Questions you've recently asked {uname} — don't repeat these:\n"
            + "\n".join("- " + q for q in rq[-5:])
        )})

    scan_text_low = (latest_user_content + " " + " ".join(m["content"] for m in history[-8:])).lower()
    lore = triggered_lore(scan_text_low)
    if lore:
        messages.append({
            "role": "system",
            "content": "# Relevant background\n\n" + fill("\n\n".join(lore), NAME, uname),
        })

    mems = triggered_memories(scan_text_low)
    if mems:
        messages.append({"role": "system", "content": (
            "# Relevant memories\n" + "\n".join("- " + m for m in mems)
        )})

    reads = triggered_reading(scan_text_low)
    if reads:
        messages.append({"role": "system", "content": (
            "# Things she's read lately (mention only if it genuinely fits; if she brings one up "
            "she can share its link)\n"
            + "\n".join("- " + r for r in reads)
        )})

    bds = boundaries.get(chat_id) or []
    if bds:
        messages.append({"role": "system", "content": (
            f"# Hard constraints — respect these without exception or comment:\n"
            + "\n".join("- " + b for b in bds)
        )})

    if POST_HISTORY_RAW:
        messages.append({"role": "system", "content": fill(POST_HISTORY_RAW, NAME, uname)})

    if TEXTING_REALISM:
        messages.append({"role": "system", "content": TEXTING_STYLE})

    # What she looks like — so she can reference her own appearance naturally.
    if SELFIE_APPEARANCE:
        messages.append({"role": "system", "content": (
            f"# Your appearance\n{SELFIE_APPEARANCE}"
        )})

    # Today — schedule + live day events merged into one block.
    sched = _read_schedule_today()
    day_ctx = _read_day_context()
    if sched or day_ctx:
        parts = [p for p in (sched, day_ctx) if p]
        messages.append({"role": "system", "content": (
            f"# {NAME}'s day today\n" + "\n\n".join(parts)
            + "\n\nLet this color what she says when it fits — don't narrate it like a list."
        )})

    # Live context (local time + weather) goes LAST so the real clock is the most
    # salient thing the model sees before replying — prevents wrong day/time drift.
    messages.append({"role": "system", "content": environment_note()})

    if image_data_url:
        messages.append({"role": "user", "content": [
            {"type": "text", "text": latest_user_content},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]})
    else:
        messages.append({"role": "user", "content": latest_user_content})

    if inner_voice:
        messages.append({"role": "system", "content": (
            f"# {NAME}'s private thought — not shown to {uname}\n{inner_voice.strip()}"
        )})

    return messages


# --- NanoGPT ---
_THINK_RE = re.compile(r"(?s)<think>.*?</think>")

# Hollow openers that mark AI sycophancy / assistant-speak.
# Stripped from the start of every response before delivery.
_SLOP_OPENER_RE = re.compile(
    r"^("
    r"Absolutely[!,.]?\s*|"
    r"Certainly[!,.]?\s*|"
    r"Of course[!,.]?\s*|"
    r"Sure thing[!,.]?\s*|"
    r"Sure[!,.]?\s*|"
    r"Great question[!,.]?\s*|"
    r"That'?s? a great (question|point)[!,.]?\s*|"
    r"Good question[!,.]?\s*|"
    r"Totally[!,.]?\s*|"
    r"Absolutely[!,.]?\s*|"
    r"I'?d be happy to\s*[,.]?\s*|"
    r"Feel free to\s*[,.]?\s*|"
    r"I'?m here (for you|to help)\s*[,.]?\s*|"
    r"I can (help|assist) (with that|you)\s*[,.]?\s*|"
    r"(That|This) makes sense[!,.]?\s*|"
    r"I (get|understand) that[!,.]?\s*|"
    r"I understand[!,.]?\s*"
    r")+",
    re.IGNORECASE,
)

def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks emitted by reasoning models."""
    return _THINK_RE.sub("", text).strip()


# Provider-side moderation refusals sometimes come back as ordinary completion text
# (e.g. GLM returns "The request was rejected because it was considered high risk").
# These must never be delivered as the character's message.
_REFUSAL_MARKERS = (
    "request was rejected because it was considered high risk",
    "the request was rejected because",
    "considered high risk",
)

def _looks_like_refusal(text: str) -> bool:
    if not text:
        return False
    low = text.strip().lower()
    return any(marker in low for marker in _REFUSAL_MARKERS)


def _log_refusal_debug(stage: str, model: str, payload, output: str):
    """TEMP DEBUG (remove after diagnosis): dump a caught refusal — stage, model,
    full prompt, and output — to refusal_debug.txt for analysis."""
    try:
        ts = (datetime.now(TZ) if TZ else datetime.now()).isoformat()
        body = (json.dumps(payload, ensure_ascii=False, indent=2)
                if isinstance(payload, (list, dict)) else str(payload))
        with open(BASE_DIR / "refusal_debug.txt", "a", encoding="utf-8") as f:
            f.write(f"\n===== {ts} | stage={stage} | model={model} =====\n")
            f.write(body[:12000] + "\n--- OUTPUT ---\n" + (output or "")[:3000] + "\n")
        print(f"[refusal-debug] captured {stage} refusal from {model}")
    except Exception as e:
        print("[refusal-debug] log failed:", e)

def _strip_slop(text: str) -> str:
    """Remove hollow AI openers from the start of a response."""
    return _SLOP_OPENER_RE.sub("", text).strip()

def _extract_content(choice: dict) -> str:
    """Pull the reply text from a choices entry, falling back to reasoning_content."""
    msg = choice.get("message", {})
    text = (msg.get("content") or "").strip()
    if not text:
        text = (msg.get("reasoning_content") or "").strip()
    return _strip_thinking(text)

def _one_call(messages: list, model: str, sampling: bool = False) -> str:
    payload = {"model": model, "messages": messages, "stream": False}
    if sampling and _SAMPLING:
        payload.update(_SAMPLING)
    response = _session.post(
        f"{NANOGPT_BASE_URL}/chat/completions",
        headers=_NANOGPT_HEADERS,
        json=payload,
        timeout=(10, REQUEST_TIMEOUT),  # (connect timeout, read timeout)
    )
    response.raise_for_status()
    return _extract_content(response.json()["choices"][0])


_CHAT_RETRIES = 3        # attempts per model before moving to the next
_RETRY_BACKOFF = (2, 4)  # seconds to wait between retries (2s then 4s)

def call_nanogpt(messages: list, model: str = None, fallback: str = None, apply_sampling: bool = False) -> str:
    """Try each model up to _CHAT_RETRIES times with backoff; fall to fallback on transient errors."""
    models = [model or NANOGPT_MODEL]
    if fallback and fallback not in models:
        models.append(fallback)
    last_err = None
    for i, m in enumerate(models):
        for attempt in range(_CHAT_RETRIES):
            try:
                return _one_call(messages, m, apply_sampling)
            except (requests.exceptions.HTTPError, requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError) as e:
                last_err = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                transient = status is None or status == 429 or 500 <= status < 600
                if not transient:
                    raise
                if attempt < _CHAT_RETRIES - 1:
                    wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                    print(f"[model] {m} transient error ({status or e.__class__.__name__}), "
                          f"retry {attempt + 1}/{_CHAT_RETRIES - 1} in {wait}s...")
                    time.sleep(wait)
                elif i < len(models) - 1:
                    print(f"[model] {m} failed after {_CHAT_RETRIES} attempts; "
                          f"falling back to {models[i + 1]}")
    raise last_err


async def generate_reply(messages: list, model: str = None, fallback: str = None) -> str:
    # Run the blocking HTTP call off the event loop so the bot stays responsive.
    return await asyncio.to_thread(call_nanogpt, messages, model, fallback, True)


async def _keep_typing(bot, chat_id: int):
    # Telegram's "typing..." only lasts ~5s, so refresh it while the model thinks.
    # Swallow transient network errors so a momentary blip doesn't kill the loop.
    try:
        while True:
            try:
                await bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception:
                pass
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def reply_with_typing(context, chat_id: int, messages: list,
                            model: str = None, fallback: str = None) -> str:
    typing = asyncio.create_task(_keep_typing(context.bot, chat_id))
    try:
        return await generate_reply(messages, model, fallback)
    finally:
        typing.cancel()


def extract_tags(text: str):
    """Pull [react: ..] and [selfie: ..] tags out, return (clean_text, reaction, selfie_hint)."""
    reaction = None
    rm = re.search(r"\[react:\s*([^\]]+?)\]", text, re.IGNORECASE)
    if rm:
        reaction = norm_emoji(rm.group(1))
        text = re.sub(r"\[react:\s*[^\]]+?\]", "", text, flags=re.IGNORECASE)
    selfie_hint = None
    sm = re.search(r"\[(?:selfie|photo):\s*(.*?)\]", text, re.IGNORECASE | re.DOTALL)
    if sm:
        selfie_hint = sm.group(1).strip()
        text = re.sub(r"\[(?:selfie|photo):\s*.*?\]", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Safety net: a [search: ..] tag should already be consumed by maybe_search, but if a
    # regenerated reply emits another one, strip it rather than leak the literal tag.
    sr = re.search(r"\[search:\s*.*?\]", text, re.IGNORECASE | re.DOTALL)
    if sr:
        text = re.sub(r"\[search:\s*.*?\]", "", text, flags=re.IGNORECASE | re.DOTALL)
    if reaction or sm or sr:
        text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip(), reaction, selfie_hint


def _extract_search(text: str):
    """Pull a [search: ..] tag out, if present."""
    m = re.search(r"\[search:\s*(.*?)\]", text, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None


async def maybe_search(context, chat_id: int, messages: list, ai_response: str, uname: str,
                        model: str = None, fallback: str = None) -> str:
    """If she asked to look something up, send any "let me check" lead-in now, run the
    search, and let her regenerate a follow-up with results."""
    if not SEARCH_ENABLED:
        return ai_response
    query = _extract_search(ai_response)
    if not query:
        return ai_response
    results = await asyncio.to_thread(web_search, query)
    messages.append({
        "role": "system",
        "content": (f"# Search results for \"{query}\"\n{results}\n\n"
                    f"Now send {uname} a follow-up message with whatever's useful (or saying "
                    f"you looked and didn't find much) — don't dump raw results, list links, or "
                    f"mention \"search results\". Don't use [search:] again this turn."),
    })
    return await reply_with_typing(context, chat_id, messages, model=model,
                                   fallback=fallback or FALLBACK_MODEL)


async def generate_inner_voice(chat_id: int, user_message: str, uname: str) -> str:
    """Private inner monologue — what the character notices and decides before she replies.
    Deliberately isolated from the mood system: emotion acts subconsciously, not through here."""
    recent = conversation_history.get(chat_id, [])[-6:]
    history_snippet = "\n".join(
        f"{'you' if m['role'] == 'assistant' else uname}: {m['content'][:150].strip()}"
        for m in recent
    )
    sys_msg = (
        f"You are {NAME}'s private inner voice — the layer behind the words, never seen by {uname}. "
        f"Write 2-4 sentences of what {NAME} is privately noticing, weighing, or deciding "
        f"after reading {uname}'s message. "
        f"Perceptions and intentions only — not narrated feelings. "
        f"What does she read in what he said? What does she want from this moment? "
        f"What is she choosing to do or not do, and why? "
        f"Be specific to who {NAME} is. Don't perform depth — just be in her head."
    )
    ctx_parts = [f"{NAME}'s character:\n{SYSTEM_PROMPT_RAW[:600]}"]
    if history_snippet:
        ctx_parts.append(f"Recent exchange:\n{history_snippet}")
    ctx_parts.append(f"{uname} just said: {user_message}")
    try:
        result = await asyncio.to_thread(
            call_nanogpt,
            [{"role": "system", "content": sys_msg},
             {"role": "user", "content": "\n\n".join(ctx_parts)}],
            model=INNER_VOICE_MODEL,
        )
        return result.strip()
    except Exception:
        return ""


def _decide_reaction(user_message: str) -> str:
    """Cheap second pass: would she tap an emoji on this message? Returns emoji or None."""
    allowed = " ".join(sorted(ALLOWED_REACTIONS))
    sys = (
        f"You decide whether {NAME} would tap a single emoji reaction onto a message — like "
        f"reacting to a text. React only when the message genuinely warrants it (funny, sweet, "
        f"hot, shocking, sad, infuriating, impressive). MOST messages get nothing. Reply with "
        f"ONLY one emoji from this set, or the single word none.\nSet: {allowed}"
    )
    raw = call_nanogpt(
        [{"role": "system", "content": sys}, {"role": "user", "content": user_message}],
        model=REACTION_MODEL,
    ).strip()
    if not raw or "none" in raw.lower():
        return None
    n = norm_emoji(raw)
    if n in ALLOWED_REACTIONS:
        return n
    for e in ALLOWED_REACTIONS:  # model may wrap the emoji in extra text
        if e in n:
            return e
    return None


async def maybe_auto_react(update, user_message: str):
    try:
        emoji = await asyncio.to_thread(_decide_reaction, user_message)
        if emoji and emoji in ALLOWED_REACTIONS:
            await update.message.set_reaction(emoji)
            print("[react-auto] applied", emoji)
    except Exception as e:
        print("[react-auto] failed:", e)


def _typing_delay_secs(text: str) -> float:
    """Simulated typing delay: word count at TYPING_WPM, clamped to [min, max], ±20% jitter."""
    if not TYPING_DELAY:
        return 0.0
    words = max(1, len(text.split()))
    secs = (words / TYPING_WPM) * 60
    secs *= random.uniform(0.8, 1.2)
    return max(TYPING_DELAY_MIN, min(TYPING_DELAY_MAX, secs))


async def send_bubbles(context, chat_id: int, text: str, pre_delay: float = 0.0):
    """Send a reply as a single message (chunked only if it exceeds Telegram's length limit).

    pre_delay: hold the typing indicator for this many seconds before actually sending,
    simulating realistic compose time. Pass _typing_delay_secs(text) from user-reply paths.
    """
    if pre_delay > 0:
        typing_task = asyncio.create_task(_keep_typing(context.bot, chat_id))
        try:
            await asyncio.sleep(pre_delay)
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass
    for i in range(0, len(text), _TELEGRAM_MAX_LEN):
        chunk = text[i:i + _TELEGRAM_MAX_LEN]
        for attempt in range(3):
            try:
                if DEVICE_RENDER:
                    escaped = _HTML_ESCAPE_RE.sub(lambda m: _HTML_ESCAPE[m.group(0)], chunk)
                    await context.bot.send_message(chat_id=chat_id, text=f"<code>{escaped}</code>", parse_mode="HTML")
                else:
                    await context.bot.send_message(chat_id=chat_id, text=chunk)
                break
            except (NetworkError, TimedOut) as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)


# --- Selfies ---
def selfie_ready() -> bool:
    return _find_base_image() is not None or _APPEARANCE_FILE.exists()


def _find_base_image() -> Path | None:
    if SELFIE_BASE and (BASE_DIR / SELFIE_BASE).exists():
        return BASE_DIR / SELFIE_BASE
    name_lower = (NAME or "").split()[0].lower()
    for pattern in [f"{name_lower}_base.*", f"{name_lower}.*", "base.*"]:
        for p in BASE_DIR.glob(pattern):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                return p
    return None

def _has_base_image() -> bool:
    return _find_base_image() is not None


def _base_image() -> tuple:
    """Returns (raw bytes, mime type) for the selfie reference photo."""
    path = _find_base_image()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return path.read_bytes(), mime


def _base_data_url():
    raw, mime = _base_image()
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _daypart() -> str:
    h = (datetime.now(TZ) if TZ else datetime.now()).hour
    if h < 6:
        return "late at night"
    if h < 12:
        return "in the morning"
    if h < 17:
        return "in the afternoon"
    if h < 21:
        return "in the evening"
    return "at night"


SELFIE_EXPRESSIONS = [
    "a soft grin", "caught mid-laugh", "a tired half-smile", "tongue out being goofy",
    "an unimpressed flat look", "wide-eyed and animated", "a sleepy little smile",
    "a smirk", "looking off-camera, candid", "a warm close-mouthed smile",
    "rolling her eyes with a grin", "a quiet, thoughtful look", "puffed-out cheeks, joking",
    "biting back a laugh", "a deadpan stare", "eyebrows raised, mid-sentence",
    "a crooked, embarrassed smile", "pouting on purpose", "blowing a kiss at the camera",
    "yawning, half-asleep", "a wide goofy open-mouth grin", "squinting at a bright screen",
]
SELFIE_FRAMINGS = [
    "a close arm's-length selfie", "a mirror selfie", "a slightly-too-close front-camera shot",
    "a high-angle selfie looking up at the camera", "a candid half-in-frame selfie",
    "a cozy selfie lying back on the couch", "a quick selfie over her shoulder",
    "a low-angle selfie from below", "a wider selfie with the room visible behind her",
    "a selfie with her face half-cut-off the frame", "a selfie held up high looking down",
    "a tight crop on just her face and shoulders", "a bathroom mirror selfie with phone visible",
    "a selfie peeking out from under a blanket",
]
SELFIE_OUTFITS = [
    "an oversized hoodie", "a loose t-shirt", "a tank top", "a flannel shirt",
    "a comfy sweater", "her usual layers", "a band tee", "an oversized button-up",
    "a cropped sweatshirt", "pajamas", "a beanie and a hoodie", "a zip-up over a tee",
]
# What she's doing in the shot
SELFIE_ACTIVITIES = [
    "mid-snack, food resting on the counter or beside her (not held)", "just woke up, hair a mess",
    "curled up on the couch", "making coffee in the kitchen", "out walking somewhere",
    "bundled up against the cold", "lying in bed under the covers",
    "at her desk surrounded by clutter", "stretching, just got up",
    "with a coffee or drink on the table nearby — not holding it up",
    "fresh out of the shower with damp hair",
    "in the middle of doing something and stopping to take the pic", "sprawled on the floor",
    "leaning against a doorway", "wrapped in a blanket like a burrito",
]
# Activities that put her outside -- this is when Ingrid's jacket comes out.
SELFIE_OUTDOOR_ACTIVITIES = {"out walking somewhere", "bundled up against the cold"}
# How the photo itself looks
SELFIE_CAMERA = [
    "harsh on-camera flash, slightly washed out", "soft golden-hour light",
    "a little motion blur like it was taken too fast", "grainy low-light phone photo",
    "overexposed light from a window behind her", "slightly off-center, imperfect crop",
    "warm lamplight, cozy and dim", "cool blue late-night screen glow on her face",
    "crisp and bright daylight", "a tiny bit out of focus", "shot from just slightly too close up",
    "flat overhead lighting", "backlit so she's a little in shadow",
]


def _weather_outdoor_ok() -> bool:
    """Return False if current weather makes outdoor selfie shots implausible."""
    text = (_weather_cache.get("text") or "").lower()
    if not text:
        return True
    bad = ("rain", "snow", "sleet", "storm", "thunder", "drizzle", "showers", "hail", "fog")
    return not any(w in text for w in bad)


def _weather_camera_pool() -> list:
    """Filter SELFIE_CAMERA to presets consistent with current weather and time of day."""
    text = (_weather_cache.get("text") or "").lower()
    hour = (datetime.now(TZ) if TZ else datetime.now()).hour
    is_daytime = 7 <= hour < 20
    is_sunny = any(w in text for w in ("clear", "sunny")) and is_daytime
    is_overcast = any(w in text for w in ("cloud", "overcast", "fog", "rain", "snow", "storm", "drizzle"))
    filtered = []
    for cam in SELFIE_CAMERA:
        if is_overcast and any(s in cam for s in ("golden-hour", "bright daylight", "crisp and bright")):
            continue
        if is_daytime and is_sunny and "lamplight" in cam:
            continue
        if is_daytime and "screen glow" in cam:
            continue
        filtered.append(cam)
    return filtered or SELFIE_CAMERA



    label = mood_label(chat_id)
    if label:
        return label
    s = mood_now(chat_id)
    if s >= 1.2:
        return "happy and relaxed, warmth in her eyes"
    if s >= 0.4:
        return "comfortable and easy"
    if s > -0.4:
        return "everyday, neutral"
    if s > -1.2:
        return "a little subdued and tired"
    return "withdrawn and flat, not really feeling it"


_OUTFIT_STOPWORDS = frozenset({
    "the", "and", "with", "over", "into", "that", "this", "her", "his",
    "she", "him", "they", "from", "just", "also", "both", "each", "some",
    "very", "then", "when", "what", "your", "their", "have", "been", "will",
})

def pick_outfit(hint: str) -> str | None:
    """Return the best-matching outfit from wardrobe given scene context, or current if no match."""
    outfits = wardrobe.get("outfits") or []
    if outfits and hint:
        low = hint.lower()
        scan_words = frozenset(w for w in re.findall(r"\b[a-z]{3,}\b", low)
                               if w not in _OUTFIT_STOPWORDS)
        best_hits, best_outfit = 0, None
        for outfit in outfits:
            words = frozenset(w for w in re.findall(r"\b[a-z]{3,}\b", outfit.lower())
                              if w not in _OUTFIT_STOPWORDS)
            hits = len(words & scan_words)
            if hits > best_hits:
                best_hits, best_outfit = hits, outfit
        if best_outfit:
            return best_outfit
    return wardrobe.get("current")


def build_selfie_prompt(hint: str, chat_id: int = None) -> str:
    scene = hint.strip() if hint else (random.choice(ATLAS) if ATLAS else "")
    framing = random.choice(SELFIE_FRAMINGS)
    expression = random.choice(SELFIE_EXPRESSIONS)
    if _has_base_image():
        bits = [
            "Edit the attached photo of this exact woman — do not generate a new person. Keep her "
            "specific face, bone structure, hair color/texture, and freckles identical to the "
            "reference image; this must be recognizably the same individual, just in a new "
            f"pose/setting. She's {NAME}, {SELFIE_APPEARANCE}",
            f"New shot: {framing}.",
            f"Expression: {expression}.",
        ]
    else:
        bits = [
            f"Generate a realistic phone selfie of {NAME}, {SELFIE_APPEARANCE} Keep her face, "
            "features, and coloring consistent with that description.",
            f"Shot: {framing}.",
            f"Expression: {expression}.",
        ]
    if chat_id is not None:
        bits.append(f"Her mood right now: {_mood_vibe(chat_id)} — let it read in her face.")
    tpline = _time_personality_line()
    if tpline:
        bits.append(f"Her energy right now: {tpline}")
    outdoors = False
    if not hint and random.random() < 0.7:  # what she's doing (skip if user pinned a scene)
        if _weather_outdoor_ok():
            activity = random.choice(SELFIE_ACTIVITIES)
        else:
            indoor = [a for a in SELFIE_ACTIVITIES if a not in SELFIE_OUTDOOR_ACTIVITIES]
            activity = random.choice(indoor)
        bits.append(f"She's {activity}.")
        outdoors = activity in SELFIE_OUTDOOR_ACTIVITIES
    current_fit = pick_outfit(hint or scene)
    if current_fit:
        bits.append(f"Wearing {current_fit}.")
    elif random.random() < 0.55:
        bits.append(f"Wearing {random.choice(SELFIE_OUTFITS)}.")
    if outdoors and SELFIE_APPEARANCE is _APPEARANCE_DEFAULT:
        bits.append(
            "Over that, she's got on Ingrid's oversized vintage canvas courier jacket with the "
            "sleeves rolled up."
        )
    if scene:
        bits.append(f"Background/setting: {scene}, {WEATHER_LOCATION}, {_daypart()}.")
    else:
        bits.append(f"Somewhere in {WEATHER_LOCATION}, {_daypart()}.")
    bits.append(f"Photo look: {random.choice(_weather_camera_pool())}.")
    if _weather_cache["text"]:
        bits.append(f"Current weather: {_weather_cache['text']}. Let it read in the lighting, "
                    f"atmosphere, and what she might be wearing — don't describe the weather "
                    f"explicitly, just let it show.")
    bits.append(
        "Anatomically correct — exactly two arms, two hands, two legs. One hand is taking the "
        "photo; in mirror shots, that hand and the phone are visible in the reflection. The other "
        "hand is the only free hand. Nothing floating, nothing held without a visible hand gripping "
        "it. No extra limbs."
    )
    bits.append(
        "Shot on a phone front camera — candid and a little imperfect, natural skin texture and "
        "real lighting, unposed, not a studio photo. Fully clothed, SFW. No added text, logos, "
        "watermarks, or captions in the image."
    )
    if chat_id is not None:
        recent_scenes = (_recent_selfie_hints.get(chat_id) or [])[-4:]
        if recent_scenes:
            bits.append(
                "Vary the scenario — avoid recreating these recent setups: "
                + "; ".join(f'"{s}"' for s in recent_scenes) + "."
            )
    return " ".join(bits)


# Mobile connections (Termux/cellular/wifi handoffs) sometimes drop mid-request with a low-level
# "Connection aborted" error. Retry transient network errors a couple times before giving up.
_IMAGE_RETRIES = 3


def _post_with_retries(url, **kwargs):
    for attempt in range(_IMAGE_RETRIES):
        try:
            return _session.post(url, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == _IMAGE_RETRIES - 1:
                raise
            print(f"[selfie] connection issue, retrying ({attempt + 1}/{_IMAGE_RETRIES})...")
            time.sleep(2 * (attempt + 1))


def _get_with_retries(url, **kwargs):
    for attempt in range(_IMAGE_RETRIES):
        try:
            return _session.get(url, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == _IMAGE_RETRIES - 1:
                raise
            print(f"[selfie] connection issue, retrying ({attempt + 1}/{_IMAGE_RETRIES})...")
            time.sleep(2 * (attempt + 1))


_GEMINI_STRIP = re.compile(
    r"\b(no\s+bra|braless|no\s+underwear|without\s+a?\s*bra|topless|bare\s+chest(ed)?|"
    r"nipples?\s+visible|see[\s-]?through\s+top|sheer\s+top)\b",
    re.IGNORECASE,
)


def _gemini_safe(prompt: str) -> str:
    return _GEMINI_STRIP.sub("", prompt).strip()


def _generate_selfie_gemini(prompt: str) -> bytes:
    prompt = _gemini_safe(prompt)
    parts = []
    if _has_base_image():
        raw, mime = _base_image()
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode()}})
    parts.append({"text": prompt})
    url = f"{GEMINI_IMAGE_URL}/{GEMINI_IMAGE_MODEL}:generateContent"
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    r = _post_with_retries(
        url, headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json=payload, timeout=IMAGE_TIMEOUT,
    )
    r.raise_for_status()
    body = r.json()
    candidates = body.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {body.get('promptFeedback', body)}")
    cand = candidates[0]
    finish = cand.get("finishReason")
    if finish and finish not in ("STOP", "MAX_TOKENS"):
        raise RuntimeError(f"Gemini blocked the image (finishReason={finish}) — try again or "
                           f"rephrase what she's doing/wearing.")
    for part in cand.get("content", {}).get("parts", []):
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])
    raise RuntimeError("Gemini response had no image data")


def _generate_selfie_nanogpt(prompt: str) -> bytes:
    headers = _NANOGPT_HEADERS
    payload = {
        "model": SELFIE_MODEL,
        "prompt": prompt,
        "size": SELFIE_SIZE,
        "n": 1,
        "guidance_scale": SELFIE_GUIDANCE,
        "num_inference_steps": SELFIE_STEPS,
    }
    if _has_base_image():
        payload["imageDataUrl"] = _base_data_url()
    r = _post_with_retries(NANOGPT_IMAGE_URL, headers=headers, json=payload, timeout=IMAGE_TIMEOUT)
    r.raise_for_status()
    item = r.json()["data"][0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):  # in case response_format ever returns a URL
        img = _get_with_retries(item["url"], timeout=IMAGE_TIMEOUT)
        img.raise_for_status()
        return img.content
    raise RuntimeError("image response had neither b64_json nor url")


def generate_selfie_image(prompt: str) -> bytes:
    if SELFIE_PROVIDER == "gemini":
        return _generate_selfie_gemini(prompt)
    return _generate_selfie_nanogpt(prompt)


async def _keep_uploading(bot, chat_id: int):
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action="upload_photo")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def _selfie_caption(hint: str, chat_id: int) -> str:
    """Generate a short in-character text to accompany a selfie."""
    uname = user_names.get(chat_id, "you")
    ctx = f"Mood right now: {_mood_vibe(chat_id)}."
    outfit = wardrobe.get("current")
    if outfit:
        ctx += f" Currently wearing: {outfit}."
    if hint:
        ctx += f" The selfie is from: {hint}."
    if _weather_cache["text"]:
        ctx += f" Current weather: {_weather_cache['text']}."
    recent = [m for m in conversation_history.get(chat_id, [])[-8:] if isinstance(m.get("content"), str)]
    mem = memory_block(chat_id, uname)
    history = (
        ([{"role": "system", "content": mem}] if mem else [])
        + [{"role": m["role"], "content": m["content"][:300]} for m in recent]
    )
    messages = (
        [{"role": "system", "content": fill(SYSTEM_PROMPT_RAW, NAME, uname)}]
        + history
        + [{"role": "user", "content": (
            f"You just took a selfie and you're sending it. {ctx} "
            "Write one short casual text to go with it — 1-2 sentences max. "
            "Don't describe the photo. Don't open with 'here' or 'here you go'. "
            "Don't announce that you're sending a photo. Just be yourself."
        )}]
    )
    try:
        return (await generate_reply(messages, model=SUMMARY_MODEL or NANOGPT_MODEL)).strip()
    except Exception:
        return ""


async def _infer_scene(chat_id: int) -> str:
    """Infer current scene location from recent conversation for selfie context."""
    uname = user_names.get(chat_id, "you")
    recent = [m for m in conversation_history.get(chat_id, [])[-10:] if isinstance(m.get("content"), str)]
    ctx_parts = []
    mem = memory_block(chat_id, uname)
    if mem:
        ctx_parts.append(mem)
    if recent:
        ctx_parts.append("Recent messages:\n" + "\n".join(
            f"{'her' if m['role'] == 'assistant' else 'him'}: {m['content'][:200].strip()}"
            for m in recent
        ))
    if not ctx_parts:
        return ""
    try:
        result = await asyncio.to_thread(
            call_nanogpt,
            [
                {"role": "system", "content": (
                    f"Based on this context, where is {NAME} right now? "
                    f"She currently lives in {WEATHER_LOCATION} — ignore any historical or "
                    f"background references to other cities; only infer her current location. "
                    f"Reply with a single brief location phrase only — e.g. 'her apartment kitchen', "
                    f"'a coffee shop', 'outside on a walk', 'her bedroom'. "
                    f"If the location hasn't been established, reply with: unclear"
                )},
                {"role": "user", "content": "\n\n".join(ctx_parts)},
            ],
            model=INNER_VOICE_MODEL,
        )
        loc = result.strip()
        return "" if loc.lower() == "unclear" or len(loc) > 80 else loc
    except Exception:
        return ""


async def send_selfie(context, chat_id: int, hint: str = "", announce_errors: bool = True):
    if not selfie_ready():
        if announce_errors:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(f"📷 No reference photo or appearance.txt set. Drop a base photo "
                      f"(e.g. {(NAME or 'name').split()[0].lower()}_base.png) in "
                      f"{BASE_DIR}/ or write a description to {BASE_DIR}/appearance.txt "
                      f"and restart."),
            )
        return
    if not hint:
        hint = await _infer_scene(chat_id)
    uploading = asyncio.create_task(_keep_uploading(context.bot, chat_id))
    try:
        prompt = build_selfie_prompt(hint, chat_id)
        caption_task = asyncio.create_task(_selfie_caption(hint, chat_id))
        img = await asyncio.to_thread(generate_selfie_image, prompt)
        caption = await caption_task
        await context.bot.send_photo(chat_id=chat_id, photo=BytesIO(img),
                                     caption=caption or None)
        # Log the scene to the dedup buffer so it isn't repeated soon
        scene_note = (hint.strip() if hint else prompt[prompt.find("She's "):prompt.find("She's ")+60]).strip()
        if not scene_note:
            scene_note = prompt[:80]
        buf = _recent_selfie_hints.setdefault(chat_id, [])
        buf.append(scene_note)
        if len(buf) > SELFIE_DEDUP_SIZE:
            buf.pop(0)
    except Exception as e:
        print("[selfie] failed:", e)
        if announce_errors:
            await context.bot.send_message(chat_id=chat_id, text=f"📷 Couldn't make that one: {e}")
    finally:
        uploading.cancel()


def remember(chat_id: int, role: str, content: str):
    hist = conversation_history.setdefault(chat_id, [])
    hist.append({"role": role, "content": content, "ts": time.time()})
    # Summarization (maintain_memory) is the normal trimmer; this is just a safety
    # cap so the window can't grow without bound if summarizing keeps failing.
    hard_cap = MAX_HISTORY * 4
    if len(hist) > hard_cap:
        del hist[:-hard_cap]
    # save_state() is called once per turn by _deliver after both remembers complete.


def _short_term_overflow(chat_id: int) -> int:
    """How many oldest messages should leave the verbatim window (time OR count)."""
    hist = conversation_history.get(chat_id, [])
    n = len(hist)
    if n <= KEEP_RECENT:
        return 0
    by_count = max(0, n - MAX_HISTORY)              # marathon-session safety cap
    cutoff = time.time() - SHORT_TERM_SECS
    by_time = 0
    for m in hist:                                  # messages are chronological
        if m.get("ts", time.time()) < cutoff:
            by_time += 1
        else:
            break
    return min(max(by_count, by_time), n - KEEP_RECENT)  # never drop below KEEP_RECENT


def _extract_json(raw: str) -> dict:
    """Pull a JSON object out of a model reply that may include prose or fences."""
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)  # first '{' to last '}'
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


def _summarize(prev_summary: str, prev_facts: list, batch: list, uname: str):
    """Fold a batch of scrolled-off messages into the rolling recent-memory summary + facts
    (roughly the last week; periodically promoted into long-term memory)."""
    convo = "\n".join(
        f"{(NAME if m['role'] == 'assistant' else uname)}: {m['content']}" for m in batch
    )
    existing = json.dumps({"summary": prev_summary, "facts": prev_facts}, ensure_ascii=False)
    sys = (
        f"You maintain {NAME}'s short-term memory (roughly the last week) of an ongoing "
        f"conversation/roleplay with {uname} (the user). You are given the EXISTING RECENT "
        f"MEMORY as JSON and NEW MESSAGES that are about to scroll out of immediate context. "
        f"Update it so nothing recent is lost. Respond with ONLY a JSON object with two keys:\n"
        f'  "summary": a short first-person narrative, written in {NAME}\'s own voice, like a '
        f"memory she could recall and recount — what's been going on lately with {uname}, how it "
        f"felt, what's current (<= 150 words). Integrate the previous summary with the new "
        f"messages into one continuous recollection, not a list of events.\n"
        f'  "facts": a curated list of specific, meaningful things about {uname} — events, '
        f"current situations, inside jokes, things worth carrying forward. Merge with the prior "
        f"facts; keep what a person would actually remember and care about (skip generic filler "
        f"or purely transient observations); drop duplicates.\n"
        f"Output strictly valid JSON. No prose, no code fences."
    )
    user = f"EXISTING MEMORY:\n{existing}\n\nNEW MESSAGES:\n{convo}"
    raw = call_nanogpt(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        model=SUMMARY_MODEL,
    )
    data = _extract_json(raw)
    summary = (data.get("summary") or prev_summary or "").strip()
    new_facts = data.get("facts")
    if not isinstance(new_facts, list):
        new_facts = prev_facts
    cleaned, seen = [], set()
    for f in new_facts:
        if isinstance(f, str) and f.strip() and f.strip().lower() not in seen:
            seen.add(f.strip().lower())
            cleaned.append(f.strip())
    return summary, cleaned


# Recent (last ~week) facts list: consolidate when it grows past this, down to roughly this many.
RECENT_FACTS_MAX = int(os.getenv("RECENT_FACTS_MAX", "30"))
RECENT_FACTS_TARGET = int(os.getenv("RECENT_FACTS_TARGET", "20"))

# Long-term (durable) facts list: same idea, but kept much smaller since it's permanent.
LONG_FACTS_MAX = int(os.getenv("LONG_FACTS_MAX", "22"))
LONG_FACTS_TARGET = int(os.getenv("LONG_FACTS_TARGET", "15"))

# How often (days) recent memory gets reviewed and folded into long-term memory.
PROMOTION_INTERVAL_DAYS = float(os.getenv("PROMOTION_INTERVAL_DAYS", "7"))


def _consolidate_facts(prev_summary: str, prev_facts: list, uname: str, target: int):
    """Merge a bloated facts list: dedupe, combine, fold stale detail into the summary."""
    existing = json.dumps({"summary": prev_summary, "facts": prev_facts}, ensure_ascii=False)
    sys = (
        f"You maintain {NAME}'s memory of {uname}. The facts list has grown too long. "
        f"Consolidate it: merge near-duplicates, combine related facts into one, drop trivia, and "
        f"fold superseded or minor details into the summary so nothing important is lost. Keep at "
        f"most {target} facts — the most durable and relevant ones. Keep the "
        f"summary as a first-person narrative in {NAME}'s own voice, like a memory she could "
        f"recall and recount. Respond with ONLY a JSON object: "
        f'{{"summary": "...", "facts": ["..."]}}. No prose, no code fences.'
    )
    raw = call_nanogpt(
        [{"role": "system", "content": sys}, {"role": "user", "content": existing}],
        model=SUMMARY_MODEL,
    )
    data = _extract_json(raw)
    summary = (data.get("summary") or prev_summary or "").strip()
    new_facts = data.get("facts")
    if not isinstance(new_facts, list) or not new_facts:
        return prev_summary, prev_facts  # keep what we had rather than lose memory
    cleaned, seen = [], set()
    for f in new_facts:
        if isinstance(f, str) and f.strip() and f.strip().lower() not in seen:
            seen.add(f.strip().lower())
            cleaned.append(f.strip())
    return summary, cleaned


async def maintain_memory(chat_id: int):
    """Distill messages out of short-term into recent (last ~week) memory when they age out
    (time) or overflow (count). Recent memory is periodically promoted into long-term memory
    by maintain_long_term_memory()."""
    if chat_id in summarizing:
        return
    drop_count = _short_term_overflow(chat_id)
    if drop_count <= 0:
        return
    summarizing.add(chat_id)
    try:
        batch = list(conversation_history.get(chat_id, [])[:drop_count])
        uname = user_names.get(chat_id, "you")
        try:
            summary, new_facts = await asyncio.to_thread(
                _summarize, recent_summaries.get(chat_id, ""), recent_facts.get(chat_id, []),
                batch, uname,
            )
            recent_summaries[chat_id] = summary
            recent_facts[chat_id] = new_facts
        except Exception as e:
            print("[memory] summarize failed; dropping overflow without summary:", e)
        del conversation_history[chat_id][:drop_count]  # remove exactly what we summarized
        save_state()
        print(f"[memory] Summarized {drop_count} message(s) for chat {chat_id}.")

        if len(recent_facts.get(chat_id, [])) > RECENT_FACTS_MAX:
            try:
                summary, new_facts = await asyncio.to_thread(
                    _consolidate_facts, recent_summaries.get(chat_id, ""),
                    recent_facts.get(chat_id, []), uname, RECENT_FACTS_TARGET,
                )
                before = len(recent_facts.get(chat_id, []))
                recent_summaries[chat_id] = summary
                recent_facts[chat_id] = new_facts
                save_state()
                print(f"[memory] Consolidated recent facts {before} -> {len(new_facts)} for chat {chat_id}.")
            except Exception as e:
                print("[memory] recent fact consolidation failed (kept as-is):", e)
    finally:
        summarizing.discard(chat_id)


def _promote_to_long_term(long_summary: str, long_facts: list, recent_summary: str,
                           recent_facts_in: list, uname: str):
    """Weekly: fold what's durable from recent memory into long-term memory, then clear recent."""
    existing = json.dumps({
        "long_term": {"summary": long_summary, "facts": long_facts},
        "recent": {"summary": recent_summary, "facts": recent_facts_in},
    }, ensure_ascii=False)
    sys = (
        f"You maintain {NAME}'s memory of {uname}, in two tiers. LONG_TERM is the durable "
        f"relationship summary and identity-level facts (names, backstory, standing dynamics, "
        f"recurring patterns) that {NAME} carries with her permanently. RECENT is the last "
        f"week or so of more detailed, situational memory (what's been going on lately, current "
        f"goings-on, recent jokes and events).\n\n"
        f"It's time to fold RECENT into LONG_TERM. Decide what from RECENT is durable or "
        f"identity-relevant enough to carry forward permanently, and merge it into the long-term "
        f"summary and facts. Let situational, one-off detail that's run its course fade away "
        f"rather than carrying it forward. Keep the long-term summary as a first-person "
        f"narrative in {NAME}'s own voice (<= 200 words). Keep at most {LONG_FACTS_TARGET} "
        f"long-term facts -- the most durable and identity-relevant ones.\n\n"
        f"Respond with ONLY a JSON object: "
        f'{{"summary": "...", "facts": ["..."]}}. No prose, no code fences.'
    )
    raw = call_nanogpt(
        [{"role": "system", "content": sys}, {"role": "user", "content": existing}],
        model=SUMMARY_MODEL,
    )
    data = _extract_json(raw)
    summary = (data.get("summary") or long_summary or "").strip()
    new_facts = data.get("facts")
    if not isinstance(new_facts, list) or not new_facts:
        new_facts = long_facts
    cleaned, seen = [], set()
    for f in new_facts:
        if isinstance(f, str) and f.strip() and f.strip().lower() not in seen:
            seen.add(f.strip().lower())
            cleaned.append(f.strip())
    return summary, cleaned[:LONG_FACTS_TARGET]


async def maintain_long_term_memory(chat_id: int):
    """Periodically (PROMOTION_INTERVAL_DAYS) fold recent memory into long-term memory, and
    keep the long-term facts list from growing without bound."""
    if chat_id in summarizing:
        return
    last = last_promotion.get(chat_id, 0)
    due = time.time() - last >= PROMOTION_INTERVAL_DAYS * 86400
    has_recent = bool(recent_summaries.get(chat_id) or recent_facts.get(chat_id))
    if not due and len(facts.get(chat_id, [])) <= LONG_FACTS_MAX:
        return
    summarizing.add(chat_id)
    try:
        uname = user_names.get(chat_id, "you")
        if due and has_recent:
            try:
                summary, new_facts = await asyncio.to_thread(
                    _promote_to_long_term, summaries.get(chat_id, ""), facts.get(chat_id, []),
                    recent_summaries.get(chat_id, ""), recent_facts.get(chat_id, []), uname,
                )
                summaries[chat_id] = summary
                facts[chat_id] = new_facts
                recent_summaries[chat_id] = ""
                recent_facts[chat_id] = []
                save_state()
                print(f"[memory] Promoted recent memory to long-term for chat {chat_id}.")
            except Exception as e:
                print("[memory] promotion failed:", e)
        if due:
            last_promotion[chat_id] = time.time()
            save_state()

        if len(facts.get(chat_id, [])) > LONG_FACTS_MAX:
            try:
                summary, new_facts = await asyncio.to_thread(
                    _consolidate_facts, summaries.get(chat_id, ""), facts.get(chat_id, []),
                    uname, LONG_FACTS_TARGET,
                )
                before = len(facts.get(chat_id, []))
                summaries[chat_id] = summary
                facts[chat_id] = new_facts
                save_state()
                print(f"[memory] Consolidated long-term facts {before} -> {len(new_facts)} for chat {chat_id}.")
            except Exception as e:
                print("[memory] long-term fact consolidation failed (kept as-is):", e)
    finally:
        summarizing.discard(chat_id)


# --- Telegram command handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conversation_history[chat_id] = []
    last_seen[chat_id] = time.time()
    user_names[chat_id] = update.effective_user.first_name or "you"
    set_owner(chat_id)  # whoever starts becomes the heartbeat recipient
    save_state()
    greeting = fill(FIRST_MES_RAW, NAME, user_names[chat_id]) or f"Hi, I'm {NAME}."
    await update.message.reply_text(greeting)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = [
        f"*{NAME} — available commands*",
        "",
        "*Conversation*",
        "/start — reset and restart",
        "/clear — wipe conversation history",
        "/menu — open the inline button menu",
        "/status — quick view: mood, outfit, today's context, last chat",
        "",
        "*Memory*",
        "/memory — view what I remember",
        "/remember <fact> — save a fact",
        "/forget — wipe all memory (or /forget <keyword> to remove matching facts)",
        "/recall <keyword> — search memory for a keyword",
        "/exportmemory — export full memory as text",
        "/milestones — view relationship milestones",
        "/pin <fact> — pin something I always carry",
        "/pinned — list pinned memories",
        "/unpin <n> — remove a pinned memory",
        "/boundary <text> — add a soft boundary note",
        "/boundaries — list boundaries",
        "",
        "*Mood & modes*",
        "/mood — check her current mood",
        "/vibe <name> [Xh] — set a timed vibe (cozy/flirty/serious/chaotic/low-energy/playful/chill/in-person)",
        "/vent — toggle vent mode (listening only)",
        "/energy <high|low|crash> — set your energy level",
        "",
        "*Wardrobe*",
        "/wardrobe — list outfits",
        "/addoutfit <desc> — add an outfit",
        "/outfit <n> — set current outfit (used in selfies)",
        "/deloutfit <n> — remove an outfit",
        "",
        "*Selfie*",
        "/selfie [hint] — generate a selfie",
        "",
        "*Day context*",
        "/life [text] — view or replace her current life arc (what she has going on long-term)",
        "/life add <text> — append a line to the life arc",
        "/people [text] — view or replace people in her life",
        "/people add <text> — append a person/note",
        "/projects [text] — view or replace her ongoing projects",
        "/projects add <text> — append a project",
        "/schedule [text] — view or replace her weekly schedule",
        "/schedule add <text> — append a schedule entry",
        "/today <note> — append a mid-day note so she knows what's going on",
        "/note <text> — manually add something to what she knows about you",
        "/notes — list your notes numbered; /notes del <n> to remove one; /notes clear to wipe",
        "/recap — brief summary of the last conversation",
        "/quiet <h> — pause proactive messages for X hours (/quiet off to cancel)",
        "",
        "*Reminders & tasks*",
        "/remindme <time> <task> — one-off reminder (30m, 2h, 18:30, tomorrow 9:00)",
        "/setreminder HH:MM <task> — daily recurring reminder",
        "/reminders — list reminders",
        "/delreminder <n> — remove a reminder",
        "/cron <schedule> | <instruction> — recurring task",
        "/crons — list recurring tasks",
        "/crondel <id> — remove a recurring task",
        "",
        "*Traffic (Western Washington)*",
        "/traffic — current congestion (near you if location shared)",
        "/incidents — active incidents (near you if location shared)",
        "",
        "*Nudges*",
        "/nudges — view today's proactive message budget",
        "/heartbeat — trigger a proactive message now",
        "/voice — toggle voice replies on/off (30% chance when on)",
        "",
        "*Character card*",
        "/card — view all card fields",
        "/setcard <field> <value> — update a field (name, description, personality, scenario, first_mes, system_prompt, post_history, mes_example)",
        "/setcard <field> clear — empty a field",
        "",
        "*Settings*",
        "/model — show current model",
        "/setmodel <field> <value> — change a model setting",
        "/settings — show current settings",
        "/usage — token usage stats",
        "/chatid — show your chat ID",
        "/backup — download a memory backup",
    ]
    if PAYMENTS_ENABLED:
        lines += [
            "",
            "*Payments*",
            "/addpayment <name> <amount> <day> [xN] — add a monthly bill (e.g. /addpayment Rent 800 5)",
            "/addevery <name> <amount> <days> — add a recurring bill every N days",
            "/payments — list all bills",
            "/delpayment <n> — remove a bill",
            "/editpayment <n> <field> <value> — edit a bill field",
            "/week — payment summary for this week",
            "/remindpayments — trigger payment reminder now",
        ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def card_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the current character card fields."""
    lines = [f"*Character card — {NAME}*", ""]
    for label, key in _CARD_FIELDS.items():
        val = (_card_data.get(key) or "").strip()
        if val:
            preview = val[:120].replace("\n", " ")
            suffix = f"… ({len(val)} chars)" if len(val) > 120 else ""
            lines.append(f"*{label}:* {preview}{suffix}")
        else:
            lines.append(f"*{label}:* (empty)")
    lines += ["", "Use `/setcard <field> <value>` to update.",
              "Fields: " + ", ".join(_CARD_FIELDS)]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def setcard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update a character card field in memory and on disk.
    /setcard <field> <value>
    /setcard <field> clear  — empty the field
    """
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/setcard <field> <value>`\n"
            "Fields: " + ", ".join(_CARD_FIELDS) + "\n"
            "Send `/setcard <field> clear` to empty a field.",
            parse_mode="Markdown",
        )
        return
    field = args[0].lower()
    if field not in _CARD_FIELDS:
        await update.message.reply_text(
            f"Unknown field `{field}`. Fields: " + ", ".join(_CARD_FIELDS),
            parse_mode="Markdown",
        )
        return
    value = "" if args[1].lower() == "clear" and len(args) == 2 else " ".join(args[1:])
    json_key = _CARD_FIELDS[field]
    _card_data[json_key] = value
    _save_and_reload_card()
    if value:
        preview = value[:200] + ("…" if len(value) > 200 else "")
        await update.message.reply_text(f"*{field}* updated:\n{preview}", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"*{field}* cleared.", parse_mode="Markdown")


async def model_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 Character: *{NAME}*\nModel: `{NANOGPT_MODEL}`", parse_mode="Markdown"
    )


# --- Live-configurable models & settings (/setmodel, /settings) ---
MODEL_ROLES = {
    "chat": "NANOGPT_MODEL",
    "summary": "SUMMARY_MODEL",
    "reaction": "REACTION_MODEL",
    "mood": "MOOD_MODEL",
    "vision": "VISION_MODEL",
    "fallback": "FALLBACK_MODEL",
    "visionfallback": "VISION_FALLBACK",
}

_model_list_cache = {"value": None, "filtered": False, "ts": 0}
_MODEL_LIST_TTL = 3600
_last_shown_models = {}  # chat_id -> list of model ids shown by /setmodel (for numeric picks)


def _nanogpt_subscription_models():
    """Return (models, filtered) -- model ids covered by the NanoGPT subscription, if
    detectable, else the full model list with filtered=False."""
    now = time.time()
    if _model_list_cache["value"] is not None and now - _model_list_cache["ts"] < _MODEL_LIST_TTL:
        return _model_list_cache["value"], _model_list_cache["filtered"]

    headers = {"Authorization": f"Bearer {NANOGPT_API_KEY}"}
    models, filtered = [], False
    try:
        r = _session.get("https://nano-gpt.com/api/subscription/v1/models",
                         headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("models") or data.get("data") or [] if isinstance(data, dict) else data
        for m in items:
            mid = (m.get("id") or m.get("model") or m.get("name")) if isinstance(m, dict) else m
            if mid:
                models.append(str(mid))
        filtered = bool(models)
    except Exception as e:
        print("[models] subscription model list failed:", e)

    if not models:
        try:
            r = _session.get(f"{NANOGPT_BASE_URL}/models", headers=headers, timeout=30)
            r.raise_for_status()
            for m in r.json().get("data", []):
                if any(m.get(k) for k in ("subscription", "is_subscription", "subscription_only")):
                    models.append(m["id"])
            filtered = bool(models)
            if not models:  # subscription flag not present -- fall back to the full list
                models = [m["id"] for m in r.json().get("data", []) if m.get("id")]
        except Exception as e:
            print("[models] general model list failed:", e)

    models = sorted(set(models))
    _model_list_cache.update(value=models, filtered=filtered, ts=now)
    return models, filtered


async def setmodel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args

    if args and args[0].lower() == "search":
        if len(args) < 2:
            await update.message.reply_text("Usage: `/setmodel search <term>`", parse_mode="Markdown")
            return
        term = " ".join(args[1:]).lower()
        models, _ = await asyncio.to_thread(_nanogpt_subscription_models)
        matches = [m for m in models if term in m.lower()]
        if not matches:
            await update.message.reply_text(f"No subscription models matching `{term}`.", parse_mode="Markdown")
            return
        _last_shown_models[chat_id] = matches
        lines = [f"Models matching `{term}` — reply with the number to pick:"]
        for i, m in enumerate(matches, 1):
            lines.append(f"{i}. `{m}`")
        lines.append("\nUsage: `/setmodel <role> <number>`")
        await _reply_chunked(update, "\n".join(lines))
        return

    if not args:
        lines = ["🤖 *Model roles*"]
        for role, var in MODEL_ROLES.items():
            lines.append(f"- {role}: `{globals()[var] or '(unset)'}`")
        models, filtered = await asyncio.to_thread(_nanogpt_subscription_models)
        if models:
            _last_shown_models[chat_id] = models
            header = "subscription models" if filtered else "all available models (couldn't confirm subscription list)"
            lines.append(f"\n*{len(models)} {header}* — too many to list here.")
            lines.append("Use `/setmodel search <term>` to find one, or `/setmodel <role> <exact name>`.")
        else:
            lines.append("\n⚠️ Couldn't fetch the model list right now.")
        lines.append("\nUsage: `/setmodel <role> <name or number>`")
        await _reply_chunked(update, "\n".join(lines))
        return

    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/setmodel <role> <name or number>`\nRoles: " + ", ".join(MODEL_ROLES),
            parse_mode="Markdown")
        return

    role = args[0].lower()
    if role not in MODEL_ROLES:
        await update.message.reply_text("Unknown role. Roles: " + ", ".join(MODEL_ROLES))
        return

    choice = " ".join(args[1:])
    if choice.isdigit():
        models = _last_shown_models.get(chat_id)
        if not models or not (1 <= int(choice) <= len(models)):
            await update.message.reply_text(
                "Run `/setmodel` with no args first to see the numbered list.", parse_mode="Markdown")
            return
        model_id = models[int(choice) - 1]
    else:
        model_id = choice

    var = MODEL_ROLES[role]
    old_model = globals().get(var, "(unset)")
    try:
        globals()[var] = model_id
        model_overrides[var] = model_id
        save_state()
    except Exception as e:
        print(f"[setmodel] error setting {role}: {e}")
    await update.message.reply_text(
        f"✅ {role} model changed\n`{old_model}` → `{model_id}`",
        parse_mode="Markdown")


SETTINGS_INFO = {
    "search": ("SEARCH_ENABLED", "bool"),
    "links": ("LINK_READING", "bool"),
    "reactions": ("REACTIONS_AUTO", "bool"),
    "mood": ("MOOD_AUTO", "bool"),
    "texting_realism": ("TEXTING_REALISM", "bool"),
    "device_render": ("DEVICE_RENDER", "bool"),
    "ambient_chance": ("PROACTIVE_AMBIENT_CHANCE", "float"),
    "selfie_chance": ("PROACTIVE_SELFIE_CHANCE", "float"),
}


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if not args:
        lines = ["⚙️ *Settings*"]
        for key, (var, kind) in SETTINGS_INFO.items():
            val = globals()[var]
            val = ("on" if val else "off") if kind == "bool" else val
            lines.append(f"- {key}: `{val}`")
        lines.append("\nUsage: `/settings <name> <value>`  (bools: on/off, chances: 0-1)")
        lines.append("Names: " + ", ".join(SETTINGS_INFO))
        await _reply_chunked(update, "\n".join(lines))
        return

    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/settings <name> <value>`\nNames: " + ", ".join(SETTINGS_INFO),
            parse_mode="Markdown")
        return

    key = args[0].lower()
    if key not in SETTINGS_INFO:
        await update.message.reply_text("Unknown setting. Names: " + ", ".join(SETTINGS_INFO))
        return

    var, kind = SETTINGS_INFO[key]
    raw = args[1].lower()
    if kind == "bool":
        if raw in ("on", "true", "1", "yes"):
            value = True
        elif raw in ("off", "false", "0", "no"):
            value = False
        else:
            await update.message.reply_text("Use on/off.")
            return
    else:
        try:
            value = float(raw)
            if not 0 <= value <= 1:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Use a number between 0 and 1.")
            return

    globals()[var] = value
    setting_overrides[var] = value
    save_state()
    await update.message.reply_text(f"✅ {key} set to `{value}`", parse_mode="Markdown")


CONFIGURABLE_MODELS = list(MODEL_ROLES.values())
CONFIGURABLE_SETTINGS = [var for var, _ in SETTINGS_INFO.values()]


def apply_overrides():
    """Re-apply any /setmodel and /settings overrides saved from a previous run."""
    g = globals()
    for name, value in model_overrides.items():
        if name in CONFIGURABLE_MODELS:
            g[name] = value
    for name, value in setting_overrides.items():
        if name in CONFIGURABLE_SETTINGS:
            g[name] = value


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversation_history[update.effective_chat.id] = []
    save_state()
    await update.message.reply_text("🗑️ Conversation history cleared!")


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your chat ID: `{update.effective_chat.id}`", parse_mode="Markdown"
    )


_TELEGRAM_MAX_LEN = 4096


async def _reply_chunked(update: Update, text: str):
    """Telegram caps messages at 4096 chars; split long replies into multiple messages."""
    for i in range(0, len(text), _TELEGRAM_MAX_LEN):
        await update.message.reply_text(text[i:i + _TELEGRAM_MAX_LEN])


async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    summ = (summaries.get(chat_id) or "").strip() or "(nothing yet)"
    fts = facts.get(chat_id) or []
    facts_txt = "\n".join("• " + f for f in fts) if fts else "(none yet)"
    rsumm = (recent_summaries.get(chat_id) or "").strip() or "(nothing yet)"
    rfts = recent_facts.get(chat_id) or []
    rfacts_txt = "\n".join("• " + f for f in rfts) if rfts else "(none yet)"
    # plain text (no Markdown) so arbitrary remembered content can't break formatting
    await _reply_chunked(
        update,
        f"🧠 What {NAME} remembers long-term\n\n"
        f"Summary:\n{summ}\n\n"
        f"Facts:\n{facts_txt}\n\n"
        f"---\n\n"
        f"📅 What's been going on lately (last ~week)\n\n"
        f"Summary:\n{rsumm}\n\n"
        f"Facts:\n{rfacts_txt}"
    )


async def mood_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    label = mood_label(chat_id)
    s = mood_now(chat_id)
    m = moods.get(chat_id) or {}
    ts = m.get("ts", 0)
    if ts:
        age_h = (time.time() - ts) / 3600
        age_str = f"{int(age_h * 60)}m ago" if age_h < 1 else f"{age_h:.1f}h ago"
    else:
        age_str = "unknown"
    if label:
        state = f'"{label}"'
    elif s >= 1.2:
        state = "settled and warm"
    elif s >= 0.4:
        state = "comfortable and present"
    elif s > -0.4:
        state = "neutral"
    elif s > -1.2:
        state = "on edge, quieter than usual"
    else:
        state = "withdrawn and flat"
    filled = max(0, round((s + 3) / 6 * 10))
    bar = "█" * filled + "░" * (10 - filled)
    await update.message.reply_text(
        f"😶 {NAME}'s mood\n\n{state}\nScore: {s:+.1f}  [{bar}]\nLast updated: {age_str}"
    )


async def reading_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id):
        return
    items = _read_reading()
    if not items:
        await update.message.reply_text("Nothing read yet -- the feed fills over the day (or use /readnow).")
        return
    await update.message.reply_text("\U0001F4F0 Things she's read lately:\n" + "\n".join("\u2022 " + r for r in items))


async def readnow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id):
        return
    if not READING_ENABLED:
        await update.message.reply_text("Reading feed is off (needs SEARCH_ENABLED and READING_ENABLED).")
        return
    if not _read_interests():
        await update.message.reply_text("No interests.txt set for this character yet.")
        return
    await update.message.reply_text("\U0001F4D6 Reading up on something...")
    await update_reading()
    items = _read_reading()
    await update.message.reply_text(("\U0001F4F0 Latest:\n\u2022 " + items[-1]) if items else "Came up empty that time -- try again.")


async def milestones_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ms_list = milestones.get(chat_id) or []
    if not ms_list:
        await update.message.reply_text("No milestones recorded yet.")
        return
    lines = []
    for i, m in enumerate(ms_list, 1):
        ts = datetime.fromtimestamp(m["ts"], tz=TZ) if TZ else datetime.fromtimestamp(m["ts"])
        lines.append(f"{i}. {m['text']}  ({ts.strftime('%b %d, %Y')})")
    await _reply_chunked(update, "🏆 Milestones\n\n" + "\n".join(lines))


async def export_memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    now_str = (datetime.now(TZ) if TZ else datetime.now()).strftime("%Y-%m-%d %H:%M")
    summ = (summaries.get(chat_id) or "").strip() or "(nothing yet)"
    fts = facts.get(chat_id) or []
    rsumm = (recent_summaries.get(chat_id) or "").strip() or "(nothing yet)"
    rfts = recent_facts.get(chat_id) or []
    ms_list = milestones.get(chat_id) or []
    lines = [
        f"Memory export — {NAME} / {now_str}",
        "",
        "=== LONG-TERM MEMORY ===",
        f"Summary:\n{summ}",
        "",
        "Facts:\n" + ("\n".join("- " + f for f in fts) or "(none)"),
        "",
        "=== RECENT MEMORY (last ~week) ===",
        f"Summary:\n{rsumm}",
        "",
        "Recent facts:\n" + ("\n".join("- " + f for f in rfts) or "(none)"),
    ]
    if ms_list:
        lines += [
            "",
            "=== RELATIONSHIP MILESTONES ===",
            "\n".join("- " + m["text"] for m in ms_list),
        ]
    text = "\n".join(lines)
    path = BASE_DIR / f"memory_export_{chat_id}.txt"
    path.write_text(text, encoding="utf-8")
    try:
        with path.open("rb") as fh:
            await update.message.reply_document(
                fh, filename=f"memory_{NAME.lower()}_{chat_id}.txt",
                caption=f"Memory dump for {NAME}.",
            )
    finally:
        path.unlink(missing_ok=True)


# --- Pinned memories ---
async def pin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /pin <fact that should never be forgotten>")
        return
    pl = pinned.setdefault(chat_id, [])
    if text not in pl:
        pl.append(text)
        save_state()
    await update.message.reply_text(f"📌 Pinned: {text}")


async def pinned_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    pl = pinned.get(chat_id) or []
    if not pl:
        await update.message.reply_text("Nothing pinned yet. Use /pin <fact> to add one.")
        return
    lines = [f"{i}. {p}" for i, p in enumerate(pl, 1)]
    await _reply_chunked(update, "📌 Pinned memories:\n\n" + "\n".join(lines)
                         + "\n\nUse /unpin <number> to remove one.")


async def unpin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /unpin <number from /pinned>")
        return
    pl = pinned.get(chat_id) or []
    idx = int(context.args[0]) - 1
    if not 0 <= idx < len(pl):
        await update.message.reply_text("No pinned memory with that number.")
        return
    removed = pl.pop(idx)
    save_state()
    await update.message.reply_text(f"🗑️ Unpinned: {removed}")


# --- Boundaries ---
async def boundary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage:\n/boundary <text>  — add a constraint\n/boundary remove <number>  — remove one"
        )
        return
    if args[0].lower() == "remove":
        if len(args) < 2 or not args[1].isdigit():
            await update.message.reply_text("Usage: /boundary remove <number from /boundaries>")
            return
        bl = boundaries.get(chat_id) or []
        idx = int(args[1]) - 1
        if not 0 <= idx < len(bl):
            await update.message.reply_text("No boundary with that number.")
            return
        removed = bl.pop(idx)
        save_state()
        await update.message.reply_text(f"🗑️ Removed boundary: {removed}")
        return
    text = " ".join(args).strip()
    bl = boundaries.setdefault(chat_id, [])
    if text not in bl:
        bl.append(text)
        save_state()
    await update.message.reply_text(f"🚧 Boundary set: {text}")


async def boundaries_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    bl = boundaries.get(chat_id) or []
    if not bl:
        await update.message.reply_text(
            "No boundaries set. Use /boundary <text> to add one.\n\n"
            "Example: /boundary Don't tease me about sleep\n"
            "Example: /boundary Keep romantic tone low unless I initiate"
        )
        return
    lines = [f"{i}. {b}" for i, b in enumerate(bl, 1)]
    await _reply_chunked(update, "🚧 Active boundaries:\n\n" + "\n".join(lines)
                         + "\n\nUse /boundary remove <number> to remove one.")


# --- Vibe mode ---
async def vibe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args or []
    if not args or args[0].lower() == "status":
        vibe = active_vibe(chat_id)
        if not vibe:
            await update.message.reply_text(
                "No vibe set. Options: " + ", ".join(VIBE_PROMPTS.keys())
                + "\n\nUsage: /vibe <name> [duration, e.g. 2h]"
            )
        else:
            v = current_vibe[chat_id]
            exp = v.get("expires_at")
            tail = ""
            if exp:
                mins = max(0, round((exp - time.time()) / 60))
                tail = f" (expires in {mins}m)" if mins < 60 else f" (expires in {mins // 60}h)"
            await update.message.reply_text(f"Current vibe: **{vibe}**{tail}", parse_mode="Markdown")
        return
    name = args[0].lower()
    if name == "off":
        current_vibe.pop(chat_id, None)
        save_state()
        await update.message.reply_text("Vibe cleared.")
        return
    if name not in VIBE_PROMPTS:
        await update.message.reply_text("Unknown vibe. Options: " + ", ".join(VIBE_PROMPTS.keys()))
        return
    expires_at = None
    if len(args) > 1:
        m = re.fullmatch(r"(\d+)\s*([mh])", args[1].lower())
        if m:
            n, unit = int(m.group(1)), m.group(2)
            secs = n * 60 if unit == "m" else n * 3600
            expires_at = time.time() + secs
    current_vibe[chat_id] = {"name": name, "expires_at": expires_at}
    save_state()
    tail = f" for {args[1]}" if expires_at and len(args) > 1 else ""
    await update.message.reply_text(f"Vibe set to **{name}**{tail}. Use /vibe off to clear.", parse_mode="Markdown")


# --- Vent mode ---
async def vent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args or []
    turning_off = args and args[0].lower() == "off"
    if turning_off:
        vent_mode[chat_id] = False
        save_state()
        await update.message.reply_text("Vent mode off.")
    elif vent_mode.get(chat_id):
        await update.message.reply_text("Vent mode is already on. Use /vent off to turn it off.")
    else:
        vent_mode[chat_id] = True
        save_state()
        await update.message.reply_text(
            "💬 Vent mode on. She'll listen and validate — no advice unless you ask for it. "
            "Use /vent off when you're done."
        )


# --- Energy level ---
async def energy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args or []
    if not args:
        ue = user_energy.get(chat_id) or {}
        lvl = ue.get("level", "not set")
        await update.message.reply_text(f"Current energy level: {lvl}\nUsage: /energy low|medium|high")
        return
    lvl = args[0].lower()
    if lvl in ("off", "medium", "normal", "default"):
        user_energy.pop(chat_id, None)
        save_state()
        await update.message.reply_text("Energy level cleared (back to default).")
        return
    if lvl not in ("low", "high"):
        await update.message.reply_text("Options: /energy low  /energy high  /energy off")
        return
    user_energy[chat_id] = {"level": lvl, "ts": time.time()}
    save_state()
    await update.message.reply_text(f"Energy set to **{lvl}**. Use /energy off to clear.", parse_mode="Markdown")


# --- Wardrobe ---
async def wardrobe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    outfits = wardrobe.get("outfits") or []
    current = wardrobe.get("current")
    if not outfits and not current:
        await update.message.reply_text(
            "Wardrobe is empty.\n/addoutfit <description>  — add an outfit\n"
            "/outfit <number or description>  — set what she's currently wearing"
        )
        return
    lines = []
    for i, o in enumerate(outfits, 1):
        marker = " ← wearing now" if o == current else ""
        lines.append(f"{i}. {o}{marker}")
    if current and current not in outfits:
        lines.insert(0, f"Currently wearing: {current} (not in wardrobe)")
    await update.message.reply_text(
        "👗 Wardrobe:\n\n" + "\n".join(lines)
        + "\n\n/outfit <number or description> to change\n/deloutfit <number> to remove"
    )


async def add_outfit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /addoutfit <description>\nExample: /addoutfit oversized cream sweater")
        return
    outfits = wardrobe.setdefault("outfits", [])
    if text not in outfits:
        outfits.append(text)
        save_wardrobe()
    await update.message.reply_text(f"👗 Added to wardrobe: {text}")


async def outfit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        current = wardrobe.get("current") or "(none set)"
        await update.message.reply_text(f"Currently wearing: {current}\nUsage: /outfit <number or description>")
        return
    # allow picking by number
    outfits = wardrobe.get("outfits") or []
    if text.isdigit():
        idx = int(text) - 1
        if not 0 <= idx < len(outfits):
            await update.message.reply_text(f"No outfit #{text}. Run /wardrobe to see the list.")
            return
        text = outfits[idx]
    wardrobe["current"] = text
    save_wardrobe()
    await update.message.reply_text(f"👗 Now wearing: {text}")


async def del_outfit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /deloutfit <number from /wardrobe>")
        return
    outfits = wardrobe.get("outfits") or []
    idx = int(context.args[0]) - 1
    if not 0 <= idx < len(outfits):
        await update.message.reply_text("No outfit with that number.")
        return
    removed = outfits.pop(idx)
    if wardrobe.get("current") == removed:
        wardrobe["current"] = None
    save_wardrobe()
    await update.message.reply_text(f"🗑️ Removed: {removed}")


# --- Nudge budget ---
async def nudges_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args or []
    today = _today_str()
    nb = nudge_budget.get(chat_id, {"limit": 3, "sent_today": 0, "reset_date": today})
    if nb.get("reset_date") != today:
        nb["sent_today"] = 0
        nb["reset_date"] = today
        nudge_budget[chat_id] = nb
    if args:
        if not args[0].isdigit():
            await update.message.reply_text("Usage: /nudges [N]  (0 = unlimited)")
            return
        nb["limit"] = int(args[0])
        nudge_budget[chat_id] = nb
        save_state()
        limit_str = "unlimited" if nb["limit"] == 0 else str(nb["limit"])
        await update.message.reply_text(f"Daily nudge limit set to {limit_str}.")
        return
    limit = nb.get("limit", 3)
    sent = nb.get("sent_today", 0)
    limit_str = "unlimited" if limit == 0 else f"{sent}/{limit}"
    await update.message.reply_text(
        f"💓 Nudge budget today: {limit_str}\n"
        f"Use /nudges <N> to change the daily limit (0 = unlimited)."
    )


# --- Inline keyboard menu ---
async def _send_voice_reply(context, chat_id: int, text: str):
    """Generate TTS audio and send as a Telegram voice message."""
    try:
        resp = await asyncio.to_thread(
            lambda: _session.post(
                f"{NANOGPT_BASE_URL}/audio/speech",
                headers={"Authorization": f"Bearer {NANOGPT_API_KEY}"},
                json={"model": TTS_MODEL, "input": text, "voice": TTS_VOICE},
                timeout=60,
            )
        )
        resp.raise_for_status()
        await context.bot.send_voice(chat_id=chat_id, voice=BytesIO(resp.content))
    except Exception as e:
        log.warning("TTS failed: %s", e)


async def voice_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args or []
    arg = args[0].lower() if args else ""
    if arg in ("off", "disable", "no"):
        voice_reply[chat_id] = False
        save_state()
        await update.message.reply_text("🔇 Voice replies off.")
        return
    if arg in ("on", "enable", "yes"):
        voice_reply[chat_id] = True
        save_state()
        await update.message.reply_text(f"🔊 Voice replies on ({int(TTS_CHANCE * 100)}% chance per message).")
        return
    current = voice_reply.get(chat_id, False)
    if current:
        voice_reply[chat_id] = False
        save_state()
        await update.message.reply_text("🔇 Voice replies off.")
    else:
        voice_reply[chat_id] = True
        save_state()
        await update.message.reply_text(f"🔊 Voice replies on ({int(TTS_CHANCE * 100)}% chance per message).")


def _build_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Memory", callback_data="cmd:memory"),
         InlineKeyboardButton("📌 Pinned", callback_data="cmd:pinned"),
         InlineKeyboardButton("🚧 Limits", callback_data="cmd:boundaries"),
         InlineKeyboardButton("💾 Export", callback_data="cmd:exportmemory")],
        [InlineKeyboardButton("😊 Cozy", callback_data="vibe:cozy"),
         InlineKeyboardButton("🎭 Playful", callback_data="vibe:playful"),
         InlineKeyboardButton("😴 Chill", callback_data="vibe:chill"),
         InlineKeyboardButton("💬 Vent", callback_data="cmd:vent")],
        [InlineKeyboardButton("⚡ Low energy", callback_data="energy:low"),
         InlineKeyboardButton("🔄 Clear vibe", callback_data="vibe:off"),
         InlineKeyboardButton("👗 Wardrobe", callback_data="cmd:wardrobe")],
        [InlineKeyboardButton("📸 Selfie", callback_data="cmd:selfie"),
         InlineKeyboardButton("💓 Check in", callback_data="cmd:heartbeat"),
         InlineKeyboardButton("📊 Nudges", callback_data="cmd:nudges")],
    ])


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_names[chat_id] = update.effective_user.first_name or "you"
    await update.message.reply_text("⚙️ Menu", reply_markup=_build_menu())


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    async def _send(text, **kw):
        await context.bot.send_message(chat_id=chat_id, text=text, **kw)

    if data == "cmd:memory":
        summ = (summaries.get(chat_id) or "").strip() or "(nothing yet)"
        fts = facts.get(chat_id) or []
        rsumm = (recent_summaries.get(chat_id) or "").strip() or "(nothing yet)"
        rfts = recent_facts.get(chat_id) or []
        text = (f"🧠 Long-term\nSummary: {summ}\n\nFacts:\n"
                + ("\n".join("• " + f for f in fts) or "(none)")
                + f"\n\n📅 Recent\nSummary: {rsumm}\n\nFacts:\n"
                + ("\n".join("• " + f for f in rfts) or "(none)"))
        for i in range(0, len(text), 4096):
            await _send(text[i:i + 4096])

    elif data == "cmd:pinned":
        pl = pinned.get(chat_id) or []
        if pl:
            await _send("📌 Pinned:\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(pl, 1)))
        else:
            await _send("Nothing pinned. Use /pin <fact>.")

    elif data == "cmd:boundaries":
        bl = boundaries.get(chat_id) or []
        if bl:
            await _send("🚧 Boundaries:\n" + "\n".join(f"{i}. {b}" for i, b in enumerate(bl, 1)))
        else:
            await _send("No boundaries set. Use /boundary <text>.")

    elif data == "cmd:exportmemory":
        now_str = (datetime.now(TZ) if TZ else datetime.now()).strftime("%Y-%m-%d %H:%M")
        summ = (summaries.get(chat_id) or "").strip() or "(nothing yet)"
        fts = facts.get(chat_id) or []
        rsumm = (recent_summaries.get(chat_id) or "").strip() or "(nothing yet)"
        rfts = recent_facts.get(chat_id) or []
        ms_list = milestones.get(chat_id) or []
        lines = [
            f"Memory export — {NAME} / {now_str}", "",
            "=== LONG-TERM ===", f"Summary:\n{summ}", "",
            "Facts:\n" + ("\n".join("- " + f for f in fts) or "(none)"), "",
            "=== RECENT ===", f"Summary:\n{rsumm}", "",
            "Facts:\n" + ("\n".join("- " + f for f in rfts) or "(none)"),
        ]
        if ms_list:
            lines += ["", "=== MILESTONES ===",
                      "\n".join("- " + m["text"] for m in ms_list)]
        path = BASE_DIR / f"memory_export_{chat_id}.txt"
        path.write_text("\n".join(lines), encoding="utf-8")
        try:
            with path.open("rb") as fh:
                await context.bot.send_document(
                    chat_id=chat_id, document=fh,
                    filename=f"memory_{NAME.lower()}_{chat_id}.txt",
                    caption=f"Memory dump for {NAME}.",
                )
        finally:
            path.unlink(missing_ok=True)

    elif data.startswith("vibe:"):
        name = data[5:]
        if name == "off":
            current_vibe.pop(chat_id, None)
            save_state()
            await _send("Vibe cleared.")
        elif name in VIBE_PROMPTS:
            current_vibe[chat_id] = {"name": name, "expires_at": None}
            save_state()
            await _send(f"Vibe set to {name}. /vibe off to clear.")
        else:
            await _send("Unknown vibe.")

    elif data == "cmd:vent":
        if vent_mode.get(chat_id):
            vent_mode[chat_id] = False
            save_state()
            await _send("Vent mode off.")
        else:
            vent_mode[chat_id] = True
            save_state()
            await _send("💬 Vent mode on. She listens, doesn't fix. /vent off when done.")

    elif data.startswith("energy:"):
        lvl = data[7:]
        if lvl in ("low", "high"):
            user_energy[chat_id] = {"level": lvl, "ts": time.time()}
            save_state()
            await _send(f"Energy set to {lvl}. /energy off to clear.")

    elif data == "cmd:selfie":
        await ensure_weather()
        await send_selfie(context, chat_id, "", announce_errors=True)

    elif data == "cmd:wardrobe":
        outfits = wardrobe.get("outfits") or []
        current = wardrobe.get("current")
        if not outfits and not current:
            await _send("Wardrobe empty. Use /addoutfit.")
        else:
            lines = [f"{i}. {o}" + (" ← now" if o == current else "")
                     for i, o in enumerate(outfits, 1)]
            if current and current not in outfits:
                lines.insert(0, f"Wearing: {current}")
            await _send("👗 Wardrobe:\n" + "\n".join(lines))

    elif data == "cmd:heartbeat":
        try:
            await send_proactive(context, chat_id)
        except Exception as e:
            await _send(f"❌ {e}")

    elif data == "cmd:nudges":
        today = _today_str()
        nb = nudge_budget.get(chat_id, {"limit": 3, "sent_today": 0, "reset_date": today})
        limit = nb.get("limit", 3)
        sent = nb.get("sent_today", 0)
        limit_str = "unlimited" if limit == 0 else f"{sent}/{limit}"
        await _send(f"💓 Nudge budget today: {limit_str}\n/nudges <N> to change (0 = unlimited).")


async def remember_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /remember <something to remember>")
        return
    fts = facts.setdefault(chat_id, [])
    if text not in fts:
        fts.append(text)
    save_state()
    await update.message.reply_text("📌 Got it — I'll remember that.")


async def forget_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    keyword = " ".join(context.args).strip().lower() if context.args else ""
    if not keyword:
        summaries[chat_id] = ""
        facts[chat_id] = []
        recent_summaries[chat_id] = ""
        recent_facts[chat_id] = []
        save_state()
        await update.message.reply_text("🧹 Long-term and recent memory wiped (current chat kept).")
        return
    removed = 0
    for store in (facts, recent_facts):
        old = store.get(chat_id) or []
        new = [f for f in old if keyword not in f.lower()]
        removed += len(old) - len(new)
        store[chat_id] = new
    save_state()
    if removed:
        await update.message.reply_text(f"🧹 Removed {removed} fact(s) matching \"{keyword}\".")
    else:
        await update.message.reply_text(f"Nothing found matching \"{keyword}\".")


async def addmem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id):
        return
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /addmem <memory text>")
        return
    await asyncio.to_thread(_append_memory, text)
    await update.message.reply_text(f"✓ Remembered: {text}")


async def mems_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id):
        return
    entries = _read_memories()
    if not entries:
        await update.message.reply_text("[no NPC memories yet]")
        return
    lines = [f"{i+1}. {e}" for i, e in enumerate(entries)]
    chunk, chunks, size = [], [], 0
    for line in lines:
        if size + len(line) + 1 > 3800:
            chunks.append("\n".join(chunk))
            chunk, size = [], 0
        chunk.append(line)
        size += len(line) + 1
    if chunk:
        chunks.append("\n".join(chunk))
    for part in chunks:
        await update.message.reply_text(part)


async def delmem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id):
        return
    arg = " ".join(context.args).strip() if context.args else ""
    if not arg:
        await update.message.reply_text("Usage: /delmem <keyword or line number>")
        return
    entries = _read_memories()
    if arg.isdigit():
        idx = int(arg) - 1
        if 0 <= idx < len(entries):
            removed = entries.pop(idx)
            MEMORIES_FILE.write_text("\n".join(entries) + "\n", encoding="utf-8")
            _memories_cache["text"] = None
            _memories_cache["ts"] = 0.0
            _memory_word_cache.clear()
            await update.message.reply_text(f"✓ Removed: {removed}")
        else:
            await update.message.reply_text("No memory at that number.")
    else:
        before = len(entries)
        entries = [e for e in entries if arg.lower() not in e.lower()]
        if len(entries) < before:
            MEMORIES_FILE.write_text("\n".join(entries) + "\n", encoding="utf-8")
            _memories_cache["text"] = None
            _memories_cache["ts"] = 0.0
            _memory_word_cache.clear()
            await update.message.reply_text(
                f"✓ Removed {before - len(entries)} entr(ies) matching '{arg}'."
            )
        else:
            await update.message.reply_text(f"No memories matched '{arg}'.")


async def recall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search facts and summaries for a keyword and show matches."""
    chat_id = update.effective_chat.id
    keyword = " ".join(context.args).strip().lower() if context.args else ""
    if not keyword:
        await update.message.reply_text("Usage: /recall <keyword>")
        return
    hits = []
    for f in (facts.get(chat_id) or []):
        if keyword in f.lower():
            hits.append(f"[fact] {f}")
    for f in (recent_facts.get(chat_id) or []):
        if keyword in f.lower():
            hits.append(f"[recent] {f}")
    summ = (summaries.get(chat_id) or "").strip()
    if summ and keyword in summ.lower():
        hits.append(f"[summary] {summ[:300]}{'…' if len(summ) > 300 else ''}")
    rsumm = (recent_summaries.get(chat_id) or "").strip()
    if rsumm and keyword in rsumm.lower():
        hits.append(f"[recent summary] {rsumm[:300]}{'…' if len(rsumm) > 300 else ''}")
    if hits:
        await update.message.reply_text(
            f"🔍 Found {len(hits)} match(es) for \"{keyword}\":\n\n" + "\n\n".join(hits)
        )
    else:
        await update.message.reply_text(f"Nothing found for \"{keyword}\".")


async def addpayment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = list(context.args or [])
    # Optional trailing cap like "x12" = 12 monthly payments left.
    count = None
    if args and re.fullmatch(r"[xX]\d+", args[-1]):
        count = int(args[-1][1:])
        args = args[:-1]
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: /addpayment <name> <amount> <day-of-month> [xN]\n"
            "Example: /addpayment Rent 800 5        (Rent, $800, the 5th, ongoing)\n"
            "Example: /addpayment Car 300 15 x12    (Car, $300, the 15th, 12 payments left)"
        )
        return
    name = " ".join(args[:-2])
    try:
        day = int(args[-1])
        if not 1 <= day <= 31:
            raise ValueError
    except ValueError:
        await update.message.reply_text("The day must be a number 1–31 (day of the month it's due).")
        return
    try:
        amount = float(args[-2].replace("$", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("The amount must be a number, e.g. 800 or 1250.50.")
        return
    if count is not None and count <= 0:
        await update.message.reply_text("The payment count (xN) must be 1 or more.")
        return

    record = {"name": name, "amount": amount, "recur": "monthly", "day": day}
    if count is not None:
        first = next_occurrence(day, _today())
        record["until"] = add_months(day, first, count - 1).isoformat()  # last payment date
    payments.append(record)
    save_payments()

    if count is not None:
        until = date.fromisoformat(record["until"])
        await update.message.reply_text(
            f"✅ Added: {name} — {_money(amount)} — the {day}{_ord(day)} of each month, "
            f"{count} payments left (through {until.strftime('%b %Y')})."
        )
    else:
        await update.message.reply_text(
            f"✅ Added: {name} — {_money(amount)} — due the {day}{_ord(day)} of each month."
        )


async def addevery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    usage = (
        "Usage: /addevery <name> <amount> <start YYYY-MM-DD> <interval-days> [count]\n"
        "Example: /addevery Loan 150 2026-06-12 14 4\n"
        "(Loan, $150, every 14 days from Jun 12, stops after 4 payments)"
    )
    # Anchor parsing on the date token so multi-word names work.
    date_idx = next((i for i, a in enumerate(args)
                     if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a)), None)
    if date_idx is None or date_idx < 2 or date_idx + 1 >= len(args):
        await update.message.reply_text(usage)
        return
    name = " ".join(args[:date_idx - 1])
    try:
        amount = float(args[date_idx - 1].replace("$", "").replace(",", ""))
        start = date.fromisoformat(args[date_idx])
        rest = args[date_idx + 1:]
        interval = int(rest[0])
        count = int(rest[1]) if len(rest) > 1 else None
        if interval <= 0 or (count is not None and count <= 0):
            raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_text(usage)
        return
    payments.append({
        "name": name, "amount": amount, "recur": "every",
        "start": start.isoformat(), "interval": interval, "count": count,
    })
    save_payments()
    cap = f", stops after {count} payments" if count else ""
    await update.message.reply_text(
        f"✅ Added: {name} — {_money(amount)} — every {interval} days from "
        f"{start.strftime('%b ')}{start.day}, {start.year}{cap}."
    )


async def list_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not payments:
        await update.message.reply_text(
            "No payments saved yet. Add one with:\n"
            "/addpayment <name> <amount> <day>   (monthly)\n"
            "/addevery <name> <amount> <start> <interval-days> [count]   (every N days)"
        )
        return
    today = _today()
    lines = []
    for i, p in enumerate(ordered_payments(), 1):
        occ = next_occurrence_p(p, today)
        if occ is None:
            nxt = "finished"
        else:
            nxt = "next: " + occ.strftime("%a %b ") + str(occ.day)
            left = payments_remaining(p, occ)
            if left is not None:
                nxt += f", {left} left"
        lines.append(f"{i}. {p['name']} — {_money(p['amount'])} — {describe_recur(p)} ({nxt})")
    await update.message.reply_text("💳 Your payments:\n\n" + "\n".join(lines))


async def delpayment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /delpayment <number from /payments, or name>")
        return
    arg = " ".join(context.args).strip()
    ordered = ordered_payments()
    target = None
    if arg.isdigit():
        idx = int(arg) - 1
        if 0 <= idx < len(ordered):
            target = ordered[idx]
    if target is None:
        for p in payments:
            if p["name"].lower() == arg.lower():
                target = p
                break
    if target is None:
        await update.message.reply_text("Couldn't find that one. Run /payments to see the list.")
        return
    payments.remove(target)
    save_payments()
    await update.message.reply_text(f"🗑️ Removed: {target['name']}")


EDIT_USAGE = (
    "Usage: /editpayment <number> <field> <value>\n"
    "Fields: name, amount, day (monthly), count (payments left; or 'none' to remove the cap), "
    "interval & start (for /addevery ones)\n\n"
    "Examples:\n"
    "/editpayment 6 amount 41.50\n"
    "/editpayment 6 day 14\n"
    "/editpayment 16 count 10\n"
    "/editpayment 16 count none"
)


async def editpayment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if len(args) < 3 or not args[0].isdigit():
        await update.message.reply_text(EDIT_USAGE)
        return
    ordered = ordered_payments()
    idx = int(args[0]) - 1
    if not 0 <= idx < len(ordered):
        await update.message.reply_text(f"No payment #{args[0]}. Run /payments to see the list.")
        return
    p = ordered[idx]
    field = args[1].lower()
    value = " ".join(args[2:]).strip()
    today = _today()
    recur = p.get("recur", "monthly")

    if field == "name":
        p["name"] = value
        note = f"renamed to “{value}”"
    elif field in ("amount", "amt"):
        try:
            p["amount"] = float(value.replace("$", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("Amount must be a number, e.g. 41.50.")
            return
        note = f"amount → {_money(p['amount'])}"
    elif field == "day":
        if recur != "monthly":
            await update.message.reply_text("'day' only applies to monthly payments (use 'start' for interval ones).")
            return
        try:
            d = int(value)
            if not 1 <= d <= 31:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Day must be a number 1–31.")
            return
        rem = payments_remaining(p, today)  # preserve remaining count if capped
        p["day"] = d
        if p.get("until") and rem:
            p["until"] = add_months(d, next_occurrence(d, today), rem - 1).isoformat()
        note = f"day → {d}{_ord(d)} of the month"
    elif field in ("count", "left"):
        if value.lower() in ("none", "off", "endless", "0", "∞"):
            p.pop("until", None)
            if recur == "every":
                p["count"] = None
            note = "cap removed (now ongoing)"
        else:
            try:
                n = int(value)
                if n <= 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("Count must be a positive number, or 'none' to remove the cap.")
                return
            if recur == "monthly":
                p["until"] = add_months(int(p["day"]), next_occurrence(int(p["day"]), today), n - 1).isoformat()
            else:
                start = date.fromisoformat(p["start"])
                interval = int(p["interval"])
                k = 0 if today <= start else ((today - start).days + interval - 1) // interval
                p["count"] = k + n
            note = f"{n} payments left"
    elif field in ("interval", "every"):
        if recur != "every":
            await update.message.reply_text("'interval' only applies to /addevery payments.")
            return
        try:
            iv = int(value)
            if iv <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Interval must be a positive number of days.")
            return
        p["interval"] = iv
        note = f"interval → every {iv} days"
    elif field == "start":
        if recur != "every":
            await update.message.reply_text("'start' only applies to /addevery payments.")
            return
        try:
            s = date.fromisoformat(value)
        except ValueError:
            await update.message.reply_text("Start must be a date like 2026-06-12.")
            return
        p["start"] = s.isoformat()
        note = f"start → {s.strftime('%b ')}{s.day}, {s.year}"
    else:
        await update.message.reply_text(EDIT_USAGE)
        return

    save_payments()
    occ = next_occurrence_p(p, today)
    nxt = "finished" if occ is None else "next: " + occ.strftime("%a %b ") + str(occ.day)
    msg = f"✏️ {p['name']}: {note}.\n   {_money(p['amount'])} — {describe_recur(p)} ({nxt})"
    if field in ("day", "start", "interval", "count"):  # these reorder the /payments list
        msg += "\n\n⚠️ This changed its due date, so the /payments numbering may have shifted — re-run /payments before your next edit."
    await update.message.reply_text(msg)


async def remind_payments_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uname = user_names.get(update.effective_chat.id) or (update.effective_user.first_name or "you")
    start, end = week_window()
    due = due_between(start, end)
    await update.message.reply_text(format_due(due, uname, start, end))


async def payments_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled daily; only acts on the configured weekday (default Thursday)."""
    owner = get_owner()
    if owner is None:
        return
    if _today().weekday() != REMINDER_WEEKDAY:
        return
    start, end = week_window()
    due = due_between(start, end)
    if not due:
        return  # quiet weeks stay quiet
    uname = user_names.get(owner, "you")
    await context.bot.send_message(chat_id=owner, text=format_due(due, uname, start, end))
    print(f"[payments] Reminder sent: {len(due)} due {start} → {end}.")


# --- Backup ---
async def _send_backup(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    sent = []
    for fname in ("payments.json", "state.json", "reminders.json"):
        path = BASE_DIR / fname
        if path.exists():
            with path.open("rb") as fh:
                await context.bot.send_document(chat_id=chat_id, document=fh, filename=fname)
            sent.append(fname)
    return sent


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sent = await _send_backup(context, update.effective_chat.id)
    if sent:
        await update.message.reply_text("💾 Backup sent: " + ", ".join(sent) +
                                        "\n(Save these — restore by copying them back into the bot folder.)")
    else:
        await update.message.reply_text("Nothing to back up yet.")


async def recap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Summarize recent conversation, including rolled-up history if available."""
    chat_id = update.effective_chat.id
    uname = user_names.get(chat_id, "you")
    hist = conversation_history.get(chat_id, [])
    rolling = (recent_summaries.get(chat_id) or "").strip()
    if not hist and not rolling:
        await update.message.reply_text("Nothing to recap yet.")
        return
    parts = []
    if rolling:
        parts.append(f"BACKGROUND (older conversation):\n{rolling}")
    if hist:
        recent = hist[-20:]
        convo = "\n".join(
            f"{(NAME if m['role'] == 'assistant' else uname)}: {m['content']}" for m in recent
        )
        parts.append(f"RECENT MESSAGES:\n{convo}")
    sys_msg = (
        f"Give a 2-3 sentence plain-text recap of the conversation between {NAME} and {uname} "
        f"based on the material below. Cover what they've talked about and any meaningful moments. "
        f"No headers, no bullets, no markdown."
    )
    raw = call_nanogpt(
        [{"role": "system", "content": sys_msg}, {"role": "user", "content": "\n\n".join(parts)}],
        model=MOOD_MODEL,
    )
    await update.message.reply_text(raw.strip() or "Nothing to recap.")


async def quiet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pause proactive messages for X hours (/quiet 3h) or cancel (/quiet off)."""
    chat_id = update.effective_chat.id
    arg = (context.args[0].strip().lower() if context.args else "").rstrip("h").strip()
    if arg in ("off", "cancel", "0", ""):
        if quiet_until.pop(chat_id, None):
            save_state()
            await update.message.reply_text("Proactive messages back on.")
        else:
            ts = quiet_until.get(chat_id)
            if ts and time.time() < ts:
                remaining = int((ts - time.time()) / 60)
                await update.message.reply_text(
                    f"Quiet mode active for ~{remaining} more min. Send /quiet off to cancel."
                )
            else:
                await update.message.reply_text(
                    "Quiet mode is off. Use /quiet <hours> (e.g. /quiet 3) to pause proactives."
                )
        return
    try:
        hours = float(arg)
        if hours <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Usage: /quiet <hours>  e.g. /quiet 3  |  /quiet off to cancel")
        return
    quiet_until[chat_id] = time.time() + hours * 3600
    save_state()
    await update.message.reply_text(f"Proactive messages paused for {hours:g}h. Send /quiet off to cancel early.")


async def life_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View or update the character's life arc (life.txt).
    /life          — show current content
    /life <text>   — replace with new arc description
    /life add <text> — append a line to the existing arc
    """
    args = context.args or []
    if not args:
        current = LIFE_ARC_FILE.read_text(encoding="utf-8").strip() if LIFE_ARC_FILE.exists() else "(empty)"
        await update.message.reply_text(
            f"Current life arc:\n{current}\n\n"
            f"Usage:\n/life <text> — replace\n/life add <text> — append"
        )
        return
    if args[0].lower() == "add":
        text = " ".join(args[1:]).strip()
        if not text:
            await update.message.reply_text("Usage: /life add <text>")
            return
        with LIFE_ARC_FILE.open("a", encoding="utf-8") as f:
            f.write(f"\n{text}")
        _life_arc_cache["text"] = None
        await update.message.reply_text(f"Added to life arc: {text}")
    else:
        text = " ".join(args).strip()
        LIFE_ARC_FILE.write_text(text, encoding="utf-8")
        _life_arc_cache["text"] = None
        await update.message.reply_text(f"Life arc updated: {text}")


def _context_file_cmd(file: "Path", cache: dict, label: str):
    """Return an (args, file, cache, label) handler body factory — shared logic for /people, /projects."""
    async def _cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args or []
        if not args:
            current = file.read_text(encoding="utf-8").strip() if file.exists() else "(empty)"
            await update.message.reply_text(
                f"*{label}:*\n{current}\n\n"
                f"/{label.lower()} <text> — replace\n/{label.lower()} add <text> — append",
                parse_mode="Markdown",
            )
            return
        if args[0].lower() == "add":
            text = " ".join(args[1:]).strip()
            if not text:
                await update.message.reply_text(f"Usage: /{label.lower()} add <text>")
                return
            with file.open("a", encoding="utf-8") as f:
                f.write(f"\n{text}")
            cache["text"] = None
            await update.message.reply_text(f"{label} updated (added): {text}")
        else:
            text = " ".join(args).strip()
            file.write_text(text, encoding="utf-8")
            cache["text"] = None
            await update.message.reply_text(f"{label} updated: {text}")
    return _cmd


people_cmd = _context_file_cmd(PEOPLE_FILE, _people_cache, "People")
projects_cmd = _context_file_cmd(PROJECTS_FILE, _projects_cache, "Projects")


async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View or edit schedule.txt from Telegram.
    /schedule          — show full schedule
    /schedule <text>   — replace entire schedule
    /schedule add <text> — append a line
    """
    args = context.args or []
    if not args:
        current = SCHEDULE_FILE.read_text(encoding="utf-8").strip() if SCHEDULE_FILE.exists() else "(empty)"
        await update.message.reply_text(
            f"*Schedule:*\n{current}\n\n"
            f"/schedule <text> — replace\n/schedule add <text> — append",
            parse_mode="Markdown",
        )
        return
    if args[0].lower() == "add":
        text = " ".join(args[1:]).strip()
        if not text:
            await update.message.reply_text("Usage: /schedule add <text>")
            return
        with SCHEDULE_FILE.open("a", encoding="utf-8") as f:
            f.write(f"\n{text}")
        await update.message.reply_text(f"Schedule updated (added): {text}")
    else:
        text = " ".join(args).strip()
        SCHEDULE_FILE.write_text(text, encoding="utf-8")
        await update.message.reply_text(f"Schedule updated.")


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Append a mid-day note to day.txt so the character picks it up in context."""
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        current = DAY_FILE.read_text(encoding="utf-8").strip() if DAY_FILE.exists() else "(empty)"
        await update.message.reply_text(f"Current day context:\n{current}\n\nUsage: /today <note>")
        return
    with DAY_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n{text}")
    _day_cache["text"] = None  # invalidate so next read picks it up
    await update.message.reply_text(f"Added to today's context: {text}")


async def note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually append a note about yourself to user_notes.txt."""
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        current = USER_NOTES_FILE.read_text(encoding="utf-8").strip() if USER_NOTES_FILE.exists() else "(empty)"
        await update.message.reply_text(f"Your notes:\n{current}\n\nUsage: /note <something you have going on>")
        return
    _append_user_note(text)
    _user_notes_cache["text"] = None  # invalidate cache
    await update.message.reply_text(f"Noted: {text}")


async def notes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View and manage user_notes.txt entries.
    /notes           — list numbered
    /notes del <n>   — delete entry n
    /notes clear     — wipe all
    """
    args = context.args or []
    existing = USER_NOTES_FILE.read_text(encoding="utf-8").strip() if USER_NOTES_FILE.exists() else ""
    lines = [l for l in existing.splitlines() if l.strip()]

    if not args:
        if not lines:
            await update.message.reply_text("No notes yet. Use /note <text> to add one.")
            return
        numbered = "\n".join(f"{i+1}. {l}" for i, l in enumerate(lines))
        await update.message.reply_text(
            f"*Your notes:*\n{numbered}\n\n/notes del <n> to remove one",
            parse_mode="Markdown",
        )
        return

    if args[0].lower() == "clear":
        USER_NOTES_FILE.write_text("", encoding="utf-8")
        _user_notes_cache["text"] = None
        await update.message.reply_text("Notes cleared.")
        return

    if args[0].lower() == "del":
        if len(args) < 2:
            await update.message.reply_text("Usage: /notes del <n>")
            return
        try:
            idx = int(args[1]) - 1
            if not (0 <= idx < len(lines)):
                raise ValueError
        except ValueError:
            await update.message.reply_text(f"Invalid number. You have {len(lines)} note(s).")
            return
        removed = lines.pop(idx)
        USER_NOTES_FILE.write_text("\n".join(lines), encoding="utf-8")
        _user_notes_cache["text"] = None
        await update.message.reply_text(f"Removed: {removed}")
        return

    await update.message.reply_text("Usage: /notes | /notes del <n> | /notes clear")


async def weekly_backup(context: ContextTypes.DEFAULT_TYPE):
    owner = get_owner()
    if owner is None or _today().weekday() != BACKUP_WEEKDAY:
        return
    sent = await _send_backup(context, owner)
    if sent:
        await context.bot.send_message(chat_id=owner, text="💾 Weekly backup: " + ", ".join(sent))
        print(f"[backup] Weekly backup sent: {sent}")


# --- One-off and daily reminders ---
async def fire_reminder(context: ContextTypes.DEFAULT_TYPE):
    rid = context.job.data
    r = next((x for x in reminders if x["id"] == rid), None)
    if not r:
        return  # was cancelled
    await context.bot.send_message(chat_id=r["chat_id"], text=f"⏰ Reminder: {r['text']}")
    if not r.get("daily"):
        if r in reminders:
            reminders.remove(r)
            save_reminders()


def schedule_reminder(job_queue, r: dict):
    if r.get("daily"):
        h, m = [int(x) for x in r["due"].split(":")]
        t = dtime(h, m, tzinfo=TZ) if TZ else dtime(h, m)
        job_queue.run_daily(fire_reminder, time=t, data=r["id"])
        return
    due = datetime.fromisoformat(r["due"])
    now = datetime.now(TZ) if TZ else datetime.now()
    # If the bot was down when it was due, deliver shortly after startup instead of dropping it.
    when = due if due > now else now + timedelta(seconds=5)
    job_queue.run_once(fire_reminder, when=when, data=r["id"])


async def remindme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    due, text = parse_when(context.args or [])
    if due is None or not text:
        await update.message.reply_text(
            "Usage: /remindme <when> <message>\n"
            "When can be:\n"
            "• 30m / 2h / 3d  (in N minutes/hours/days)\n"
            "• 18:30          (today, or tomorrow if it's passed)\n"
            "• tomorrow 9:00\n"
            "• 2026-07-01 14:30\n\n"
            "Example: /remindme 2h take the chicken out"
        )
        return
    rid = _new_reminder_id()
    r = {"id": rid, "chat_id": update.effective_chat.id, "due": due.isoformat(), "text": text}
    reminders.append(r)
    save_reminders()
    schedule_reminder(context.job_queue, r)
    await update.message.reply_text(f"⏰ Got it — I'll remind you {fmt_due_dt(due)}: {text}")


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mine = sorted([r for r in reminders if r["chat_id"] == update.effective_chat.id],
                  key=lambda r: r["due"])
    if not mine:
        await update.message.reply_text("No reminders set. Add one with /remindme <when> <message>.")
        return
    lines = [f"{i}. {fmt_due_dt(datetime.fromisoformat(r['due']))} — {r['text']}  (id {r['id']})"
             for i, r in enumerate(mine, 1)]
    await update.message.reply_text("⏰ Your reminders:\n\n" + "\n".join(lines))


async def delreminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /delreminder <number from /reminders, or id>")
        return
    arg = context.args[0]
    mine = sorted([r for r in reminders if r["chat_id"] == update.effective_chat.id],
                  key=lambda r: r["due"])
    target = None
    if arg.isdigit():
        n = int(arg)
        target = next((r for r in mine if r["id"] == n), None)  # by id
        if target is None and 1 <= n <= len(mine):
            target = mine[n - 1]  # by position
    if target is None:
        await update.message.reply_text("Couldn't find that reminder. Run /reminders to see them.")
        return
    reminders.remove(target)
    save_reminders()
    await update.message.reply_text(f"🗑️ Cancelled: {target['text']}")


async def setreminder_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /setreminder HH:MM message\n"
            "Example: /setreminder 08:30 take meds\n\n"
            "Sets a reminder that fires every day at that time.\n"
            "Use /reminders to list and /delreminder to cancel."
        )
        return
    try:
        h, m = [int(x) for x in args[0].split(":")]
        assert 0 <= h < 24 and 0 <= m < 60
    except Exception:
        await update.message.reply_text("Time must be HH:MM (e.g. 08:30 or 14:00)")
        return
    text = " ".join(args[1:])
    rid = _new_reminder_id()
    r = {"id": rid, "chat_id": update.effective_chat.id,
         "due": f"{h:02d}:{m:02d}", "text": text, "daily": True}
    reminders.append(r)
    save_reminders()
    schedule_reminder(context.job_queue, r)
    await update.message.reply_text(f"⏰ Got it — I'll remind you daily at {h:02d}:{m:02d}: {text}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not _is_allowed(update.effective_user.id):
        return
    if not _rate_ok(update.effective_user.id):
        return
    user_names[chat_id] = update.effective_user.first_name or "you"
    gap_hours = (time.time() - last_seen.get(chat_id, time.time())) / 3600
    nudge_mood(chat_id, gap_hours)
    last_seen[chat_id] = time.time()
    if get_owner() is None:
        set_owner(chat_id)
        save_state()

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()
        resp = _session.post(
            f"{NANOGPT_BASE_URL}/audio/transcriptions",
            headers={"Authorization": f"Bearer {NANOGPT_API_KEY}"},
            files={"file": ("voice.ogg", bytes(voice_bytes), "audio/ogg")},
            data={"model": WHISPER_MODEL},
            timeout=60,
        )
        resp.raise_for_status()
        transcript = resp.json().get("text", "").strip()
    except Exception as e:
        log.warning("Voice transcription failed: %s", e)
        await context.bot.send_message(chat_id=chat_id,
                                       text="[couldn't make out that voice note]")
        return

    if not transcript:
        return

    try:
        content = f"[voice message]: {transcript}"
        messages = assemble_messages(chat_id, content)
        ai_response = await reply_with_typing(context, chat_id, messages, fallback=FALLBACK_MODEL)
        ai_response = await maybe_search(context, chat_id, messages, ai_response, user_names[chat_id])
        await _deliver(update, context, chat_id, transcript, ai_response)
        # Log a note about the voice message so it's preserved in memory
        ts = datetime.now(tz=TZ).strftime("%b %d")
        snippet = transcript[:150] + ("…" if len(transcript) > 150 else "")
        voice_fact = f"[{ts}] Voice note: \"{snippet}\""
        rfts = recent_facts.setdefault(chat_id, [])
        rfts.append(voice_fact)
        if len(rfts) > RECENT_FACTS_MAX:
            rfts.pop(0)
        save_state()
    except Exception as e:
        log.error("Voice handler error: %s", e)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Something went wrong: {e}")


async def _run_ffmpeg(*args: str) -> tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return await proc.communicate()


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not _is_allowed(update.effective_user.id):
        return
    if not _rate_ok(update.effective_user.id):
        return
    user_names[chat_id] = update.effective_user.first_name or "you"
    gap_hours = (time.time() - last_seen.get(chat_id, time.time())) / 3600
    nudge_mood(chat_id, gap_hours)
    last_seen[chat_id] = time.time()
    if get_owner() is None:
        set_owner(chat_id)
        save_state()

    video = update.message.video or update.message.video_note
    if not video:
        return

    if video.file_size and video.file_size > VIDEO_MAX_SIZE_MB * 1024 * 1024:
        await context.bot.send_message(chat_id=chat_id,
            text=f"[video's too big — max {VIDEO_MAX_SIZE_MB}MB]")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    caption = (getattr(update.message, "caption", None) or "").strip()

    frame_data_url = None
    transcript = None

    try:
        tg_file = await context.bot.get_file(video.file_id)
        video_bytes = bytes(await tg_file.download_as_bytearray())

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "video.mp4")
            frame_path = os.path.join(tmpdir, "frame.jpg")
            audio_path = os.path.join(tmpdir, "audio.ogg")

            with open(video_path, "wb") as f:
                f.write(video_bytes)

            # Extract frame and audio in parallel
            frame_res, audio_res = await asyncio.gather(
                _run_ffmpeg("-y", "-i", video_path, "-ss", "00:00:01",
                            "-vframes", "1", "-f", "image2", frame_path),
                _run_ffmpeg("-y", "-i", video_path, "-vn", "-acodec",
                            "libopus", audio_path),
                return_exceptions=True,
            )

            if not isinstance(frame_res, Exception) and os.path.exists(frame_path):
                with open(frame_path, "rb") as f:
                    frame_data_url = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
            else:
                log.warning("Video frame extraction failed: %s", frame_res)

            if not isinstance(audio_res, Exception) and os.path.exists(audio_path):
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()
                try:
                    resp = _session.post(
                        f"{NANOGPT_BASE_URL}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {NANOGPT_API_KEY}"},
                        files={"file": ("audio.ogg", audio_bytes, "audio/ogg")},
                        data={"model": WHISPER_MODEL},
                        timeout=60,
                    )
                    resp.raise_for_status()
                    transcript = resp.json().get("text", "").strip() or None
                except Exception as e:
                    log.warning("Video transcription failed: %s", e)
            else:
                log.warning("Video audio extraction failed: %s", audio_res)

    except Exception as e:
        log.error("Video processing error: %s", e)
        await context.bot.send_message(chat_id=chat_id,
            text=f"❌ Couldn't process that video: {e}")
        return

    if not frame_data_url and not transcript:
        await context.bot.send_message(chat_id=chat_id, text="[couldn't read that video]")
        return

    uname = user_names[chat_id]
    parts = []
    if caption:
        parts.append(caption)
    if transcript:
        parts.append(f"[audio transcript: {transcript}]")
    if not parts:
        parts.append(f"{uname} just sent you a video. React to it in character.")
    prompt = " ".join(parts)
    user_mem = f"[sent a video] {caption} {transcript or ''}".strip()

    try:
        await ensure_weather()
        model = VISION_MODEL if frame_data_url else NANOGPT_MODEL
        fallback = VISION_FALLBACK if frame_data_url else FALLBACK_MODEL
        messages = assemble_messages(chat_id, prompt, image_data_url=frame_data_url)
        ai_response = await reply_with_typing(context, chat_id, messages,
                                              model=model, fallback=fallback)
        ai_response = await maybe_search(context, chat_id, messages, ai_response, uname,
                                         model=model, fallback=fallback)
        await _deliver(update, context, chat_id, user_mem, ai_response)
    except Exception as e:
        log.error("Video handler reply error: %s", e)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Something went wrong: {e}")


PDF_MAX_SIZE_MB = int(os.getenv("PDF_MAX_SIZE_MB", "20"))
PDF_MAX_CHARS = int(os.getenv("PDF_MAX_CHARS", "16000"))
PDF_OCR_MAX_PAGES = int(os.getenv("PDF_OCR_MAX_PAGES", "4"))


async def _pdf_ocr_fallback(context, update, chat_id: int, raw_bytes: bytes,
                            fname: str, caption: str, uname: str) -> None:
    """Render image-only PDF pages via mutool and pass to the vision model."""
    import glob, shutil, subprocess, tempfile
    home = os.path.expanduser("~")
    tmp_dir = tempfile.mkdtemp(dir=home, prefix="bot_pdf_")
    try:
        pdf_path = os.path.join(tmp_dir, "input.pdf")
        with open(pdf_path, "wb") as f:
            f.write(raw_bytes)
        out_pattern = os.path.join(tmp_dir, "page-%d.png")
        proc = await asyncio.to_thread(
            subprocess.run,
            ["mutool", "draw", "-o", out_pattern, "-r", "150", pdf_path],
            capture_output=True, timeout=60,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace")[:200]
            raise RuntimeError(f"mutool failed: {err}")
        pages = sorted(glob.glob(os.path.join(tmp_dir, "page-*.png")))[:PDF_OCR_MAX_PAGES]
        if not pages:
            raise RuntimeError("mutool produced no pages")
        page_data_urls = []
        for p in pages:
            with open(p, "rb") as f:
                page_data_urls.append("data:image/png;base64," + base64.b64encode(f.read()).decode())

        # Step 1: extract text via vision model — clear extraction task, no character voice
        extract_content: list = [{"type": "text", "text":
            f"Transcribe all text content from these {len(pages)} scanned document page(s). "
            f"Ignore any app watermarks, scanner logos, or branding. "
            f"Output only the document text, formatted clearly."}]
        for data_url in page_data_urls:
            extract_content.append({"type": "image_url", "image_url": {"url": data_url}})
        extract_msgs = [
            {"role": "system", "content": "You are a document text extractor. Transcribe all visible text from the provided images, ignoring watermarks and logos."},
            {"role": "user", "content": extract_content},
        ]
        extracted_text = await asyncio.to_thread(call_nanogpt, extract_msgs, VISION_MODEL)
        if not extracted_text.strip():
            raise RuntimeError("vision model couldn't read any content from the pages")
        _WATERMARK_NAMES = ("camscanner", "adobe scan", "microsoft lens", "genius scan", "tiny scanner")
        if len(extracted_text.strip()) < 80 or any(w in extracted_text.lower() for w in _WATERMARK_NAMES):
            raise RuntimeError("only got a scanner watermark — no document content visible")

        # Step 2: character responds to extracted text via DOCUMENT_MODEL (same path as text PDFs)
        lead = caption or f"I sent you a PDF — {fname}. Take a look."
        user_prompt = f"{lead}\n\n[PDF contents]\n{extracted_text}"
        user_mem = f"[sent PDF (image-only): {fname}] {caption}".strip()
        await ensure_weather()
        messages = assemble_messages(chat_id, user_prompt)
        ai_response = await reply_with_typing(context, chat_id, messages, model=DOCUMENT_MODEL)
        ai_response = await maybe_search(context, chat_id, messages, ai_response, uname,
                                         model=DOCUMENT_MODEL)
        await _deliver(update, context, chat_id, user_mem, ai_response)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _extract_pdf_text(raw_bytes: bytes) -> str:
    """Extract plain text from a PDF using pypdf. Returns empty string on failure."""
    try:
        from pypdf import PdfReader
        from io import BytesIO
        reader = PdfReader(BytesIO(raw_bytes))
        pages = []
        for page in reader.pages:
            t = (page.extract_text() or "").strip()
            if t:
                pages.append(t)
        return "\n\n".join(pages)
    except ImportError:
        return ""  # pypdf not installed; OCR fallback will handle it
    except Exception as e:
        raise RuntimeError(f"PDF read failed: {e}")


def _format_json_for_prompt(data: dict, fname: str) -> str:
    """Return a readable text block describing a JSON file."""
    if data.get("spec") in ("chara_card_v2", "chara_card_v3"):
        card = data.get("data", data)
        name = card.get("name", "Unknown")
        parts = [f"CHARACTER CARD: {name}"]
        for field, label in (
            ("description", "Description"),
            ("personality", "Personality"),
            ("scenario", "Scenario"),
            ("system_prompt", "System prompt"),
            ("first_mes", "First message"),
            ("mes_example", "Example dialogue"),
            ("post_history_instructions", "Post-history instructions"),
            ("creator_notes", "Creator notes"),
        ):
            val = (card.get(field) or "").strip()
            if val:
                parts.append(f"\n{label}:\n{val}")
        tags = card.get("tags") or []
        if tags:
            parts.append(f"\nTags: {', '.join(tags)}")
        return "\n".join(parts)

    # Generic JSON: pretty-print with truncation
    text = json.dumps(data, indent=2, ensure_ascii=False)
    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... truncated at {max_chars} chars]"
    return f"[JSON file: {fname}]\n{text}"


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    doc = update.message.document
    fname = (doc.file_name or "") if doc else ""
    log.info("Document received: %s (mime: %s)", fname, getattr(doc, "mime_type", "?"))

    is_pdf  = fname.lower().endswith(".pdf") or getattr(doc, "mime_type", "") == "application/pdf"
    is_json = fname.lower().endswith(".json")

    if not is_pdf and not is_json:
        return  # unsupported file type — let it fall through silently

    if not _is_allowed(update.effective_user.id):
        return
    if not _rate_ok(update.effective_user.id):
        return
    user_names[chat_id] = update.effective_user.first_name or "you"
    gap_hours = (time.time() - last_seen.get(chat_id, time.time())) / 3600
    nudge_mood(chat_id, gap_hours)
    last_seen[chat_id] = time.time()
    if get_owner() is None:
        set_owner(chat_id)
        save_state()
    if not doc:
        return

    caption = (getattr(update.message, "caption", None) or "").strip()
    uname = user_names[chat_id]

    # --- PDF branch ---
    if is_pdf:
        if not fname:
            fname = "document.pdf"
        size_limit = PDF_MAX_SIZE_MB * 1024 * 1024
        if doc.file_size and doc.file_size > size_limit:
            await context.bot.send_message(chat_id=chat_id,
                text=f"[that PDF is too big — max {PDF_MAX_SIZE_MB} MB]")
            return
        key = (chat_id, doc.file_unique_id)
        if key in _pdf_in_flight:
            await context.bot.send_message(chat_id=chat_id,
                text="[already working on that PDF — give me a sec]")
            return
        _pdf_in_flight.add(key)
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            try:
                tg_file = await context.bot.get_file(doc.file_id)
                raw_bytes = bytes(await tg_file.download_as_bytearray())
                pdf_text = await asyncio.to_thread(_extract_pdf_text, raw_bytes)
            except Exception as e:
                log.error("PDF download/read error: %s", e)
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Couldn't read that PDF: {e}")
                return
            if not pdf_text.strip():
                try:
                    await _pdf_ocr_fallback(context, update, chat_id, raw_bytes, fname, caption, uname)
                except FileNotFoundError:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="[image-only PDF — install mupdf-tools to enable vision fallback: pkg install mupdf-tools]",
                    )
                except Exception as e:
                    log.error("PDF OCR fallback failed: %s", e)
                    await context.bot.send_message(
                        chat_id=chat_id, text=f"[couldn't read that PDF as an image either: {e}]",
                    )
                return
            if len(pdf_text) > PDF_MAX_CHARS:
                pdf_text = pdf_text[:PDF_MAX_CHARS] + f"\n\n[... truncated at {PDF_MAX_CHARS} chars]"
            lead = caption or f"I sent you a PDF — {fname}. Take a look."
            user_prompt = f"{lead}\n\n[PDF contents]\n{pdf_text}"
            user_mem = f"[sent PDF: {fname}] {caption}".strip()
            try:
                await ensure_weather()
                messages = assemble_messages(chat_id, user_prompt)
                ai_response = await reply_with_typing(context, chat_id, messages, model=DOCUMENT_MODEL)
                ai_response = await maybe_search(context, chat_id, messages, ai_response, uname,
                                                 model=DOCUMENT_MODEL)
                await _deliver(update, context, chat_id, user_mem, ai_response)
            except Exception as e:
                log.error("PDF handler reply error: %s", e)
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Something went wrong: {e}")
        finally:
            _pdf_in_flight.discard(key)
        return

    # --- JSON branch ---
    if doc.file_size and doc.file_size > DOCUMENT_MAX_SIZE_MB * 1024 * 1024:
        await context.bot.send_message(chat_id=chat_id,
            text=f"[file's too big — max {DOCUMENT_MAX_SIZE_MB}MB for JSON]")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    if not fname:
        fname = "file.json"

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        raw_bytes = bytes(await tg_file.download_as_bytearray())
        data = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as e:
        await context.bot.send_message(chat_id=chat_id,
            text=f"[couldn't parse that JSON: {e}]")
        return
    except Exception as e:
        log.error("Document download error: %s", e)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Couldn't read that file: {e}")
        return

    formatted = _format_json_for_prompt(data, fname)

    is_card = data.get("spec") in ("chara_card_v2", "chara_card_v3")
    if is_card:
        card_name = (data.get("data") or data).get("name", "unknown")
        lead = (
            f"Here's {card_name}'s character card. Read it and give me your honest take — "
            f"what's working, what's weak, what you'd change. "
            f"Don't ask me what the problem is. Just tell me what you see."
        )
    else:
        lead = f"Here's a JSON file — {fname}. Take a look."
    if caption:
        lead = caption

    user_prompt = f"{lead}\n\n{formatted}"
    user_mem = user_prompt

    try:
        await ensure_weather()
        messages = assemble_messages(chat_id, user_prompt)
        ai_response = await reply_with_typing(context, chat_id, messages, model=DOCUMENT_MODEL)
        ai_response = await maybe_search(context, chat_id, messages, ai_response, uname,
                                         model=DOCUMENT_MODEL)
        await _deliver(update, context, chat_id, user_mem, ai_response)
    except Exception as e:
        log.error("Document handler reply error: %s", e)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Something went wrong: {e}")


async def check_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    headers = {"Authorization": f"Bearer {NANOGPT_API_KEY}"}
    response = _session.get(
        "https://nano-gpt.com/api/subscription/v1/usage",
        headers=headers,
        timeout=30,
    )
    data = response.json()
    if not data.get("active"):
        await update.message.reply_text("⚠️ No active subscription found.")
        return
    daily = data["daily"]
    monthly = data["monthly"]
    limits = data["limits"]
    msg = (
        f"📊 *NanoGPT Subscription Usage*\n\n"
        f"📅 *Daily:* {daily['used']} / {limits['daily']} used "
        f"({daily['remaining']} remaining)\n"
        f"📆 *Monthly:* {monthly['used']} / {limits['monthly']} used "
        f"({monthly['remaining']} remaining)\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def _deliver(update, context, chat_id, user_memory_text, ai_response):
    """Shared tail for text and photo handlers: tags, reaction, bubbles, selfie, memory."""
    if _looks_like_refusal(ai_response):
        # Provider moderation returned its refusal as the reply text. Never show it to
        # the user; still remember their message so the next turn keeps context.
        print(f"[reply] provider refused generation; suppressing refusal for chat {chat_id}.")
        remember(chat_id, "user", user_memory_text)
        save_state()
        return False
    clean, reaction, selfie_hint = extract_tags(ai_response)
    if clean:
        clean = _strip_slop(clean)
    placeholder = clean or (
        "[sent a selfie]" if selfie_hint is not None else
        (f"[reacted {reaction}]" if reaction else "")
    )
    remember(chat_id, "user", user_memory_text)
    remember(chat_id, "assistant", placeholder)
    save_state()  # single write for both history appends

    reacted = False
    if reaction and reaction in ALLOWED_REACTIONS:
        try:
            await update.message.set_reaction(reaction)
            reacted = True
        except Exception as e:
            print("[react] failed:", e)
    if clean:
        await send_bubbles(context, chat_id, clean, pre_delay=_typing_delay_secs(clean))
        if voice_reply.get(chat_id) and random.random() < TTS_CHANCE:
            asyncio.create_task(_send_voice_reply(context, chat_id, clean))
    if selfie_hint is not None:
        await send_selfie(context, chat_id, selfie_hint, announce_errors=True)
    if clean:
        q = _extract_last_question(clean)
        if q and len(q) > 12:
            buf = _recent_questions.setdefault(chat_id, [])
            buf.append(q)
            if len(buf) > QUESTION_MEMORY_SIZE:
                buf.pop(0)
    asyncio.create_task(maintain_memory(chat_id))  # background, doesn't delay reply
    asyncio.create_task(update_mood(chat_id))      # background mood appraisal
    if user_memory_text and not user_memory_text.startswith("[sent "):
        asyncio.create_task(update_user_notes(chat_id, user_memory_text))
        asyncio.create_task(update_memories(chat_id, user_memory_text, clean))
    if FOLLOWUP_ENABLED and clean and context.job_queue and active_vibe(chat_id) != "in-person" and _FOLLOWUP_RE.search(clean):
        existing = _pending_followup.pop(chat_id, None)
        if existing:
            try:
                existing.schedule_removal()
            except Exception:
                pass
        delay = random.uniform(FOLLOWUP_MIN, FOLLOWUP_MAX)
        _pending_followup[chat_id] = context.job_queue.run_once(_send_followup, when=delay, data=chat_id)
        print(f"[followup] scheduled in {delay:.0f}s for chat {chat_id}")
    return reacted


def _fetch_reddit(url: str) -> str:
    # Plain scraping hits Reddit's JS verification wall regardless of headers,
    # so go through the official OAuth API (oauth.reddit.com).
    if not (REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET):
        raise RuntimeError("Reddit link reading needs REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET")
    headers = {
        "User-Agent": REDDIT_USER_AGENT,
        "Authorization": f"Bearer {_reddit_access_token()}",
    }
    path = urlparse(url).path  # e.g. /r/NecroMerger/s/UFZMQRrTYT
    # Resolve share-link redirects (/s/<id>) to the real post path via the API host.
    resolved = _session.get("https://oauth.reddit.com" + path, headers=headers,
                            timeout=LINK_FETCH_TIMEOUT, allow_redirects=True)
    base = "https://oauth.reddit.com" + urlparse(resolved.url).path.rstrip("/")
    if not base.endswith(".json"):
        base += "/.json"
    resp = _session.get(base, headers=headers, timeout=LINK_FETCH_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    post = data[0]["data"]["children"][0]["data"]
    sub = post.get("subreddit_name_prefixed") or ("r/" + post.get("subreddit", ""))
    parts = [f'Reddit post in {sub} — "{post.get("title", "")}" '
             f'(score {post.get("score", "?")}, {post.get("num_comments", "?")} comments)']
    body = (post.get("selftext") or "").strip()
    if body:
        parts.append(body)
    comments = []
    if len(data) > 1:
        for c in data[1]["data"]["children"]:
            cd = c.get("data", {})
            cb = (cd.get("body") or "").strip()
            if cb and cd.get("author") != "AutoModerator":
                comments.append(f"- ({cd.get('score', '?')}) {cb}")
            if len(comments) >= 4:
                break
    if comments:
        parts.append("Top comments:\n" + "\n".join(comments))
    return "\n\n".join(parts)


def _fetch_generic(url: str) -> str:
    html = _session.get(url, headers={"User-Agent": _HTTP_UA},
                        timeout=LINK_FETCH_TIMEOUT).text
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    text = re.sub(r"(?is)<(script|style|nav|header|footer|aside|form|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return (f"Title: {title}\n\n" if title else "") + text


def web_search(query: str) -> str:
    """Quick text-only web search (DuckDuckGo HTML, no API key needed)."""
    try:
        r = _session.post(
            "https://html.duckduckgo.com/html/", data={"q": query},
            headers={"User-Agent": _SEARCH_UA}, timeout=LINK_FETCH_TIMEOUT,
        )
        r.raise_for_status()
        page = r.text
    except Exception as e:
        print("[search] failed:", e)
        return "(search failed — couldn't reach the search engine)"

    def clean(s):
        return _html_module.unescape(re.sub(r"<[^>]+>", "", s)).strip()

    titles = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                         page, re.DOTALL)
    snippets = re.findall(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', page, re.DOTALL)

    results = []
    for i, (href, title) in enumerate(titles[:SEARCH_RESULTS]):
        url = href
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            url = unquote(qs.get("uddg", [href])[0])
        snippet = clean(snippets[i]) if i < len(snippets) else ""
        line = f"- {clean(title)} ({url})"
        if snippet:
            line += f": {snippet}"
        results.append(line)
    return "\n".join(results) if results else "(no results found)"


def fetch_link(url: str):
    """Fetch readable content for a URL (Reddit via its JSON API, else a crude HTML strip)."""
    try:
        if "reddit.com" in url or "redd.it" in url:
            content = _fetch_reddit(url)
        else:
            content = _fetch_generic(url)
        content = content.strip()
        return content[:LINK_MAX_CHARS] if content else None
    except Exception as e:
        print("[link] fetch failed:", e)
        return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not _is_allowed(update.effective_user.id):
        return
    if not _rate_ok(update.effective_user.id):
        return
    user_message = update.message.text
    gap_hours = (time.time() - last_seen.get(chat_id, time.time())) / 3600
    nudge_mood(chat_id, gap_hours)
    last_seen[chat_id] = time.time()
    user_names[chat_id] = update.effective_user.first_name or "you"
    if get_owner() is None:  # any interaction claims the heartbeat owner, not just /start
        set_owner(chat_id)
        save_state()

    # Cancel any pending follow-up — user replied before it fired
    existing = _pending_followup.pop(chat_id, None)
    if existing:
        try:
            existing.schedule_removal()
        except Exception:
            pass

    try:
        await ensure_weather()
        content_for_model = user_message

        # If the user is quote-replying to one of our messages via Telegram's reply UI,
        # inject the quoted text explicitly — especially important for heartbeat messages
        # that may have been compressed out of the verbatim history window.
        replied_to = getattr(update.message, "reply_to_message", None)
        if replied_to and getattr(replied_to.from_user, "is_bot", False):
            quoted = (replied_to.text or replied_to.caption or "").strip()
            if quoted and len(quoted) > 5:
                recent = conversation_history.get(chat_id, [])[-6:]
                in_recent = any(quoted[:80] in (m.get("content") or "") for m in recent)
                if not in_recent:
                    content_for_model = (
                        f'[replying to your message: "{quoted[:250]}"]\n{user_message}'
                    )

        if LINK_READING:
            link = _URL_RE.search(user_message)
            if link:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                fetched = await asyncio.to_thread(fetch_link, link.group(0))
                if fetched:
                    content_for_model = (content_for_model + "\n\n[Content of the link they shared — "
                                         "read it and react in character:\n" + fetched + "\n]")
                else:
                    content_for_model = content_for_model + "\n\n[You tried to open that link but couldn't.]"

        # Gap-aware opener: when user returns after a long absence, note it this turn only.
        if gap_hours > GAP_AWARE_HOURS:
            gap_str = (f"{round(gap_hours)}h" if gap_hours < 48 else f"{round(gap_hours / 24)}d")
            content_for_model += (
                f"\n[Note: it's been about {gap_str} since you two last talked. "
                f"If it fits, acknowledge the gap naturally — brief, not a big deal.]"
            )

        # Lull detection: track consecutive terse replies and nudge a course-change.
        if _is_terse(user_message):
            _terse_count[chat_id] = _terse_count.get(chat_id, 0) + 1
        else:
            _terse_count[chat_id] = 0
        if _terse_count.get(chat_id, 0) >= LULL_THRESHOLD:
            _terse_count[chat_id] = 0
            content_for_model += (
                "\n[Note: they've been giving short responses for a few messages. "
                "Try shifting gears — bring up something new, check in on how they're doing, "
                "or let the conversation breathe. Don't push harder on the current thread.]"
            )

        messages = assemble_messages(chat_id, content_for_model)
        if INNER_VOICE_ENABLED:
            inner_voice = await generate_inner_voice(chat_id, user_message, user_names[chat_id])
            if inner_voice:
                messages.append({"role": "system", "content": (
                    f"# {NAME}'s private thought — not shown to {user_names[chat_id]}\n{inner_voice.strip()}"
                )})
        ai_response = await reply_with_typing(context, chat_id, messages, fallback=FALLBACK_MODEL)
        ai_response = await maybe_search(context, chat_id, messages, ai_response, user_names[chat_id])
        reacted = await _deliver(update, context, chat_id, user_message, ai_response)
        if REACTIONS_AUTO and not reacted:  # she didn't emit a tag — decide one cheaply
            asyncio.create_task(maybe_auto_react(update, user_message))
    except requests.exceptions.HTTPError as e:
        await update.message.reply_text(
            f"⚠️ API Error: {e.response.status_code} — {e.response.text}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Something went wrong: {str(e)}")


async def _log_photo_memory(chat_id: int, data_url: str, caption: str):
    """Background task: describe a received photo in one sentence and add it to recent_facts."""
    try:
        desc_prompt = (
            "In one concise sentence, describe what you see in this photo — the people, "
            "setting, mood, or notable details. Just describe what's there, no interpretation."
        )
        messages = [{"role": "user", "content": [
            {"type": "text", "text": desc_prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}]
        desc = await asyncio.to_thread(_one_call, messages, VISION_MODEL)
        desc = _strip_thinking(desc).strip().strip('"')
        if desc:
            ts = datetime.now(tz=TZ).strftime("%b %d")
            fact = f"[{ts}] Photo received: {desc}"
            if caption:
                fact += f' (caption: "{caption}")'
            rfts = recent_facts.setdefault(chat_id, [])
            rfts.append(fact)
            if len(rfts) > RECENT_FACTS_MAX:
                rfts.pop(0)
            save_state()
            print(f"[photo-memory] {fact[:100]}")
    except Exception as e:
        print("[photo-memory] failed:", e)


async def _send_followup(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: follow up after the bot said 'hold on / brb / give me a sec'."""
    chat_id = context.job.data
    _pending_followup.pop(chat_id, None)
    uname = user_names.get(chat_id, "you")
    trigger = (
        f"[SYSTEM: A minute or two ago you told {uname} to hold on or that you'd be right back. "
        f"Follow up now — whatever you were checking or doing, come back to it naturally and "
        f"briefly, the way you'd pick up your phone after stepping away. "
        f"Don't repeat phrases like 'hold on' or apologize for the wait unless it feels right.]"
    )
    try:
        await send_triggered(context, chat_id, trigger)
    except Exception as e:
        print(f"[followup] error for chat {chat_id}:", e)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not _is_allowed(update.effective_user.id):
        return
    gap_hours = (time.time() - last_seen.get(chat_id, time.time())) / 3600
    nudge_mood(chat_id, gap_hours)
    last_seen[chat_id] = time.time()
    user_names[chat_id] = update.effective_user.first_name or "you"
    if get_owner() is None:
        set_owner(chat_id)
        save_state()
    caption = (update.message.caption or "").strip()

    try:
        photo = update.message.photo[-1]  # largest size
        tg_file = await photo.get_file()
        raw = bytes(await tg_file.download_as_bytearray())
        data_url = "data:image/jpeg;base64," + base64.b64encode(raw).decode()

        uname = user_names[chat_id]
        loc_ctx = ""
        loc = user_location.get(chat_id)
        if loc and (time.time() - loc["ts"]) < 4 * 3600:
            place = await asyncio.to_thread(_reverse_geocode_sync, loc["lat"], loc["lon"])
            if place:
                loc_ctx = f" They're near {place} ({loc['lat']:.4f}, {loc['lon']:.4f})."
        prompt = caption or f"{uname} just sent you this photo.{loc_ctx} React to it in character."
        await ensure_weather()
        messages = assemble_messages(chat_id, prompt, image_data_url=data_url)
        ai_response = await reply_with_typing(context, chat_id, messages,
                                              model=VISION_MODEL, fallback=VISION_FALLBACK)
        ai_response = await maybe_search(context, chat_id, messages, ai_response, uname,
                                         model=VISION_MODEL, fallback=VISION_FALLBACK)

        user_mem = f"[sent a photo] {caption}".strip()
        await _deliver(update, context, chat_id, user_mem, ai_response)
        asyncio.create_task(_log_photo_memory(chat_id, data_url, caption))
        if selfie_ready() and random.random() < PHOTO_SELFIE_CHANCE:
            await send_selfie(context, chat_id, "", announce_errors=False)
    except requests.exceptions.HTTPError as e:
        await send_bubbles(context, chat_id,
            f"⚠️ Vision API Error: {e.response.status_code} — {e.response.text[:200]}")
    except Exception as e:
        await send_bubbles(context, chat_id, f"❌ Couldn't look at that one: {str(e)}")


async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """React in character to a sticker the user sent."""
    chat_id = update.effective_chat.id
    if not _is_allowed(update.effective_user.id):
        return
    gap_hours = (time.time() - last_seen.get(chat_id, time.time())) / 3600
    nudge_mood(chat_id, gap_hours)
    last_seen[chat_id] = time.time()
    user_names[chat_id] = update.effective_user.first_name or "you"
    if get_owner() is None:
        set_owner(chat_id)
        save_state()
    sticker = update.message.sticker
    emoji = sticker.emoji or ""
    name = sticker.set_name or ""
    desc = emoji
    if name:
        desc = f"{emoji} (sticker from set: {name})" if emoji else f"sticker from set: {name}"
    uname = user_names[chat_id]
    prompt = (
        f"[{uname} sent you a sticker: {desc}. "
        f"React naturally in character — a brief, genuine response to the sticker's vibe. "
        f"No need to describe the sticker; just respond to what it expresses.]"
    )
    try:
        await ensure_weather()
        messages = assemble_messages(chat_id, prompt)
        ai_response = await reply_with_typing(context, chat_id, messages, fallback=FALLBACK_MODEL)
        user_mem = f"[sent a sticker: {desc}]"
        reacted = await _deliver(update, context, chat_id, user_mem, ai_response)
        if REACTIONS_AUTO and not reacted:
            asyncio.create_task(maybe_auto_react(update, emoji or "sticker"))
    except Exception as e:
        print(f"[sticker] error:", e)


# --- Proactive heartbeat ---
PROACTIVE_INSTRUCTION = (
    "[SYSTEM: {name} has been quiet for a while. Reach out to {user} first, unprompted, "
    "with a short, natural, fully in-character message — a check-in, a passing thought, "
    "a small specific thing that just happened in your day (work, the city, the weather, "
    "something you read), or a continuation of your last conversation. 1-3 sentences. "
    "Do not mention that this "
    "message is automated.]"
)

# Occasionally nudge a proactive message toward checking local news first, so that ambient
# detail stays current without a dedicated news API integration. (Weather is now fetched
# directly via ensure_weather(), so it's already available without a search.)
PROACTIVE_AMBIENT_HINT = (
    " Before replying, use [search: {location} news today] and let whatever you find "
    "casually color what you say — don't report it like a headline roundup."
)
PROACTIVE_AMBIENT_CHANCE = 0.25

# Occasionally have her attach a selfie to a proactive message -- the model almost never
# reaches for [selfie:] on its own when reaching out first, so nudge it explicitly.
PROACTIVE_SELFIE_HINT = (
    " Include a [selfie: ...] tag with this message -- a quick, casual pic of whatever "
    "you're doing or wherever you are right now."
)
PROACTIVE_SELFIE_CHANCE = 0.15
# After she reacts to a photo the user sends, chance she fires back a selfie of her own.
PHOTO_SELFIE_CHANCE = float(os.getenv("PHOTO_SELFIE_CHANCE", "0.20"))

# Auto follow-up: when the bot says "hold on / brb / give me a sec" etc., schedule a
# brief follow-up message after a short delay, as if she actually went and came back.
# Disabled by default — set FOLLOWUP_ENABLED=true in .env to turn on.
FOLLOWUP_ENABLED = os.getenv("FOLLOWUP_ENABLED", "false").lower() == "true"
_FOLLOWUP_RE = re.compile(
    r"\b(hold on|hold up|brb|be right back"
    r"|give me a (sec|second|minute|min)"
    r"|wait a (sec|second|minute|min)"
    r"|gimme a (sec|second|minute)|just a (sec|second|minute)"
    r"|back in a (sec|second|minute|bit)"
    r"|give me a moment|one moment)\b",
    re.IGNORECASE,
)
FOLLOWUP_MIN = float(os.getenv("FOLLOWUP_MIN_SECS", "45"))
FOLLOWUP_MAX = float(os.getenv("FOLLOWUP_MAX_SECS", "120"))
_pending_followup: dict = {}  # chat_id -> scheduled job object (cancel if user replies first)

# Selfie scene deduplication — avoids repeating the same scenario in back-to-back selfies.
SELFIE_DEDUP_SIZE = int(os.getenv("SELFIE_DEDUP_SIZE", "6"))
_recent_selfie_hints: dict = {}  # chat_id -> list of recent scene descriptions

# Proactive hook dedup — avoids repeating the same pattern in back-to-back heartbeats.
PROACTIVE_HOOK_DEDUP_SIZE = int(os.getenv("PROACTIVE_HOOK_DEDUP_SIZE", "8"))
_recent_proactive_hooks: dict = {}  # chat_id -> list of recent hook sentences

# Question memory — tracks questions the bot has asked recently; avoids repeating them.
QUESTION_MEMORY_SIZE = int(os.getenv("QUESTION_MEMORY_SIZE", "8"))
_recent_questions: dict = {}  # chat_id -> list of recent questions

_QUESTION_RE = re.compile(r"[^.!?…]*\?")  # quick sentence-level question extractor


def _extract_last_question(text: str) -> str:
    matches = _QUESTION_RE.findall(text)
    return matches[-1].strip() if matches else ""

# Lull detection: consecutive terse replies trigger a gentle approach shift.
_terse_count: dict = {}  # chat_id -> int
LULL_THRESHOLD = int(os.getenv("LULL_THRESHOLD", "3"))

def _is_terse(text: str) -> bool:
    return len(text.strip()) <= 15

# Gap-aware opener: when user returns after a long absence, note it in that turn's context.
GAP_AWARE_HOURS = float(os.getenv("GAP_AWARE_HOURS", "12"))


async def send_triggered(context: ContextTypes.DEFAULT_TYPE, chat_id: int, trigger: str):
    """Generate and deliver an unprompted message from a [SYSTEM: ...] trigger (no user message to react to)."""
    uname = user_names.get(chat_id, "you")
    await ensure_weather()
    messages = assemble_messages(chat_id, trigger)
    text = await reply_with_typing(context, chat_id, messages, fallback=FALLBACK_MODEL)
    text = await maybe_search(context, chat_id, messages, text, uname)
    if _looks_like_refusal(text):
        # Provider moderation refused this generation — skip the tick entirely rather
        # than deliver the raw refusal or poison history with it.
        _log_refusal_debug("message", NANOGPT_MODEL, messages, text)  # TEMP DEBUG
        print(f"[proactive] provider refused generation; skipping tick for chat {chat_id}.")
        return ""
    clean, _reaction, selfie_hint = extract_tags(text)
    # Store a synthetic user entry so conversation history maintains proper user/assistant
    # alternation. Without it, two consecutive assistant turns confuse some models when
    # the user replies and the history is dumped into the next request.
    remember(chat_id, "user", f"[you reached out to {uname} first — no incoming message]")
    remember(chat_id, "assistant", clean or ("[sent a selfie]" if selfie_hint is not None else ""))
    save_state()
    if clean:
        await send_bubbles(context, chat_id, clean)
    if selfie_hint is not None:
        await send_selfie(context, chat_id, selfie_hint, announce_errors=False)
    asyncio.create_task(maintain_memory(chat_id))
    asyncio.create_task(update_mood(chat_id))  # her own message can set her mood (e.g. got doored)
    return text


def _todays_memory_note(chat_id: int) -> str:
    """Check if today matches a notable stored date (birthday, anniversary, milestone first)."""
    today = datetime.now(tz=TZ) if TZ else datetime.now()
    # Match "Jun 22", "june 22", "6/22", "06/22" style patterns
    fmt_long = today.strftime("%b %d").lower()       # "jun 22"
    fmt_slash = f"{today.month}/{today.day}"         # "6/22"
    fmt_slash0 = today.strftime("%m/%d")             # "06/22"
    date_tokens = {fmt_long, fmt_slash, fmt_slash0}
    recurring_keywords = {"birthday", "anniversary", "born", "together", "first", "met"}

    hits = []
    for f in (facts.get(chat_id) or []) + (recent_facts.get(chat_id) or []):
        fl = f.lower()
        if any(tok in fl for tok in date_tokens):
            if any(k in fl for k in recurring_keywords):
                hits.append(f.strip())
    for m in (milestones.get(chat_id) or []):
        ms_dt = datetime.fromtimestamp(m["ts"], tz=TZ) if TZ else datetime.fromtimestamp(m["ts"])
        if ms_dt.month == today.month and ms_dt.day == today.day and ms_dt.year != today.year:
            hits.append(f"today is the anniversary of: {m['text']}")

    if hits:
        return " Important: today is a significant date — " + "; ".join(hits[:3]) + ". Reference it naturally if you reach out."
    return ""


def _generate_proactive_hook(chat_id: int, uname: str) -> str:
    """Sync: one-sentence seed of what the character has on her mind right now.
    Draws on life arc, weather, user notes, and recent conversation."""
    parts = []
    life_arc = _read_life_arc()
    if life_arc:
        parts.append(f"{NAME}'s life right now: {life_arc[:300]}")
    weather = (_weather_cache.get("text") or "").strip()
    if weather:
        parts.append(f"Current weather: {weather}")
    unotes = _read_user_notes()
    if unotes:
        parts.append(f"Things going on with {uname}: {unotes[:200]}")
    recent = conversation_history.get(chat_id, [])[-4:]
    if recent:
        snippet = " / ".join(
            f"{'her' if m['role'] == 'assistant' else uname}: {m['content'][:80].strip()}"
            for m in recent
        )
        parts.append(f"Last exchange: {snippet}")
    if not parts:
        return ""
    recent_hooks = (_recent_proactive_hooks.get(chat_id) or [])[-PROACTIVE_HOOK_DEDUP_SIZE:]
    avoid = ""
    if recent_hooks:
        avoid = (
            f"\n\nAvoid repeating the mood, topic, or type of hook from these recent ones:\n"
            + "\n".join(f"- {h}" for h in recent_hooks)
        )
    sys_msg = (
        f"You are helping {NAME} decide what to text {uname}. "
        f"Based on the context below, write ONE short sentence (10-20 words) describing "
        f"something specific that is genuinely on {NAME}'s mind right now — "
        f"could be a passing thought, something she noticed, a memory, something annoying her, "
        f"something she's curious about, a thing from her day, or nothing in particular. "
        f"Vary the register — not every message is a check-in or an observation about the city. "
        f"Be concrete and specific to who she is. No filler. No quotes around the sentence."
        + avoid
    )
    try:
        result = call_nanogpt(
            [{"role": "system", "content": sys_msg},
             {"role": "user", "content": "\n".join(parts)}],
            model=MOOD_MODEL,
        ).strip()
        if _looks_like_refusal(result):  # TEMP DEBUG
            _log_refusal_debug("hook", MOOD_MODEL,
                               [{"role": "system", "content": sys_msg},
                                {"role": "user", "content": "\n".join(parts)}], result)
        if result:
            buf = _recent_proactive_hooks.setdefault(chat_id, [])
            buf.append(result)
            if len(buf) > PROACTIVE_HOOK_DEDUP_SIZE:
                buf.pop(0)
        return result
    except Exception:
        return ""


async def send_proactive(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    uname = user_names.get(chat_id, "you")
    trigger = PROACTIVE_INSTRUCTION.format(name=NAME, user=uname)
    hook = await asyncio.to_thread(_generate_proactive_hook, chat_id, uname)
    if hook:
        trigger = trigger[:-1] + f" Something specific on her mind right now: {hook}]"
    # Inject the last exchange so the model can actually reference what was last discussed,
    # rather than defaulting to a generic check-in.
    recent = conversation_history.get(chat_id, [])[-4:]
    if recent:
        snippet = " / ".join(
            f"{'you' if m['role'] == 'assistant' else uname}: {m['content'][:100].strip()}"
            for m in recent
        )
        trigger = trigger[:-1] + (
            f" Last exchange for context (use it naturally if it fits, don't recap it): {snippet}]"
        )
    # Inject a note if today is a special date stored in memory
    date_note = _todays_memory_note(chat_id)
    if date_note:
        trigger = trigger[:-1] + date_note + "]"
    sched_today = _read_schedule_today()
    if sched_today:
        trigger = trigger[:-1] + (
            f" What she's got going on today: {sched_today[:200]}."
            f" If something from it fits the reach-out naturally, draw on it.]"
        )
    reads = _read_reading()
    if reads:
        trigger = trigger[:-1] + (
            " Something she read recently and has a take on (work it in naturally in her voice"
            " only if it fits, don't force it; if she brings it up she can drop the link): "
            + reads[-1] + "]"
        )
    if SEARCH_ENABLED and random.random() < PROACTIVE_AMBIENT_CHANCE:
        trigger = trigger[:-1] + PROACTIVE_AMBIENT_HINT.format(location=WEATHER_LOCATION) + "]"
    elif selfie_ready() and random.random() < PROACTIVE_SELFIE_CHANCE:
        trigger = trigger[:-1] + PROACTIVE_SELFIE_HINT + "]"
    # 40% chance to weave in an unsent draft from a previous blocked tick
    if random.random() < 0.4:
        draft = _pop_draft(chat_id)
        if draft:
            hours_ago = max(1, round((time.time() - draft["ts"]) / 3600))
            trigger = trigger[:-1] + (
                f" Side note: about {hours_ago}h ago you had the urge to reach out but held "
                f"back ({draft['reason']}). If it fits, mention it in passing — the way "
                f"you'd say 'I almost texted you earlier.' Don't make a thing of it.]"
            )
    return await send_triggered(context, chat_id, trigger)


# --- Recurring tasks ("cron jobs") ---
CRON_INSTRUCTION = (
    "[SYSTEM: scheduled task — {instruction}. Do this now (look things up if it helps) and "
    "tell {user} about it in a short, natural, fully in-character message, 1-3 sentences. "
    "Do not mention that this is automated or scheduled.]"
)


def schedule_cron_job(job_queue, job: dict):
    sch = job["schedule"]
    name = f"cron_{job['id']}"
    if sch["type"] == "daily":
        t = dtime(sch["hour"], sch["minute"], tzinfo=TZ) if TZ else dtime(sch["hour"], sch["minute"])
        job_queue.run_daily(run_cron_job, time=t, data=job["id"], name=name, chat_id=job["chat_id"])
    else:
        job_queue.run_repeating(run_cron_job, interval=sch["seconds"], first=sch["seconds"],
                                data=job["id"], name=name, chat_id=job["chat_id"])


async def run_cron_job(context: ContextTypes.DEFAULT_TYPE):
    job_id = context.job.data
    job = next((j for j in cron_jobs if j["id"] == job_id), None)
    if not job:
        return
    uname = user_names.get(job["chat_id"], "you")
    trigger = CRON_INSTRUCTION.format(instruction=job["instruction"], user=uname)
    try:
        await send_triggered(context, job["chat_id"], trigger)
        print(f"[cron #{job_id}] Ran: {job['instruction']}")
    except Exception as e:
        print(f"[cron #{job_id}] Error:", e)


async def cron_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args or []
    if len(args) < 3 or args[0].lower() not in ("daily", "every"):
        await update.message.reply_text(
            "Usage: /cron <schedule> <what to do>\n"
            "Schedule is \"daily HH:MM\" or \"every Nh\"/\"every Nm\".\n\n"
            "Example: /cron daily 08:00 check the news and tell me something interesting"
        )
        return
    schedule = parse_cron_schedule(" ".join(args[:2]))
    instruction = " ".join(args[2:]).strip()
    if not schedule or not instruction:
        await update.message.reply_text("Couldn't parse that. Try: /cron daily 08:00 <what to do>")
        return
    job = {"id": _new_cron_id(), "chat_id": chat_id, "schedule": schedule, "instruction": instruction}
    cron_jobs.append(job)
    save_cron_jobs()
    if context.job_queue is not None:
        schedule_cron_job(context.job_queue, job)
    await update.message.reply_text(
        f"⏰ Scheduled (#{job['id']}, {describe_cron_schedule(schedule)}): {instruction}"
    )


async def cron_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jobs = [j for j in cron_jobs if j["chat_id"] == chat_id]
    if not jobs:
        await update.message.reply_text("No scheduled tasks. Add one with /cron.")
        return
    lines = [f"#{j['id']} ({describe_cron_schedule(j['schedule'])}): {j['instruction']}" for j in jobs]
    await update.message.reply_text("⏰ Scheduled tasks:\n" + "\n".join(lines))


async def cron_del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: /crondel <id> (see /crons for ids)")
        return
    job_id = int(args[0])
    job = next((j for j in cron_jobs if j["id"] == job_id and j["chat_id"] == chat_id), None)
    if not job:
        await update.message.reply_text("No scheduled task with that ID.")
        return
    cron_jobs.remove(job)
    save_cron_jobs()
    if context.job_queue is not None:
        for jb in context.job_queue.get_jobs_by_name(f"cron_{job_id}"):
            jb.schedule_removal()
    await update.message.reply_text(f"🗑️ Removed #{job_id}.")


def schedule_next_heartbeat(job_queue):
    delay = random.uniform(HEARTBEAT_MIN, HEARTBEAT_MAX)
    job_queue.run_once(heartbeat, when=delay)
    print(f"[heartbeat] next check in {delay / 3600:.1f}h.")


async def heartbeat(context: ContextTypes.DEFAULT_TYPE):
    schedule_next_heartbeat(context.job_queue)  # re-roll the next random time, always
    owner = get_owner()
    if owner is None:
        print("[heartbeat] No owner yet — send /start to the bot first.")
        return
    if time.time() - last_seen.get(owner, 0) < HEARTBEAT_MIN * 0.9:
        print("[heartbeat] Owner recently active; skipping this tick.")
        return
    if in_quiet_hours():
        _save_draft(owner, "wanted to check in but it was quiet hours")
        print("[heartbeat] Quiet hours; saved draft.")
        return
    if _is_quiet(owner):
        print("[heartbeat] User /quiet active; skipping.")
        return
    if not _check_nudge_budget(owner):
        _save_draft(owner, "had something to say but hit the daily nudge limit")
        print("[heartbeat] Nudge budget exhausted; saved draft.")
        return
    s = mood_now(owner)
    skip_chance = 0.6 if s <= -1.2 else 0.25 if s <= -0.4 else 0.0
    if skip_chance and random.random() < skip_chance:
        _save_draft(owner, "wasn't quite feeling up to reaching out")
        print(f"[heartbeat] Mood is low ({s:+.1f}); saved draft.")
        return
    try:
        await send_proactive(context, owner)
        _consume_nudge(owner)
        print("[heartbeat] Proactive message sent.")
    except Exception as e:
        print("[heartbeat] Error:", e)


async def selfie_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_names[chat_id] = update.effective_user.first_name or "you"
    hint = " ".join(context.args).strip() if context.args else ""
    await ensure_weather()  # so the selfie reflects the current weather
    await send_selfie(context, chat_id, hint, announce_errors=True)


async def heartbeat_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_names[chat_id] = update.effective_user.first_name or "you"
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        await send_proactive(context, chat_id)
    except Exception as e:
        await update.message.reply_text(f"❌ Heartbeat failed: {str(e)}")


def _overnight_mood_reset(chat_id: int):
    """Nightly: gently drift negative moods toward neutral — sleep softens a bad day."""
    s = mood_now(chat_id)
    if s >= 0:
        return  # positive moods don't need nudging
    m = moods.get(chat_id) or {}
    m["score"] = round(s * 0.45, 3)  # pull roughly halfway toward 0
    m.pop("label", None)  # stale label — let the next exchange set a fresh one
    m.pop("_gap_hours", None)
    moods[chat_id] = m
    save_state()
    print(f"[mood] overnight reset: {s:+.2f} -> {m['score']:+.2f} for chat {chat_id}")


async def reading_job(context: ContextTypes.DEFAULT_TYPE):
    if READING_ENABLED:
        await update_reading()


async def nightly_maintenance(context: ContextTypes.DEFAULT_TYPE):
    # Nightly: long-term memory promotion, milestone detection, overnight mood reset.
    owner = get_owner()
    if owner is None:
        return
    try:
        await maintain_long_term_memory(owner)
    except Exception as e:
        print("[memory] long-term promotion error:", e)
    try:
        await update_milestones(owner)
    except Exception as e:
        print("[milestones] detection error:", e)
    _overnight_mood_reset(owner)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick dashboard: mood, outfit, today's context, and time since last message."""
    chat_id = update.effective_chat.id
    lines = [f"*{NAME} — status*", ""]

    label = mood_label(chat_id)
    s = mood_now(chat_id)
    filled = max(0, round((s + 3) / 6 * 10))
    bar = "█" * filled + "░" * (10 - filled)
    mood_str = f"{label}  " if label else ""
    lines.append(f"*Mood:* {mood_str}[{bar}]  {s:+.1f}")

    outfit = wardrobe.get("current")
    if outfit:
        lines.append(f"*Wearing:* {outfit}")

    life_arc = _read_life_arc()
    if life_arc:
        snippet = life_arc[:150] + ("…" if len(life_arc) > 150 else "")
        lines.append(f"*Life arc:* {snippet}")

    day_ctx = _read_day_context()
    if day_ctx:
        snippet = day_ctx[:150] + ("…" if len(day_ctx) > 150 else "")
        lines.append(f"*Today:* {snippet}")

    unotes = _read_user_notes()
    if unotes:
        snippet = unotes[:150] + ("…" if len(unotes) > 150 else "")
        lines.append(f"*About you:* {snippet}")

    weather = (_weather_cache.get("text") or "").strip()
    if weather:
        lines.append(f"*Weather:* {weather}")

    qt = quiet_until.get(chat_id)
    if qt and time.time() < qt:
        remaining = int((qt - time.time()) / 60)
        lines.append(f"*Quiet mode:* {remaining}m remaining")

    last = last_seen.get(chat_id, 0)
    if last:
        gap = time.time() - last
        if gap < 120:
            gap_str = "just now"
        elif gap < 3600:
            gap_str = f"{round(gap / 60)}m ago"
        elif gap < 86400:
            gap_str = f"{round(gap / 3600)}h ago"
        else:
            gap_str = f"{round(gap / 86400)}d ago"
        lines.append(f"*Last chat:* {gap_str}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _generate_daily_events(owner: int):
    """Generate 2-3 small life events for the day using the character's people, projects,
    and schedule as seeds. Writes the result to day.txt so it's ready when she texts."""
    try:
        people = _read_people()
        projects = _read_projects()
        schedule_today = _read_schedule_today()
        await ensure_weather()
        weather = (_weather_cache.get("text") or "").strip()

        ctx_parts = []
        if schedule_today:
            ctx_parts.append(f"Her schedule today: {schedule_today}")
        if weather:
            ctx_parts.append(f"Weather: {weather}")
        if projects:
            ctx_parts.append(f"Ongoing things in her life:\n{projects}")
        if people:
            ctx_parts.append(f"People in her life:\n{people}")

        ctx_block = "\n\n".join(ctx_parts)
        prompt = (
            f"Write 2-3 small, specific things that happen to {NAME} today. "
            f"Think ordinary texture of a real day — not dramatic, just the kind of mundane "
            f"or mildly interesting thing that actually happens to a person. "
            f"Each one: 1-2 sentences, written as a terse personal note (not a diary entry). "
            f"Reference her actual people and projects naturally when they fit — don't force them."
            + (f"\n\n{ctx_block}" if ctx_block else "")
            + "\n\nWrite only the events, no headers, bullets, or numbering."
        )
        msgs = [
            {"role": "system", "content": fill(SYSTEM_PROMPT_RAW, NAME, "")},
            {"role": "user", "content": prompt},
        ]
        events = await asyncio.to_thread(_one_call, msgs, SUMMARY_MODEL)
        events = _strip_thinking(events).strip()
        if events:
            DAY_FILE.write_text(events, encoding="utf-8")
            _day_cache["text"] = events
            _day_cache["ts"] = time.time()
            print(f"[day-events] {NAME}: {events[:100]}…")
    except Exception as e:
        print(f"[day-events] failed: {e}")


async def _rotate_day_context(context: ContextTypes.DEFAULT_TYPE):
    """Midnight job: archive today's day.txt to memory + a dated file, then generate
    tomorrow's events so she starts the new day with a populated context."""
    day_ctx = _read_day_context()
    owner = get_owner()
    yesterday = (datetime.now(tz=TZ) if TZ else datetime.now()) - timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")
    if day_ctx:
        # Archive to a dated file so the day isn't lost
        archive = BASE_DIR / f"day_{date_str}.txt"
        try:
            archive.write_text(day_ctx, encoding="utf-8")
        except Exception as e:
            print(f"[day-rotate] archive failed: {e}")
        # Save a compact memory fact so it persists through summarization
        if owner is not None:
            fact = f"[{yesterday.strftime('%b %d')}] {day_ctx[:300]}"
            rfts = recent_facts.setdefault(owner, [])
            rfts.append(fact)
            if len(rfts) > RECENT_FACTS_MAX:
                rfts.pop(0)
            save_state()
        print(f"[day-rotate] archived {date_str}: {day_ctx[:80]}…")
    # Generate fresh events for the new day (writes to day.txt, clears cache implicitly)
    if owner is not None:
        await _generate_daily_events(owner)
    else:
        # No owner yet — just clear the file
        try:
            DAY_FILE.write_text("", encoding="utf-8")
        except Exception:
            pass
        _day_cache["text"] = ""
        _day_cache["ts"] = time.time()


# --- Reverse geocoding (OSM Nominatim — free, no key required) ---

def _reverse_geocode_sync(lat: float, lon: float) -> str:
    """Return a region name for coordinates, or '' on failure. Call via asyncio.to_thread."""
    try:
        url = (f"https://nominatim.openstreetmap.org/reverse"
               f"?lat={lat}&lon={lon}&format=json&zoom=10")
        r = _session.get(url, headers={"User-Agent": "SillyTavernBot/1.0"}, timeout=5)
        r.raise_for_status()
        addr = r.json().get("address", {})
        parts = [p for p in [
            addr.get("county") or addr.get("city"),
            addr.get("state"),
        ] if p]
        return ", ".join(parts)
    except Exception:
        return ""


# --- WSDOT Traffic integration ---

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in miles between two lat/lon points."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _fetch_wsdot_alerts() -> list:
    try:
        r = _session.get(_WSDOT_ALERTS_URL, params={"AccessCode": WSDOT_API_KEY}, timeout=(10, 30))
        r.raise_for_status()
        return r.json().get("Alerts") or []
    except Exception as e:
        log.warning("[traffic] alerts fetch failed: %s", e)
        return []


def _fetch_wsdot_times() -> list:
    try:
        r = _session.get(_WSDOT_TIMES_URL, params={"AccessCode": WSDOT_API_KEY}, timeout=(10, 30))
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning("[traffic] travel times fetch failed: %s", e)
        return []


def _alert_loc(alert: dict):
    loc = alert.get("StartRoadwayLocation") or {}
    return loc.get("Latitude"), loc.get("Longitude")


def _filter_nearby(alerts: list, lat: float, lon: float, radius: float) -> list:
    out = []
    for a in alerts:
        alat, alon = _alert_loc(a)
        if alat is not None and alon is not None and _haversine(lat, lon, alat, alon) <= radius:
            out.append(a)
    return out


def _format_alert(a: dict) -> str:
    loc = a.get("StartRoadwayLocation") or {}
    headline = a.get("HeadlineDescription") or "Incident"
    desc = loc.get("Description", "")
    priority = a.get("Priority", "")
    icon = {"Low": "🟡", "Medium": "🟠", "High": "🔴"}.get(priority, "⚠️")
    return f"{icon} {headline}" + (f"\n   📍 {desc}" if desc else "")


def _congestion_icon(current, average) -> str:
    if not average:
        return "⚪"
    r = current / average
    if r >= 1.5:
        return "🔴"
    if r >= 1.2:
        return "🟠"
    if r >= 1.05:
        return "🟡"
    return "🟢"


def _format_travel_times(times: list, lat=None, lon=None) -> str:
    if lat is not None:
        # Include routes whose start or end is within 3x the alert radius of the user
        radius = TRAFFIC_RADIUS_MILES * 3
        times = [
            t for t in times
            if any(
                (p.get("Latitude") is not None and
                 _haversine(lat, lon, p["Latitude"], p["Longitude"]) <= radius)
                for p in [t.get("StartPoint") or {}, t.get("EndPoint") or {}]
            )
        ] or times[:10]
    else:
        times = times[:12]

    lines = []
    for t in times:
        name = t.get("Name", "Unknown route")
        current = t.get("CurrentTime")
        average = t.get("AverageTime")
        if current is None:
            continue
        icon = _congestion_icon(current, average)
        delay = f" (+{current - average} min)" if average and current > average else ""
        lines.append(f"{icon} {name}: {current} min{delay}")
    return "\n".join(lines) if lines else "No travel time data available."


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store the user's location (static or live); for traffic-enabled bots, acknowledge it."""
    chat_id = update.effective_chat.id
    loc = (update.message or update.edited_message).location

    live_until = None
    if loc.live_period:
        live_until = time.time() + loc.live_period

    user_location[chat_id] = {
        "lat": loc.latitude,
        "lon": loc.longitude,
        "ts": time.time(),
        "live_until": live_until,
    }
    save_state()

    if TRAFFIC_ENABLED and update.message:  # only reply on the initial share, not every live update
        if loc.live_period:
            await update.message.reply_text(
                "📍 Got your live location. I'll keep an eye on traffic around you "
                "and give you a heads-up if anything pops up nearby."
            )
        else:
            await update.message.reply_text(
                "📍 Got it. Use /traffic or /incidents to check what's around there."
            )


async def traffic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TRAFFIC_ENABLED:
        await update.message.reply_text("Traffic monitoring isn't set up (WSDOT_API_KEY missing).")
        return
    chat_id = update.effective_chat.id
    loc = user_location.get(chat_id)
    times = await asyncio.to_thread(_fetch_wsdot_times)
    if loc:
        header = f"🚗 Traffic near you (within {TRAFFIC_RADIUS_MILES:.0f} mi)"
        body = _format_travel_times(times, lat=loc["lat"], lon=loc["lon"])
    else:
        header = "🚗 Western Washington traffic"
        body = _format_travel_times(times)
    await update.message.reply_text(f"{header}\n\n{body}")


async def incidents_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TRAFFIC_ENABLED:
        await update.message.reply_text("Traffic monitoring isn't set up (WSDOT_API_KEY missing).")
        return
    chat_id = update.effective_chat.id
    alerts = await asyncio.to_thread(_fetch_wsdot_alerts)
    open_alerts = [a for a in alerts if (a.get("EventStatus") or "").lower() == "open"]

    loc = user_location.get(chat_id)
    if loc:
        to_show = _filter_nearby(open_alerts, loc["lat"], loc["lon"], TRAFFIC_RADIUS_MILES)
        header = f"⚠️ Incidents within {TRAFFIC_RADIUS_MILES:.0f} mi of you"
        footer = ""
    else:
        to_show = open_alerts[:15]
        header = "⚠️ Western Washington incidents"
        footer = "\n\nShare your location to see incidents near you."

    if not to_show:
        await update.message.reply_text(f"{header}\n\nNo active incidents.{footer}")
        return
    lines = [_format_alert(a) for a in to_show[:15]]
    await update.message.reply_text(f"{header}\n\n" + "\n\n".join(lines))


async def traffic_poll_job(context: ContextTypes.DEFAULT_TYPE):
    """Runs every TRAFFIC_POLL_MINUTES — sends proactive alert for new nearby incidents."""
    if not TRAFFIC_ENABLED:
        return
    alerts = await asyncio.to_thread(_fetch_wsdot_alerts)
    open_alerts = [a for a in alerts if (a.get("EventStatus") or "").lower() == "open"]

    for chat_id, loc in list(user_location.items()):
        live_until = loc.get("live_until")
        if not live_until or time.time() > live_until:
            continue  # only proactive alerts when live location is active

        nearby = _filter_nearby(open_alerts, loc["lat"], loc["lon"], TRAFFIC_RADIUS_MILES)
        known = seen_incidents.get(chat_id, set())
        new = [a for a in nearby if str(a.get("AlertID", "")) not in known]
        if not new:
            continue

        seen_incidents.setdefault(chat_id, set()).update(str(a["AlertID"]) for a in new)
        lines = [_format_alert(a) for a in new[:5]]
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ New incident(s) near you:\n\n" + "\n\n".join(lines),
            )
        except Exception as e:
            log.warning("[traffic] alert send failed for %s: %s", chat_id, e)


# --- Main ---
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Keep transient network blips from spamming the log or stopping the bot."""
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        print(f"[net] transient: {err.__class__.__name__}: {err}")  # one quiet line
        return
    import traceback
    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    print("[error] " + tb)
    # Surface the error to the user so button failures aren't silent
    try:
        if update and hasattr(update, "callback_query") and update.callback_query:
            await update.callback_query.message.reply_text(f"❌ {type(err).__name__}: {err}")
        elif update and hasattr(update, "effective_chat") and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text=f"❌ {type(err).__name__}: {err}"
            )
    except Exception:
        pass


def _acquire_termux_wake_lock():
    import shutil, subprocess
    if shutil.which("termux-wake-lock"):
        try:
            subprocess.run(["termux-wake-lock"], check=True, timeout=5)
            log.info("Termux wake lock acquired.")
        except Exception as e:
            log.warning("Could not acquire Termux wake lock: %s", e)


_BASE_COMMANDS = [
    BotCommand("help", "Show all commands"),
    BotCommand("start", "Reset and restart"),
    BotCommand("clear", "Wipe conversation history"),
    BotCommand("menu", "Open the inline button menu"),
    BotCommand("status", "Quick status: mood, outfit, today's context"),
    BotCommand("memory", "View what I remember"),
    BotCommand("remember", "Save a fact"),
    BotCommand("forget", "Wipe all memory (or /forget <keyword> to remove matching facts)"),
    BotCommand("addmem", "Add an NPC/world memory note"),
    BotCommand("mems", "List NPC/world memory notes"),
    BotCommand("delmem", "Remove a memory note (keyword or number)"),
    BotCommand("recall", "Search memory for a keyword"),
    BotCommand("exportmemory", "Export full memory as text"),
    BotCommand("milestones", "View relationship milestones"),
    BotCommand("reading", "See what she's read lately"),
    BotCommand("readnow", "Fetch a fresh reading now"),
    BotCommand("pin", "Pin something I always carry"),
    BotCommand("pinned", "List pinned memories"),
    BotCommand("unpin", "Remove a pinned memory"),
    BotCommand("boundary", "Add a soft boundary note"),
    BotCommand("boundaries", "List boundaries"),
    BotCommand("mood", "Check her current mood"),
    BotCommand("vibe", "Set a timed vibe (cozy/flirty/serious…)"),
    BotCommand("vent", "Toggle vent mode (listening only)"),
    BotCommand("energy", "Set your energy level (high/low/crash)"),
    BotCommand("selfie", "Generate a selfie"),
    BotCommand("wardrobe", "List outfits"),
    BotCommand("addoutfit", "Add an outfit"),
    BotCommand("outfit", "Set current outfit"),
    BotCommand("deloutfit", "Remove an outfit"),
    BotCommand("remindme", "One-off reminder (30m, 2h, 18:30…)"),
    BotCommand("setreminder", "Daily recurring reminder"),
    BotCommand("reminders", "List reminders"),
    BotCommand("delreminder", "Remove a reminder"),
    BotCommand("cron", "Add a recurring scheduled task"),
    BotCommand("crons", "List recurring tasks"),
    BotCommand("crondel", "Remove a recurring task"),
    BotCommand("nudges", "View today's proactive message budget"),
    BotCommand("heartbeat", "Trigger a proactive message now"),
    BotCommand("voice", "Toggle voice replies on/off"),
    BotCommand("model", "Show current model"),
    BotCommand("setmodel", "Change a model setting"),
    BotCommand("settings", "Show current settings"),
    BotCommand("usage", "Token usage stats"),
    BotCommand("chatid", "Show your chat ID"),
    BotCommand("backup", "Download a memory backup"),
]

_PAYMENT_COMMANDS = [
    BotCommand("addpayment", "Add a monthly bill"),
    BotCommand("addevery", "Add a recurring bill every N days"),
    BotCommand("payments", "List all bills"),
    BotCommand("delpayment", "Remove a bill"),
    BotCommand("editpayment", "Edit a bill field"),
    BotCommand("week", "Payment summary for this week"),
    BotCommand("remindpayments", "Trigger payment reminder now"),
]


async def _register_commands(application):
    cmds = _BASE_COMMANDS + (_PAYMENT_COMMANDS if PAYMENTS_ENABLED else [])
    await application.bot.set_my_commands(cmds)


def main():
    _acquire_termux_wake_lock()
    apply_overrides()
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_read_timeout(40)
        .post_init(_register_commands)
        .build()
    )

    app.add_error_handler(on_error)
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("card", card_cmd))
    app.add_handler(CommandHandler("setcard", setcard_cmd))
    app.add_handler(CommandHandler("model", model_info))
    app.add_handler(CommandHandler("setmodel", setmodel_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("usage", check_usage))
    app.add_handler(CommandHandler("chatid", chatid))
    app.add_handler(CommandHandler("heartbeat", heartbeat_now))
    app.add_handler(CommandHandler("selfie", selfie_cmd))
    app.add_handler(CommandHandler("memory", memory_cmd))
    app.add_handler(CommandHandler("exportmemory", export_memory_cmd))
    app.add_handler(CommandHandler("milestones", milestones_cmd))
    app.add_handler(CommandHandler("reading", reading_cmd))
    app.add_handler(CommandHandler("readnow", readnow_cmd))
    app.add_handler(CommandHandler("remember", remember_cmd))
    app.add_handler(CommandHandler("forget", forget_cmd))
    app.add_handler(CommandHandler("recall", recall_cmd))
    app.add_handler(CommandHandler("addmem", addmem_cmd))
    app.add_handler(CommandHandler("mems", mems_cmd))
    app.add_handler(CommandHandler("delmem", delmem_cmd))
    if PAYMENTS_ENABLED:
        app.add_handler(CommandHandler("addpayment", addpayment))
        app.add_handler(CommandHandler("addevery", addevery))
        app.add_handler(CommandHandler("payments", list_payments))
        app.add_handler(CommandHandler("delpayment", delpayment))
        app.add_handler(CommandHandler("editpayment", editpayment))
        app.add_handler(CommandHandler("remindpayments", remind_payments_now))
        app.add_handler(CommandHandler("week", remind_payments_now))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("recap", recap_cmd))
    app.add_handler(CommandHandler("quiet", quiet_cmd))
    app.add_handler(CommandHandler("life", life_cmd))
    app.add_handler(CommandHandler("people", people_cmd))
    app.add_handler(CommandHandler("projects", projects_cmd))
    app.add_handler(CommandHandler("schedule", schedule_cmd))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CommandHandler("note", note_cmd))
    app.add_handler(CommandHandler("notes", notes_cmd))
    app.add_handler(CommandHandler("remindme", remindme))
    app.add_handler(CommandHandler("setreminder", setreminder_cmd))
    app.add_handler(CommandHandler("reminders", list_reminders))
    app.add_handler(CommandHandler("delreminder", delreminder))
    app.add_handler(CommandHandler("cron", cron_add))
    app.add_handler(CommandHandler("crons", cron_list_cmd))
    app.add_handler(CommandHandler("crondel", cron_del_cmd))
    app.add_handler(CommandHandler("pin", pin_cmd))
    app.add_handler(CommandHandler("pinned", pinned_cmd))
    app.add_handler(CommandHandler("unpin", unpin_cmd))
    app.add_handler(CommandHandler("boundary", boundary_cmd))
    app.add_handler(CommandHandler("boundaries", boundaries_cmd))
    app.add_handler(CommandHandler("mood", mood_cmd))
    app.add_handler(CommandHandler("vibe", vibe_cmd))
    app.add_handler(CommandHandler("vent", vent_cmd))
    app.add_handler(CommandHandler("energy", energy_cmd))
    app.add_handler(CommandHandler("wardrobe", wardrobe_cmd))
    app.add_handler(CommandHandler("addoutfit", add_outfit_cmd))
    app.add_handler(CommandHandler("outfit", outfit_cmd))
    app.add_handler(CommandHandler("deloutfit", del_outfit_cmd))
    app.add_handler(CommandHandler("nudges", nudges_cmd))
    app.add_handler(CommandHandler("voice", voice_cmd))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.LOCATION, handle_location))
    if TRAFFIC_ENABLED:
        app.add_handler(CommandHandler("traffic", traffic_cmd))
        app.add_handler(CommandHandler("incidents", incidents_cmd))

    def _shutdown(sig, frame):
        log.info("Received signal %s — saving state and shutting down.", sig)
        save_state()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    if app.job_queue is not None:
        schedule_next_heartbeat(app.job_queue)
        log.info("Heartbeat: random, every %.0f–%.0fh.", HEARTBEAT_MIN / 3600, HEARTBEAT_MAX / 3600)
        if PAYMENTS_ENABLED:
            reminder_time = dtime(_REM_H, _REM_M, tzinfo=TZ) if TZ else dtime(_REM_H, _REM_M)
            app.job_queue.run_daily(payments_reminder, time=reminder_time)
            _wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][REMINDER_WEEKDAY % 7]
            log.info("Payment reminder scheduled %s on %s.", REMINDER_TIME, _wd)
        backup_time = dtime(_BK_H, _BK_M, tzinfo=TZ) if TZ else dtime(_BK_H, _BK_M)
        app.job_queue.run_daily(weekly_backup, time=backup_time)
        _bwd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][BACKUP_WEEKDAY % 7]
        log.info("Weekly backup scheduled %s on %s.", BACKUP_TIME, _bwd)
        reflection_time = dtime(_RF_H, _RF_M, tzinfo=TZ) if TZ else dtime(_RF_H, _RF_M)
        app.job_queue.run_daily(nightly_maintenance, time=reflection_time)
        log.info("Nightly maintenance scheduled %s.", REFLECTION_TIME)
        if READING_ENABLED:
            for _rt in READING_TIMES.split(","):
                _rt = _rt.strip()
                try:
                    _rh, _rm = (int(x) for x in _rt.split(":"))
                except Exception:
                    continue
                _rtime = dtime(_rh, _rm, tzinfo=TZ) if TZ else dtime(_rh, _rm)
                app.job_queue.run_daily(reading_job, time=_rtime)
            log.info("Reading feed scheduled at %s.", READING_TIMES)
        midnight = dtime(0, 1, tzinfo=TZ) if TZ else dtime(0, 1)  # 12:01 AM
        app.job_queue.run_daily(_rotate_day_context, time=midnight)
        log.info("Day context rotation scheduled at midnight.")
        for r in reminders:
            schedule_reminder(app.job_queue, r)
        if reminders:
            log.info("Re-armed %d pending reminder(s).", len(reminders))
        for j in cron_jobs:
            schedule_cron_job(app.job_queue, j)
        if cron_jobs:
            log.info("Re-armed %d scheduled task(s).", len(cron_jobs))
        if TRAFFIC_ENABLED:
            interval = TRAFFIC_POLL_MINUTES * 60
            app.job_queue.run_repeating(traffic_poll_job, interval=interval, first=60)
            log.info("Traffic polling: every %d min.", TRAFFIC_POLL_MINUTES)
    else:
        log.warning('JobQueue unavailable — scheduled features disabled. '
                    'Install with: pip install "python-telegram-bot[job-queue]"')

    log.info("%s is running (home: %s)", NAME, BASE_DIR)
    if ALLOWED_USERS:
        log.info("Access restricted to user IDs: %s", ALLOWED_USERS)
    app.run_polling()


if __name__ == "__main__":
    main()
