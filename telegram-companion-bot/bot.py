import os
import re
import sys
import json
import math
import fcntl
import random
import asyncio
# Python 3.14 removed the auto-create fallback from asyncio.get_event_loop().
# PTB v21 calls it internally in multiple places; patch it once here so the
# library's assumption holds regardless of Python version.
_orig_gel = asyncio.get_event_loop
def _gel_compat():
    try:
        return _orig_gel()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
asyncio.get_event_loop = _gel_compat
import time
import base64
import calendar
import logging
import logging.handlers
import tempfile
import threading
import secrets
import zipfile
import http.server
import html as _html_module
from io import BytesIO
from datetime import datetime, date, timedelta, time as dtime
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image, ImageDraw, ImageFont

import concurrent.futures

# Thread-local HTTP sessions — each worker thread gets its own connection pool,
# avoiding the thread-safety issues of a shared requests.Session.
_thread_local = threading.local()

def _get_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.mount("https://", HTTPAdapter(
            max_retries=Retry(total=0),
            pool_connections=4,
            pool_maxsize=8,
        ))
        s.mount("http://", HTTPAdapter(
            max_retries=Retry(total=0),
            pool_connections=2,
            pool_maxsize=4,
        ))
        _thread_local.session = s
    return s

# Dedicated pool for user-facing LLM replies — background tasks can never starve these.
_REPLY_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="reply")
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    ApplicationBuilder,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    MessageReactionHandler,
    ContextTypes,
    TypeHandler,
    filters,
)

# Bump on every release — shown in /audit and the startup log so it's always
# clear which build an instance is running.
BOT_VERSION = "2026-07-11.7"

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

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("companion")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

_error_log_path = BASE_DIR / "errors.log"
_error_handler = logging.handlers.RotatingFileHandler(
    _error_log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8",
)
_error_handler.setLevel(logging.WARNING)
_error_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
))
log.addHandler(_error_handler)

# --- Error tracking for self-audit ---
_BOOT_TIME = time.time()
_error_counts: dict[str, list[float]] = {}
_llm_stats: dict = {"date": "", "calls": 0, "tok_in": 0, "tok_out": 0}

def _count_error(category: str):
    ts = _error_counts.setdefault(category, [])
    ts.append(time.time())
    if len(ts) > 200:
        del ts[:-200]


def _track_llm_usage(messages: list, reply: str):
    today = time.strftime("%Y-%m-%d")
    if _llm_stats["date"] != today:
        _llm_stats["date"] = today
        _llm_stats["calls"] = 0
        _llm_stats["tok_in"] = 0
        _llm_stats["tok_out"] = 0
    _llm_stats["calls"] += 1
    _llm_stats["tok_in"] += sum(_est_tokens(m.get("content", "") or "") for m in messages)
    _llm_stats["tok_out"] += _est_tokens(reply)

# --- Env parsing that can't brick the fleet ---
# A non-numeric value in an instance .env used to raise at import and crash-loop
# that bot until someone reached a shell (/restart can't fix a file that won't
# import). Bad values now fall back to the default with a loud warning.
_CONFIG_WARNINGS: list[str] = []

def _env_int(name: str, default: str) -> int:
    raw = os.getenv(name, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        msg = f"{name}={raw!r} is not a valid integer — using default {default}"
        logging.warning("[config] %s", msg)
        _CONFIG_WARNINGS.append(msg)
        return int(default)


def _env_float(name: str, default: str = None):
    raw = os.getenv(name, default)
    if raw is None or raw == "":
        return None if default is None else float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        msg = f"{name}={raw!r} is not a valid number — using default {default}"
        logging.warning("[config] %s", msg)
        _CONFIG_WARNINGS.append(msg)
        return None if default is None else float(default)

# --- Access control ---
def _parse_id_set(raw: str, name: str) -> set[int]:
    """Comma-separated Telegram ids → set. Bad tokens are skipped with a warning —
    the old isdigit-after-lstrip filter let '--123' through to int(), which raised
    ValueError at import and crash-looped the bot until someone got to a shell."""
    out: set[int] = set()
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.add(int(tok))
        except ValueError:
            msg = f"ignoring invalid id {tok!r} in {name}"
            logging.warning("[config] %s", msg)
            _CONFIG_WARNINGS.append(msg)
    return out


_allowed_raw = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS: set[int] = _parse_id_set(_allowed_raw, "ALLOWED_USERS")

# --- Rate limiting ---
_last_request: dict[int, float] = {}
RATE_LIMIT_SECONDS = _env_float("RATE_LIMIT_SECONDS", "2")

def _is_allowed(user_id: int) -> bool:
    return not ALLOWED_USERS or user_id in ALLOWED_USERS

def _is_admin(user_id: int) -> bool:
    """Strict gate for operational commands (update/restart/errors/backup).
    Unlike _is_allowed, an empty ALLOWED_USERS does NOT open the door."""
    if user_id in ALLOWED_USERS:
        return True
    owner = get_owner()
    return owner is not None and user_id == owner

def _rate_ok(user_id: int) -> bool:
    now = time.time()
    if now - _last_request.get(user_id, 0) < RATE_LIMIT_SECONDS:
        return False
    _last_request[user_id] = now
    return True

NANOGPT_BASE_URL = os.getenv("NANOGPT_BASE", "https://nano-gpt.com/api/v1").rstrip("/")
NANOGPT_MODEL = os.getenv("NANOGPT_MODEL", "zai-org/glm-5:thinking")
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", NANOGPT_MODEL)  # can point at a faster model
VISION_MODEL = os.getenv("VISION_MODEL", "zai-org/glm-4.6v")    # must accept image input
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")          # used if the chat model 5xx/times out
VISION_FALLBACK = os.getenv("VISION_FALLBACK", "")        # must also accept image input
REQUEST_TIMEOUT = _env_int("REQUEST_TIMEOUT", "120")  # hard cap per request
# Dead man's switch: per-instance ping URL (e.g. healthchecks.io). The self-audit job
# GETs it every 30 min; the service alerts the owner when pings STOP — which catches
# every failure the bot can't self-report, including the whole phone being dead.
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL", "")
USAGE_BUDGET_MONTHLY = _env_float("USAGE_BUDGET_MONTHLY", "0")
STREAM_TIMEOUT = _env_int("STREAM_TIMEOUT", "90")    # max silence between chunks
MAX_TOKENS = _env_int("MAX_TOKENS", "2048")
CONTEXT_TOKEN_BUDGET = _env_int("CONTEXT_TOKEN_BUDGET", "0")
TEMPERATURE = _env_float("TEMPERATURE")  # None = use the model default
REACTION_MODEL = os.getenv("REACTION_MODEL", "zai-org/glm-4.7-flash")  # fast/cheap for emoji pick
REACTIONS_AUTO = os.getenv("REACTIONS_AUTO", "1").lower() not in ("0", "false", "no", "off")
MOOD_AUTO = os.getenv("MOOD_AUTO", "1").lower() not in ("0", "false", "no", "off")
MOOD_MODEL = os.getenv("MOOD_MODEL", REACTION_MODEL)  # cheap appraiser
MOOD_LABEL_FRESH_HOURS = _env_float("MOOD_LABEL_FRESH_HOURS", "12")
INNER_VOICE_ENABLED = os.getenv("INNER_VOICE_ENABLED", "false").lower() == "true"
INNER_VOICE_MODEL = os.getenv("INNER_VOICE_MODEL", MOOD_MODEL)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
VIDEO_MAX_SIZE_MB = _env_int("VIDEO_MAX_SIZE_MB", "50")
DOCUMENT_MAX_SIZE_MB = _env_int("DOCUMENT_MAX_SIZE_MB", "2")
# Separate model for document/card analysis — should be an instruction model,
# not a roleplay-tuned one, so it won't perform the character it's reading about.
DOCUMENT_MODEL = os.getenv("DOCUMENT_MODEL", "deepseek/deepseek-v4-flash")
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("TTS_VOICE", "nova")
TTS_CHANCE = _env_float("TTS_CHANCE", "0.30")
VOICE_REPLY_TO_VOICE = _env_float("VOICE_REPLY_TO_VOICE", "0.9")
# Inworld TTS: when INWORLD_API_KEY is set, voice replies use api.inworld.ai
# (with TTS_VOICE as the Inworld voice ID) instead of NanoGPT's speech endpoint.
INWORLD_API_KEY = os.getenv("INWORLD_API_KEY", "")   # base64 runtime key from the Inworld portal
INWORLD_TTS_MODEL = os.getenv("INWORLD_TTS_MODEL", "inworld-tts-2")
LINK_READING = os.getenv("LINK_READING", "1").lower() not in ("0", "false", "no", "off")
LINK_FETCH_TIMEOUT = _env_int("LINK_FETCH_TIMEOUT", "8")
LINK_MAX_CHARS = _env_int("LINK_MAX_CHARS", "2200")
SEARCH_ENABLED = os.getenv("SEARCH_ENABLED", "1").lower() not in ("0", "false", "no", "off")
SEARCH_RESULTS = _env_int("SEARCH_RESULTS", "4")
TEXTING_REALISM = os.getenv("TEXTING_REALISM", "1").lower() not in ("0", "false", "no", "off")
TYPING_DELAY = os.getenv("TYPING_DELAY", "1").lower() not in ("0", "false", "no", "off")
TYPING_WPM = _env_float("TYPING_WPM", "120")
TYPING_DELAY_MIN = _env_float("TYPING_DELAY_MIN", "0.5")
TYPING_DELAY_MAX = _env_float("TYPING_DELAY_MAX", "3.5")

# --- Group chat (experimental, GROUP_CHAT_DESIGN.md) ---
# An instance participates in a group only when GROUP_MODE=1 AND the group is in
# GROUP_ALLOWED_CHATS. Every other instance ignores group traffic entirely (fail
# closed, fleet-wide) — see group_guard().
GROUP_MODE = os.getenv("GROUP_MODE", "0").lower() in ("1", "true", "yes")
GROUP_ALLOWED_CHATS: set[int] = _parse_id_set(
    os.getenv("GROUP_ALLOWED_CHATS", ""), "GROUP_ALLOWED_CHATS")
GROUP_PEERS = [p.strip() for p in os.getenv("GROUP_PEERS", "").split(",") if p.strip()]
GROUP_PEER_NOTES = os.getenv("GROUP_PEER_NOTES", "")  # "Name: relationship line; Name2: ..."
GROUP_BOT_REPLY_PROB = _env_float("GROUP_BOT_REPLY_PROB", "0.35")
GROUP_BOT_CHAIN_MAX = _env_int("GROUP_BOT_CHAIN_MAX", "2")
GROUP_POLL_SECONDS = _env_int("GROUP_POLL_SECONDS", "5")
GROUP_MIN_GAP_SECONDS = _env_float("GROUP_MIN_GAP_SECONDS", "20")
GROUP_ALTERNATION_PENALTY = _env_float("GROUP_ALTERNATION_PENALTY", "2.0")
GROUP_DAILY_BOT_BUDGET = _env_int("GROUP_DAILY_BOT_BUDGET", "30")
GROUP_LEDGER_DIR = Path(os.getenv("GROUP_LEDGER_DIR", str(Path(__file__).resolve().parent)))
GROUP_LEDGER_MAX_AGE_SECONDS = _env_int("GROUP_LEDGER_MAX_AGE_SECONDS", "600")
GROUP_CLAIM_TTL_SECONDS = _env_int("GROUP_CLAIM_TTL_SECONDS", "600")
GROUP_ALLOWED_COMMANDS = {"chatid"}

# --- R6 evolution experiments (each behind its own flag, default off) ---
FEEDBACK_REACTIONS = os.getenv("FEEDBACK_REACTIONS", "0").lower() in ("1", "true", "yes")
CLOSENESS_ENABLED = os.getenv("CLOSENESS_ENABLED", "0").lower() in ("1", "true", "yes")
THREADS_ENABLED = os.getenv("THREADS_ENABLED", "0").lower() in ("1", "true", "yes")
JOKE_CANDIDATES = os.getenv("JOKE_CANDIDATES", "0").lower() in ("1", "true", "yes")

_DEFAULT_TEXTING_STYLE = (
    "# How you text\n"
    "You're texting on a phone, not narrating a scene. Write like a real person types:\n"
    "- Go very light on *asterisk actions* — use them only when a physical detail genuinely adds "
    "something. Don't stage-direct your movements (no \"*heads for the door, jacket on*\"). Mostly "
    "just talk.\n"
    "- Vary your energy. Not every message is intense or a big declaration — sometimes you're tired, "
    "distracted, low-key, or just saying something ordinary. Let flat and mundane moments exist.\n"
    "- Keep the language plain and natural, the way people actually text. Skip the poetic or dramatic "
    "lines and the performing. Understatement over theater.\n"
    "- Don't narrate things you almost did or almost said (\"almost texted you,\" \"I deleted a whole "
    "argument,\" \"was going to send you this\"). Claiming credit for actions not taken is a tic, not "
    "intimacy. Either do it or don't mention it.\n"
    "- Don't interrogate — don't stack questions or end every message on one (see dialogue_rules "
    "if the card has them).\n"
    "- Use normal capitalization and punctuation — capitalize sentence starts, \"I\", and proper "
    "nouns, and use periods/commas/question marks where they'd naturally fall. Casual phrasing and "
    "fragments are fine; sloppy typing (all lowercase, no punctuation) is not the goal."
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
    resp = _get_session().post(
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
SELFIE_BASE = os.getenv("SELFIE_BASE", "priya_base.png")
SELFIE_SIZE = os.getenv("SELFIE_SIZE", "1024x1024")
SELFIE_GUIDANCE = _env_float("SELFIE_GUIDANCE", "3.5")
SELFIE_STEPS = _env_int("SELFIE_STEPS", "28")
IMAGE_TIMEOUT = _env_int("IMAGE_TIMEOUT", "180")

if SELFIE_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise SystemExit("SELFIE_PROVIDER=gemini but GEMINI_API_KEY not found in .env at " + str(env_path))

# --- Memes (template + text overlay, not AI-generated -- AI image models render text
# unreliably, and a meme lives or dies on legible captions) ---
# Templates/font are shared code assets (alongside bot.py), not per-instance, since
# they're generic rather than character-specific.
MEME_TEMPLATES_DIR = Path(__file__).resolve().parent / "meme_templates"
MEME_FONT_PATH = Path(__file__).resolve().parent / "fonts" / "Anton-Regular.ttf"
MEME_FONT_SIZE = _env_int("MEME_FONT_SIZE", "80")
MEME_MIN_FONT_SIZE = 24
MEME_DEDUP_SIZE = _env_int("MEME_DEDUP_SIZE", "5")
_recent_meme_templates: dict = {}  # chat_id -> list of recently used template filenames
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
HEARTBEAT_MIN = _env_float("HEARTBEAT_MIN_HOURS", "2") * 3600  # random window low end
HEARTBEAT_MAX = _env_float("HEARTBEAT_MAX_HOURS", "6") * 3600  # random window high end
OWNER_CHAT_ID_ENV = os.getenv("OWNER_CHAT_ID")
OWNER_FILE = BASE_DIR / "owner_chat.txt"
MAX_HISTORY = 20    # hard count cap on the verbatim window (marathon-session safety)
KEEP_RECENT = 10    # always keep at least this many recent messages verbatim
SHORT_TERM_HOURS = _env_float("SHORT_TERM_HOURS", "48")  # verbatim messages older
SHORT_TERM_SECS = SHORT_TERM_HOURS * 3600                       # than this get distilled out

# --- Local atlas (real places she can reference / selfie backgrounds) ---
ATLAS_FILE = BASE_DIR / os.getenv("ATLAS_FILE", "atlas.txt")
ATLAS_SAMPLE = _env_int("ATLAS_SAMPLE", "6")
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

# NPC / world relationship memories (memories.txt) — keyword-triggered RAG injection
MEMORIES_FILE = BASE_DIR / "memories.txt"
MEMORY_TOKEN_BUDGET = _env_int("MEMORY_TOKEN_BUDGET", "300")
MEMORIES_MAX = _env_int("MEMORIES_MAX", "200")
MEMORY_AUTO = os.getenv("MEMORY_AUTO", "1").strip() not in ("0", "false", "no")
MEMORY_AUTOCONF = _env_int("MEMORY_AUTOCONF", "7")
AWAY_AUTO_HOURS = _env_int("AWAY_AUTO_HOURS", "3")
_memories_cache: dict = {"text": None, "ts": 0.0}
_memory_lock = threading.Lock()

# Memory provenance sidecar (R1 memory auditor)
MEMORY_META_FILE = BASE_DIR / "memory_meta.json"
MEMORY_REVIEW_FILE = BASE_DIR / "memory_review.json"
MEMORY_LOG_FILE = BASE_DIR / "memory_log.txt"
MEMORY_REVIEW_MAX = 20
_memory_meta: dict[str, dict] = {}


def _load_memory_meta():
    global _memory_meta
    try:
        if MEMORY_META_FILE.exists():
            _memory_meta = json.loads(MEMORY_META_FILE.read_text(encoding="utf-8"))
    except Exception:
        _memory_meta = {}


def _save_memory_meta():
    try:
        MEMORY_META_FILE.write_text(
            json.dumps(_memory_meta, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning("[memory-meta] save failed: %s", e)


def _load_memory_review() -> list[dict]:
    try:
        if MEMORY_REVIEW_FILE.exists():
            return json.loads(MEMORY_REVIEW_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_memory_review(queue: list[dict]):
    try:
        MEMORY_REVIEW_FILE.write_text(
            json.dumps(queue, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning("[memory-review] save failed: %s", e)


def _memory_log(action: str, text: str = "", extra: str = ""):
    try:
        now = datetime.now(tz=TZ).strftime("%Y-%m-%dT%H:%M") if TZ else datetime.now().strftime("%Y-%m-%dT%H:%M")
        entry = f"{now} {action}"
        if text:
            entry += f' "{text[:120]}"'
        if extra:
            entry += f" {extra}"
        with open(MEMORY_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
        try:
            lines = MEMORY_LOG_FILE.read_text(encoding="utf-8").splitlines()
            if len(lines) > 1000:
                MEMORY_LOG_FILE.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
        except Exception:
            pass
    except Exception as e:
        log.warning("[memory-log] write failed: %s", e)


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _trim_history_to_budget(messages: list, budget: int) -> list:
    if budget <= 0:
        return messages
    total = sum(_est_tokens(m.get("content", "") if isinstance(m.get("content"), str)
                            else str(m.get("content", ""))) for m in messages)
    if total <= budget:
        return messages
    system_indices = {i for i, m in enumerate(messages) if m["role"] == "system"}
    final_user = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "user":
            final_user = i
            break
    protected = system_indices | ({final_user} if final_user is not None else set())
    droppable = [i for i in range(len(messages)) if i not in protected]
    dropped = 0
    while total > budget and droppable:
        i = droppable.pop(0)
        content = messages[i].get("content", "")
        total -= _est_tokens(content if isinstance(content, str) else str(content))
        messages[i] = None
        dropped += 1
    messages = [m for m in messages if m is not None]
    if dropped:
        log.info("[prompt] trimmed %d msgs, ~%dk tokens over budget", dropped, (total // 1000))
    return messages


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


def _read_schedule_today() -> str:
    """Return today's section from schedule.txt (lines under today's day name)."""
    if not SCHEDULE_FILE.exists():
        return ""
    try:
        text = SCHEDULE_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    today = (datetime.now(tz=TZ) if TZ else datetime.now()).strftime("%A")  # e.g. "Monday"
    day_abbrevs = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    lines = text.splitlines()
    result, in_today = [], False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # A heading is a line whose FIRST WORD is a day name/abbrev ("Mon", "Monday",
        # "Monday:"), not any line that merely starts with those letters — plain
        # startswith turned "money is tight" into a Monday heading ("wedding"→Wed,
        # "sunshine"→Sun, …) and served the wrong day's schedule.
        first_word = re.split(r"[\s:,-]+", stripped.lower(), maxsplit=1)[0]
        is_day_heading = any(
            first_word == d or (first_word.startswith(d) and first_word in
                                ("monday", "tuesday", "wednesday", "thursday",
                                 "friday", "saturday", "sunday", "tues", "thur", "thurs"))
            for d in day_abbrevs
        )
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
USER_NOTES_MAX = _env_int("USER_NOTES_MAX", "15")
_user_notes_cache: dict = {"text": None, "ts": 0.0}


def _read_user_notes() -> str:
    return _read_life_file(USER_NOTES_FILE, _user_notes_cache)


def _append_user_note(note: str, due: str = ""):
    note = note.strip()
    if not note:
        return
    existing = USER_NOTES_FILE.read_text(encoding="utf-8").strip() if USER_NOTES_FILE.exists() else ""
    if existing and note[:20].lower() in existing.lower():
        return  # simple dedup
    if due:
        # Suffix marker (keeps the prefix dedup working); note_followup_job fires on it.
        note = f"{note} (due {due})"
    lines = [l for l in existing.splitlines() if l.strip()]
    lines.append(note)
    if len(lines) > USER_NOTES_MAX:
        lines = lines[-USER_NOTES_MAX:]
    USER_NOTES_FILE.write_text("\n".join(lines), encoding="utf-8")
    _user_notes_cache["text"] = None  # invalidate cache


def _memory_replace(old_line: str | None, new_line: str | None, meta: dict | None = None):
    """Single choke point for all memory mutations (add/edit/delete).
    Keeps memories.txt, embeddings.json, and memory_meta.json in sync."""
    with _memory_lock:
        existing = MEMORIES_FILE.read_text(encoding="utf-8") if MEMORIES_FILE.exists() else ""
        lines = [l for l in existing.splitlines() if l.strip()]
        if old_line is not None:
            old_stripped = old_line.strip()
            try:
                idx = next(i for i, l in enumerate(lines) if l.strip() == old_stripped)
            except StopIteration:
                return False
            lines.pop(idx)
            _embeddings_cache.pop(old_stripped, None)
            _memory_meta.pop(old_stripped, None)
        if new_line is not None:
            new_stripped = new_line.strip()
            if not new_stripped:
                return old_line is not None
            lines.append(new_stripped)
            if len(lines) > MEMORIES_MAX:
                lines = lines[-MEMORIES_MAX:]
            _embed_memory_line(new_stripped)
            if meta:
                _memory_meta[new_stripped] = meta
        MEMORIES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _memories_cache["text"] = None
        _memories_cache["ts"] = 0.0
        _save_embeddings()
        _save_memory_meta()
    return True


def _append_memory(text: str, auto: bool = False, meta: dict | None = None):
    text = text.strip()
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
    if meta is None:
        meta = {"ts": time.time(), "origin": "auto" if auto else "manual"}
    _memory_replace(None, entry, meta=meta)
    action = "ADD auto" if auto else "ADD manual"
    conf = meta.get("confidence")
    src = meta.get("source", "")
    extra = ""
    if conf is not None:
        extra += f"conf={conf}"
    if src:
        extra += f' src="{src[:80]}"'
    _memory_log(action, text, extra)


# --- Semantic memory (embeddings-backed recall) ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDINGS_FILE = BASE_DIR / "embeddings.json"
_embeddings_cache: dict[str, list[float]] = {}
_embeddings_dirty = False


def _load_embeddings():
    global _embeddings_cache
    try:
        if EMBEDDINGS_FILE.exists():
            _embeddings_cache = json.loads(EMBEDDINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        _embeddings_cache = {}


def _save_embeddings():
    global _embeddings_dirty
    if not _embeddings_dirty:
        return
    try:
        EMBEDDINGS_FILE.write_text(
            json.dumps(_embeddings_cache, ensure_ascii=False), encoding="utf-8")
        _embeddings_dirty = False
    except Exception as e:
        log.warning("[embeddings] save failed: %s", e)


def _embed_text(text: str) -> list[float] | None:
    try:
        resp = _get_session().post(
            f"{NANOGPT_BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {NANOGPT_API_KEY}"},
            json={"model": EMBEDDING_MODEL, "input": text[:8000]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    except Exception as e:
        log.debug("[embeddings] embed failed: %s", e)
        return None


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _embed_memory_line(line: str):
    global _embeddings_dirty
    key = line.strip()
    if key in _embeddings_cache:
        return
    vec = _embed_text(key)
    if vec:
        _embeddings_cache[key] = vec
        _embeddings_dirty = True


def semantic_recall(query: str, entries: list[str], top_k: int = 5) -> list[tuple[float, str]]:
    q_vec = _embed_text(query)
    if not q_vec:
        return []
    scored = []
    for line in entries:
        key = line.strip()
        vec = _embeddings_cache.get(key)
        if vec:
            scored.append((_cosine_sim(q_vec, vec), line))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


_load_embeddings()
_load_memory_meta()


def _quote_grounded(quote: str, user_lines: list[str]) -> bool:
    """True if quote is a substring of any user line (case/whitespace-normalized)."""
    if not quote or not user_lines:
        return False
    norm_q = " ".join(quote.lower().split())
    if not norm_q:
        return False
    for line in user_lines:
        norm_l = " ".join(line.lower().split())
        if norm_q in norm_l:
            return True
    return False


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
    log.error("[time] Could not load timezone '%s' (%s); using device local time.", TIMEZONE, e)
    TZ = None

# Built-in default setting. Override by dropping a setting.txt next to bot.py.
DEFAULT_SETTING = (
    "Nora grew up on Chicago's South Side and is Chicago underneath it all — her directness, "
    "the chip on her shoulder, Ingrid's jacket she still wears, her instincts. She's since moved "
    "to Seattle for the messenger work. She's a transplant: she measures everything against "
    "Chicago, gripes about Seattle's passive-aggressiveness and its hills, misses real deep-dish, "
    "but Seattle is her life now. Use real Seattle geography for her present-day surroundings — "
    "the hills, the rain, her bike routes, Capitol Hill, the waterfront — while keeping her "
    "Chicago roots, edge, and frame of reference fully intact."
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
TRAFFIC_RADIUS_MILES = _env_float("TRAFFIC_RADIUS_MILES", "10")
TRAFFIC_POLL_MINUTES = _env_int("TRAFFIC_POLL_MINUTES", "10")
_WSDOT_ALERTS_URL   = "https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/HighwayAlertsREST.svc/GetAlertsAsJson"
_WSDOT_TIMES_URL    = "https://www.wsdot.wa.gov/Traffic/api/TravelTimes/TravelTimesREST.svc/GetTravelTimesAsJson"

# --- TomTom Maps (routing + place/POI search; Nora, Emily, Priya) ---
# Fail-closed like WSDOT above: no key => /route /nearby /place are disabled.
TOMTOM_API_KEY      = os.getenv("TOMTOM_API_KEY", "")
TOMTOM_ENABLED      = bool(TOMTOM_API_KEY)
# Per-instance default travel mode for /route, validated per-call by _tomtom_mode().

# --- Payment reminders (off by default on named character instances) ---
PAYMENTS_ENABLED = os.getenv(
    "PAYMENTS_ENABLED", "0" if IS_NAMED_INSTANCE else "1"
).lower() not in ("0", "false", "no", "off")
PAYMENTS_FILE = BASE_DIR / "payments.json"
REMINDER_TIME = os.getenv("REMINDER_TIME", "09:00")        # HH:MM in local TZ
REMINDER_WEEKDAY = _env_int("REMINDER_WEEKDAY", "3")  # Mon=0 ... Thu=3 ... Sun=6
REMINDER_WINDOW_DAYS = _env_int("REMINDER_WINDOW_DAYS", "6")  # Thu + 6 = next Wed
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
BACKUP_WEEKDAY = _env_int("BACKUP_WEEKDAY", "6")  # Sun=6
BACKUP_TIME = os.getenv("BACKUP_TIME", "09:05")
try:
    _BK_H, _BK_M = (int(x) for x in BACKUP_TIME.split(":"))
except Exception:
    _BK_H, _BK_M = 9, 5

# --- One-off reminders ---
REMINDERS_FILE = BASE_DIR / "reminders.json"

# --- Shared world context (world.txt) — same weather/happenings across all instances ---
# One instance (WORLD_GENERATOR=1, typically nora) writes world.txt at midnight;
# every instance reads it as day-generation context if present.
_SCRIPT_DIR = Path(__file__).resolve().parent
WORLD_FILE = Path(os.getenv("WORLD_FILE", str(_SCRIPT_DIR / "world.txt")))
WORLD_GENERATOR = os.getenv("WORLD_GENERATOR", "").lower() in ("1", "true", "yes")

def _read_world_context() -> str:
    try:
        return WORLD_FILE.read_text(encoding="utf-8").strip() if WORLD_FILE.exists() else ""
    except Exception:
        return ""

# --- Group chat: shared ledger, claims, turn-taking (GROUP_CHAT_DESIGN.md) ---
# Telegram never delivers one bot's messages to another bot, so bot-to-bot flows
# through a shared JSONL ledger on the common filesystem (same pattern as world.txt).
# LOCK DISCIPLINE (binding): every flock acquire/release runs in a worker thread via
# asyncio.to_thread, and the lock is NEVER held across an await — see design §3.

def _group_ledger_path(chat_id: int) -> Path:
    return GROUP_LEDGER_DIR / f"group_{chat_id}.jsonl"


def _group_claims_dir() -> Path:
    d = GROUP_LEDGER_DIR / "group_claims"
    try:
        d.mkdir(exist_ok=True)
    except Exception:
        pass
    return d


def _parse_ledger_lines(lines) -> list[dict]:
    """Tolerant line-by-line parse; bad lines are skipped and counted, never fatal."""
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            e = json.loads(ln)
        except Exception:
            _count_error("group_ledger")
            continue
        if isinstance(e, dict) and "msg_id" in e and e.get("kind") in ("human", "bot"):
            out.append(e)
    return out


def _bot_chain_len(entries: list[dict]) -> int:
    """Consecutive kind=='bot' entries at the ledger tail. A human message resets it."""
    n = 0
    for e in reversed(entries):
        if e.get("kind") == "bot":
            n += 1
        else:
            break
    return n


def _is_addressed(text: str, char_name: str, bot_username: str, replied_to_own: bool = False) -> bool:
    """Does this message address this character? @username, first name on a word
    boundary, or a Telegram reply to a message this bot posted."""
    if replied_to_own:
        return True
    low = (text or "").lower()
    if bot_username and f"@{bot_username.lower()}" in low:
        return True
    first = (char_name or "").split()[0].lower() if char_name else ""
    if first and re.search(r"\b" + re.escape(first) + r"\b", low):
        return True
    return False


def _should_reply_to_bot(entries: list[dict], prob_roll: float, addressed: bool) -> bool:
    """Reply to a peer bot's message? The chain cap overrides even being addressed —
    that's the loop-prevention primary (design §3)."""
    if _bot_chain_len(entries) >= GROUP_BOT_CHAIN_MAX:
        return False
    return addressed or prob_roll < GROUP_BOT_REPLY_PROB


def _claim_delay(entries: list[dict], char_name: str, jitter_roll: float) -> float:
    """Jittered pre-claim delay; the last bot to have spoken waits extra so the quieter
    character tends to win the next open message (alternation without coordination)."""
    delay = 0.5 + max(0.0, min(1.0, jitter_roll)) * 2.5
    first = (char_name or "").split()[0] if char_name else ""
    for e in reversed(entries):
        if e.get("kind") == "bot":
            if e.get("sender") == first:
                delay += GROUP_ALTERNATION_PENALTY
            break
    return delay


def _ledger_append(chat_id: int, entry: dict) -> bool:
    """Append one entry under an exclusive lock, deduping by msg_id against the tail
    (all privacy-off bots receive the same human message; one append survives).
    Rotates the file when it grows past ~1000 lines. Blocking — call via to_thread."""
    path = _group_ledger_path(chat_id)
    try:
        with open(path, "a+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                lines = f.readlines()
                tail = _parse_ledger_lines(lines[-50:])
                if any(e.get("msg_id") == entry.get("msg_id") for e in tail):
                    return False
                if len(lines) > 1000:
                    keep = lines[-300:]
                    f.seek(0)
                    f.truncate()
                    f.writelines(keep)
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                return True
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        log.warning("[group] ledger append failed: %s", e)
        _count_error("group_ledger")
        return False


def _ledger_tail(chat_id: int, max_lines: int = 50) -> list[dict]:
    """Last entries of the ledger, read under a shared lock. Blocking — to_thread."""
    path = _group_ledger_path(chat_id)
    if not path.exists():
        return []
    try:
        with open(path, "rb") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 16384))
                raw = f.read()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return _parse_ledger_lines(raw.decode("utf-8", "replace").splitlines()[-max_lines:])
    except Exception as e:
        log.warning("[group] ledger tail read failed: %s", e)
        _count_error("group_ledger")
        return []


def _ledger_read_new(chat_id: int) -> list[dict]:
    """Entries past this instance's persisted byte cursor. On first sight or rotation
    shrink, fast-forward to EOF (never replay). Blocking — call via to_thread."""
    path = _group_ledger_path(chat_id)
    if not path.exists():
        return []
    try:
        with open(path, "rb") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                f.seek(0, 2)
                size = f.tell()
                cur = group_cursor.get(chat_id, -1)
                if cur < 0 or cur > size:
                    group_cursor[chat_id] = size
                    save_state()
                    return []
                if cur == size:
                    return []
                f.seek(cur)
                raw = f.read()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        group_cursor[chat_id] = cur + len(raw)
        save_state()
        return _parse_ledger_lines(raw.decode("utf-8", "replace").splitlines())
    except Exception as e:
        log.warning("[group] ledger read failed: %s", e)
        _count_error("group_ledger")
        return []


def _chain_ok_under_lock(chat_id: int) -> bool:
    """Pre-send re-check of the chain cap against the current ledger tail (design §3).
    Fails open on IO error — the claim/throttle/budget still bound. Blocking — to_thread."""
    return _bot_chain_len(_ledger_tail(chat_id)) < GROUP_BOT_CHAIN_MAX


def _try_claim(chat_id: int, msg_id) -> bool:
    """Atomically claim the right to answer one message. O_CREAT|O_EXCL: exactly one
    process fleet-wide can succeed. Blocking — call via to_thread."""
    try:
        fd = os.open(str(_group_claims_dir() / f"{chat_id}_{msg_id}"),
                     os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception as e:
        log.warning("[group] claim failed: %s", e)
        _count_error("group_claim")
        return False


def _prune_claims():
    """Delete claim markers older than the TTL. Blocking — call via to_thread."""
    try:
        now = time.time()
        for p in _group_claims_dir().iterdir():
            try:
                if now - p.stat().st_mtime > GROUP_CLAIM_TTL_SECONDS:
                    p.unlink()
            except FileNotFoundError:
                pass
    except Exception:
        pass


_group_last_send: dict[int, float] = {}  # chat_id -> ts of our last group message


def _group_gap_ok(chat_id: int) -> bool:
    return time.time() - _group_last_send.get(chat_id, 0) >= GROUP_MIN_GAP_SECONDS


def _group_budget_ok(chat_id: int) -> bool:
    today = (datetime.now(TZ) if TZ else datetime.now()).strftime("%Y-%m-%d")
    b = group_bot_sends_today.get(chat_id)
    if not b or b.get("date") != today:
        return True
    return b.get("count", 0) < GROUP_DAILY_BOT_BUDGET


def _group_bump_budget(chat_id: int):
    today = (datetime.now(TZ) if TZ else datetime.now()).strftime("%Y-%m-%d")
    b = group_bot_sends_today.get(chat_id)
    if not b or b.get("date") != today:
        group_bot_sends_today[chat_id] = {"date": today, "count": 1}
    else:
        b["count"] = b.get("count", 0) + 1
    save_state()


def _run_claim_test() -> bool:
    """--claim-test: on-device smoke test of both atomicity primitives before trusting
    them (GROUP_CHAT_DESIGN.md §10.5). Two processes race 100 claims (exactly one
    winner each) and append 100 flock'd ledger lines each (all 200 intact)."""
    import multiprocessing as mp
    test_chat = -999_999_999
    ledger = _group_ledger_path(test_chat)
    ledger.unlink(missing_ok=True)
    for p in _group_claims_dir().glob(f"{test_chat}_*"):
        p.unlink(missing_ok=True)

    def worker(idx: int, q):
        wins = 0
        for i in range(100):
            if _try_claim(test_chat, 7_000_000 + i):
                wins += 1
            _ledger_append(test_chat, {
                "ts": time.time(), "msg_id": idx * 1_000_000 + i,
                "sender": f"proc{idx}", "kind": "bot", "text": "x" * 40, "reply_to": None,
            })
        q.put(wins)

    q = mp.Queue()
    procs = [mp.Process(target=worker, args=(i + 1, q)) for i in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    wins = [q.get(timeout=5) for _ in range(2)]
    entries = _parse_ledger_lines(ledger.read_text(encoding="utf-8").splitlines())
    claims_ok = sum(wins) == 100
    ledger_ok = len(entries) == 200
    print(f"[claim-test] claims: {wins[0]}+{wins[1]}={sum(wins)} (want exactly 100) -> "
          f"{'PASS' if claims_ok else 'FAIL'}")
    print(f"[claim-test] ledger: {len(entries)}/200 intact lines -> "
          f"{'PASS' if ledger_ok else 'FAIL'}")
    ledger.unlink(missing_ok=True)
    for p in _group_claims_dir().glob(f"{test_chat}_*"):
        p.unlink(missing_ok=True)
    return claims_ok and ledger_ok


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


# --- Date-aware note follow-ups ("interview Tuesday" -> asks how it went) ---
NOTE_FOLLOWUP_TIME = os.getenv("NOTE_FOLLOWUP_TIME", "18:00")
try:
    _NF_H, _NF_M = (int(x) for x in NOTE_FOLLOWUP_TIME.split(":"))
except Exception:
    _NF_H, _NF_M = 18, 0

# --- Nightly self-reflection (self-image + recommendation outcomes) ---
REFLECTION_TIME = os.getenv("REFLECTION_TIME", "03:00")
try:
    _RF_H, _RF_M = (int(x) for x in REFLECTION_TIME.split(":"))
except Exception:
    _RF_H, _RF_M = 3, 0
BELIEF_TRAITS = _env_int("BELIEF_TRAITS", "5")      # how many core self-image traits to track
BELIEF_DRIFT_MAX = _env_float("BELIEF_DRIFT_MAX", "2.5")  # max distance from her card-derived baseline
RECS_MAX = _env_int("RECS_MAX", "20")  # cap on tracked recommendations/outcomes
MILESTONES_MAX = _env_int("MILESTONES_MAX", "30")  # cap on relationship milestones stored


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
        lore.append({
            "keys": [k.lower() for k in entry.get("keys", [])],
            "content": (entry.get("content") or "").strip(),
            "constant": bool(entry.get("constant", False)),
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


def _char_first_name() -> str:
    """First name of the character — the ledger sender label and the name peers use
    to address her in groups. A function (not a constant) so /setcard stays live."""
    return (NAME or "Bot").split()[0]


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
beliefs = {}        # chat_id -> {"items": {trait: {"score": float, "anchor": float}}}
recommendations = {}  # chat_id -> [{"id", "text", "ts", "status", "outcome", "note"}]
rec_seq = {}        # chat_id -> next recommendation id
next_goals = {}     # chat_id -> something she wants to bring up/do next time they talk
milestones = {}     # chat_id -> [{"text": str, "ts": float}] relationship firsts
pinned = {}         # chat_id -> [str] facts that never get summarized away
boundaries = {}     # chat_id -> [str] hard behavioral constraints from the user
current_vibe = {}   # chat_id -> {"name": str, "expires_at": float|None}
vent_mode = {}      # chat_id -> bool
user_energy = {}    # chat_id -> {"level": "low"|"medium"|"high", "ts": float}
unsent_drafts = {}  # chat_id -> [{"reason": str, "ts": float}]
nudge_budget = {}   # chat_id -> {"limit": int, "sent_today": int, "reset_date": str}
quiet_until = {}    # chat_id -> float (unix ts); suppress proactives until then
quiet_windows = {}  # chat_id -> [{"dow": int (0=Mon), "start": int (minutes), "end": int (minutes)}]
away = {}           # chat_id -> {"reason": str, "since": float, "origin": str, "expires": float|None}
_just_returned = {} # chat_id -> {"reason": str} — ephemeral, cleared after one reply
voice_reply = {}    # chat_id -> bool  (TTS replies enabled)
inside_jokes = []   # [{"id":int,"phrase":str,"meaning":str,"tone":str,"last_used":float,"cooldown_days":int}]
wardrobe = {"outfits": [], "current": None}  # loaded from wardrobe.json
summarizing = set()  # chat_ids with a summary update in flight (avoid overlap)
_SUMMARIZE_SEM = asyncio.Semaphore(1)
model_overrides = {}    # global var name (e.g. "NANOGPT_MODEL") -> model id, set via /setmodel
setting_overrides = {}  # global var name (e.g. "SEARCH_ENABLED") -> value, set via /settings
user_location: dict = {}   # chat_id -> {lat, lon, ts, live_until}  (traffic feature)
seen_incidents: dict = {}  # chat_id -> set of AlertID strings already alerted on
group_cursor: dict = {}    # group chat_id -> byte offset into the shared group ledger
group_bot_sends_today: dict = {}  # group chat_id -> {"date": str, "count": int} (bot-to-bot budget)
feedback_log: dict = {}    # chat_id -> [{"emoji": str, "ts": float, "msg_snippet": str}] (capped 50)
closeness: dict = {}       # chat_id -> {"score": float, "bucket": str, "updated": str}
open_threads: dict = {}    # chat_id -> [str] (capped 3) — replaces str next_goals when THREADS_ENABLED

STATE_FILE = BASE_DIR / "state.json"
# watchdog.sh (a phone-side script, not part of this repo) treats a stale .alive as a
# frozen-but-technically-running bot and force-restarts it. It expects this touched
# every 60s; without this job the file (if present at all, e.g. from manual setup) only
# gets more stale, so watchdog.sh eventually restarts every bot on a loop forever.
ALIVE_FILE = BASE_DIR / ".alive"


async def _touch_alive(context: ContextTypes.DEFAULT_TYPE):
    try:
        ALIVE_FILE.touch(exist_ok=True)
    except Exception:
        pass


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
    for cid, bv in data.get("beliefs", {}).items():
        beliefs[int(cid)] = bv
    for cid, rl in data.get("recommendations", {}).items():
        recommendations[int(cid)] = rl
    for cid, sq in data.get("rec_seq", {}).items():
        rec_seq[int(cid)] = sq
    for cid, g in data.get("next_goals", {}).items():
        next_goals[int(cid)] = g
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
    for cid, qw in data.get("quiet_windows", {}).items():
        quiet_windows[int(cid)] = qw
    for cid, vr in data.get("voice_reply", {}).items():
        voice_reply[int(cid)] = vr
    for cid, aw in data.get("away", {}).items():
        away[int(cid)] = aw
    model_overrides.update(data.get("model_overrides", {}))
    setting_overrides.update(data.get("setting_overrides", {}))
    for cid, lv in data.get("user_location", {}).items():
        user_location[int(cid)] = lv
    for cid, ids in data.get("seen_incidents", {}).items():
        seen_incidents[int(cid)] = set(ids)
    for cid, off in data.get("group_cursor", {}).items():
        group_cursor[int(cid)] = off
    for cid, b in data.get("group_bot_sends_today", {}).items():
        group_bot_sends_today[int(cid)] = b
    for cid, fl in data.get("feedback_log", {}).items():
        feedback_log[int(cid)] = fl[-50:]
    for cid, cl in data.get("closeness", {}).items():
        closeness[int(cid)] = cl
    for cid, ot in data.get("open_threads", {}).items():
        open_threads[int(cid)] = ot[:3]
    # Migration (THREADS_ENABLED): next_goals str -> open_threads list
    if THREADS_ENABLED:
        for cid, g in list(next_goals.items()):
            if isinstance(g, str) and g.strip() and cid not in open_threads:
                open_threads[cid] = [g.strip()]
    for cat, ts in data.get("error_counts", {}).items():
        _error_counts[cat] = ts[-200:]
    saved_llm = data.get("llm_stats")
    if saved_llm and saved_llm.get("date") == time.strftime("%Y-%m-%d"):
        _llm_stats.update(saved_llm)
    # Migration (v2026-07-10.2): day archives used to be stored as plain "[Jul 09] …"
    # facts — indistinguishable from real user facts, so proactive prompts asserted
    # her own fiction as shared history. Retag them, and move any that were promoted
    # into permanent facts back into the recent tier where they expire.
    for cid in list(recent_facts.keys()):
        recent_facts[cid] = _retag_legacy_day_facts(recent_facts[cid])
    for cid in list(facts.keys()):
        retagged = _retag_legacy_day_facts(facts[cid])
        real, own = _split_own_day_facts(retagged)
        if own:
            facts[cid] = real
            recent_facts.setdefault(cid, []).extend(own)
            log.info("[memory] moved %d own-day entr(ies) out of long-term facts for chat %s",
                     len(own), cid)
    log.info("Loaded history for %d chat(s).", len(conversation_history))


# Captured by _post_init so worker threads can hand saves back to the event loop
# instead of iterating live state dicts cross-thread (RuntimeError race).
_MAIN_LOOP = None


def _serialize_state() -> str:
    """Build the JSON payload. MUST run on the thread that owns the mutations
    (the event loop, normally) — iterating the live dicts from a worker thread
    while handlers mutate them raises 'dict changed size during iteration'."""
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
        "beliefs": {str(k): v for k, v in beliefs.items()},
        "recommendations": {str(k): v for k, v in recommendations.items()},
        "rec_seq": {str(k): v for k, v in rec_seq.items()},
        "next_goals": {str(k): v for k, v in next_goals.items()},
        "milestones": {str(k): v for k, v in milestones.items()},
        "pinned": {str(k): v for k, v in pinned.items()},
        "boundaries": {str(k): v for k, v in boundaries.items()},
        "current_vibe": {str(k): v for k, v in current_vibe.items()},
        "vent_mode": {str(k): v for k, v in vent_mode.items()},
        "user_energy": {str(k): v for k, v in user_energy.items()},
        "unsent_drafts": {str(k): v for k, v in unsent_drafts.items()},
        "nudge_budget": {str(k): v for k, v in nudge_budget.items()},
        "quiet_until": {str(k): v for k, v in quiet_until.items()},
        "quiet_windows": {str(k): v for k, v in quiet_windows.items()},
        "away": {str(k): v for k, v in away.items()},
        "voice_reply": {str(k): v for k, v in voice_reply.items()},
        "model_overrides": model_overrides,
        "setting_overrides": setting_overrides,
        "user_location": {str(k): v for k, v in user_location.items()},
        "seen_incidents": {str(k): list(v) for k, v in seen_incidents.items()},
        "group_cursor": {str(k): v for k, v in group_cursor.items()},
        "group_bot_sends_today": {str(k): v for k, v in group_bot_sends_today.items()},
        "feedback_log": {str(k): v[-50:] for k, v in feedback_log.items()},
        "closeness": {str(k): v for k, v in closeness.items()},
        "open_threads": {str(k): v for k, v in open_threads.items()},
        "error_counts": {cat: list(ts) for cat, ts in list(_error_counts.items())},
        "llm_stats": dict(_llm_stats),
    }
    return json.dumps(data)


def _write_state_text(payload: str):
    tmp = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(STATE_FILE)


def _write_state():
    _write_state_text(_serialize_state())


def _atomic_write_text(path: Path, text: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


_save_scheduled = False

def save_state():
    """Save bot state. On the event loop: debounce, serialize on the loop (safe),
    write the file in a thread. From a worker thread: hand off to the loop — the
    old direct write iterated live dicts cross-thread and could hit
    'dict changed size during iteration'. At startup/shutdown (no loop running):
    write immediately."""
    global _save_scheduled
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        if _MAIN_LOOP is not None and _MAIN_LOOP.is_running():
            try:
                _MAIN_LOOP.call_soon_threadsafe(save_state)
                return
            except RuntimeError:
                pass  # loop mid-shutdown — fall through to a direct write
        _write_state()
        return
    if _save_scheduled:
        return
    _save_scheduled = True
    async def _deferred():
        global _save_scheduled
        await asyncio.sleep(0.5)
        _save_scheduled = False
        try:
            payload = _serialize_state()  # on the loop — no cross-thread iteration
            await asyncio.to_thread(_write_state_text, payload)
        except Exception as e:
            log.error("[state] deferred save failed: %s", e)
    loop.create_task(_deferred())


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


# --- Own-day memory provenance (must be above load_state which uses them) ---
_OWN_DAY_PREFIX = "[own-day"
OWN_DAYS_KEPT = _env_int("OWN_DAYS_KEPT", "5")
_LEGACY_DAY_RE = re.compile(r"^\[[A-Z][a-z]{2} \d{1,2}\] (?!Voice note:)")


def _is_own_day_fact(f) -> bool:
    return isinstance(f, str) and f.startswith(_OWN_DAY_PREFIX)


def _split_own_day_facts(fl):
    """(real_facts, own_day_entries) — keeps LLM memory consumers away from her fiction."""
    fl = fl or []
    return ([f for f in fl if not _is_own_day_fact(f)],
            [f for f in fl if _is_own_day_fact(f)])


def _retag_legacy_day_facts(fl):
    """Migration: day archives used to be stored as plain '[Jul 09] …' facts,
    indistinguishable from real user facts. Retag them with the own-day prefix."""
    return [f"[own-day {f[1:]}" if isinstance(f, str) and _LEGACY_DAY_RE.match(f) else f
            for f in (fl or [])]


load_state()

if _CONFIG_WARNINGS:
    log.warning("[config] %d warning(s) at startup: %s",
                len(_CONFIG_WARNINGS), "; ".join(_CONFIG_WARNINGS))

# --- Inside jokes ---
JOKES_FILE = BASE_DIR / "jokes.json"
WARDROBE_FILE = BASE_DIR / "wardrobe.json"


def load_jokes():
    global inside_jokes
    if JOKES_FILE.exists():
        try:
            inside_jokes = json.loads(JOKES_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("[jokes] load failed: %s", e)
            _count_error("load")
            inside_jokes = []


def save_jokes():
    _atomic_write_text(JOKES_FILE, json.dumps(inside_jokes, indent=2))


def _new_joke_id() -> int:
    return (max((j["id"] for j in inside_jokes), default=0)) + 1


def _available_jokes() -> list:
    """Jokes whose cooldown has expired and are eligible to be surfaced."""
    now = time.time()
    return [j for j in inside_jokes
            if now - j.get("last_used", 0) >= j.get("cooldown_days", 7) * 86400]


def _check_joke_used(text: str):
    """Scan a response and mark any joke whose phrase appears as recently used."""
    if not inside_jokes:
        return
    low = text.lower()
    changed = False
    for j in inside_jokes:
        if j["phrase"].lower() in low:
            j["last_used"] = time.time()
            changed = True
    if changed:
        save_jokes()


load_jokes()


# --- Wardrobe ---
def load_wardrobe():
    if WARDROBE_FILE.exists():
        try:
            wardrobe.update(json.loads(WARDROBE_FILE.read_text(encoding="utf-8")))
        except Exception as e:
            log.warning("[wardrobe] load failed: %s", e)
            _count_error("load")


def save_wardrobe():
    _atomic_write_text(WARDROBE_FILE, json.dumps(wardrobe, indent=2))


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
    "busy":       ("Texting mode: they're busy. Shorter replies, no long questions. "
                   "Don't pile up messages. One thought at a time, low-demand."),
    "working":    ("Texting mode: they're working. Keep it brief and non-disruptive. "
                   "Short replies, no multi-part questions, nothing that needs a long answer."),
    "driving":    ("Texting mode: they're driving. Ultra-short replies only if they text first. "
                   "Don't start conversations. Safety first."),
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


def _in_quiet_window(now, windows) -> bool:
    """True if `now` (datetime) falls within any recurring quiet window.

    Each window: {"dow": int (0=Mon..6=Sun), "start": int (minutes from midnight),
    "end": int (minutes from midnight)}.  Midnight crossing supported:
    start > end means the window spans into the next day.
    """
    if not windows:
        return False
    cur_dow = now.weekday()  # 0=Mon
    cur_min = now.hour * 60 + now.minute
    for w in windows:
        wdow = w["dow"]
        ws = w["start"]
        we = w["end"]
        if ws <= we:
            if cur_dow == wdow and ws <= cur_min < we:
                return True
        else:
            # crosses midnight: check same-day after start, or next-day before end
            if cur_dow == wdow and cur_min >= ws:
                return True
            prev_dow = (cur_dow - 1) % 7
            if prev_dow == wdow and cur_min < we:
                return True
    return False


def _compute_closeness(days_active: int, message_count: int,
                       milestones_count: int, beliefs_count: int) -> tuple[float, str]:
    """Pure function: derive closeness score and bucket from relationship signals.

    Returns (score 0-1, bucket label). Bucket thresholds:
      <0.33 = "getting to know each other"
      <0.66 = "comfortable"
      >=0.66 = "deeply familiar"
    """
    d = min(days_active / 60, 1.0) * 0.3
    m = min(message_count / 500, 1.0) * 0.3
    ms = min(milestones_count / 8, 1.0) * 0.2
    b = min(beliefs_count / 6, 1.0) * 0.2
    score = round(d + m + ms + b, 3)
    if score >= 0.66:
        bucket = "deeply familiar"
    elif score >= 0.33:
        bucket = "comfortable"
    else:
        bucket = "getting to know each other"
    return score, bucket


def _is_away(chat_id: int) -> bool:
    """True if the user has an active /away (or auto-detected away)."""
    aw = away.get(chat_id)
    if not aw:
        return False
    exp = aw.get("expires")
    if exp and time.time() > exp:
        away.pop(chat_id, None)
        save_state()
        return False
    return True


def _clear_away(chat_id: int) -> dict | None:
    """Remove away state; returns the old entry (or None if not away)."""
    return away.pop(chat_id, None)


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
            log.warning("[payments] load failed: %s", e)
            _count_error("load")
            payments = []


def save_payments():
    _atomic_write_text(PAYMENTS_FILE, json.dumps(payments, indent=2))


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
            log.warning("[reminders] load failed: %s", e)
            _count_error("load")
            reminders = []


def save_reminders():
    _atomic_write_text(REMINDERS_FILE, json.dumps(reminders, indent=2))


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
            log.warning("[cron] load failed: %s", e)
            _count_error("load")
            cron_jobs = []


def save_cron_jobs():
    _atomic_write_text(CRON_FILE, json.dumps(cron_jobs, indent=2))


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
            # Silent None here made every admin command fail closed for the owner
            # with zero signal — say why, loudly, once per call site that cares.
            log.warning("[config] OWNER_CHAT_ID is not numeric (%r) — owner disabled, "
                        "admin commands and proactive messages will not work",
                        OWNER_CHAT_ID_ENV)
            return None
    if OWNER_FILE.exists():
        try:
            return int(OWNER_FILE.read_text().strip())
        except ValueError:
            return None
    return None


def set_owner(chat_id: int):
    # A group chat must never capture proactive messaging (heartbeats, follow-ups).
    # Central guard: there are seven call sites and all of them claim on first
    # interaction — refusing negative ids here closes every one (GROUP_CHAT_DESIGN.md §6).
    if chat_id < 0:
        return
    if not OWNER_CHAT_ID_ENV:
        OWNER_FILE.write_text(str(chat_id))


def triggered_lore(scan_text: str):
    low = scan_text.lower()
    out = []
    seen: set[str] = set()
    for entry in LORE:
        hit = entry["constant"] or any(
            re.search(r"\b" + re.escape(k) + r"\b", low) for k in entry["keys"]
        )
        if hit and entry["content"] not in seen:
            seen.add(entry["content"])
            out.append(entry["content"])
    return out


_MEMORY_STOPWORDS = frozenset({
    "the", "and", "that", "this", "with", "from", "have", "will", "been",
    "they", "them", "their", "made", "user", "told", "said", "just", "more",
    "about", "into", "than", "also", "some", "very", "when", "what", "where",
    "your", "always", "never", "every", "would", "could", "should", "still",
    "even", "both", "only", "other", "back", "then", "well", "each",
})


def triggered_memories(scan_text: str) -> list[str]:
    entries = _read_memories()
    if not entries:
        return []
    char_name = NAME.lower() if NAME else ""
    stopwords = _MEMORY_STOPWORDS | ({char_name} if char_name else set())
    low = scan_text.lower()
    scan_words = set(re.findall(r"\b[a-z]{4,}\b", low))

    # Keyword scoring (original path — always runs)
    keyword_scored: dict[str, float] = {}
    for line in entries:
        words = {w for w in re.findall(r"\b[a-z]{4,}\b", line.lower())
                 if w not in stopwords}
        hits = len(words & scan_words)
        if hits > 0:
            keyword_scored[line] = float(hits)

    # Semantic scoring (additive — falls back silently on failure).
    # _embed_text makes a blocking HTTP call; skip it when running on the event
    # loop (assemble_messages is called from async handlers) to avoid freezing
    # all other handlers for up to 30s.  Keyword scoring still works fine.
    try:
        _loop = asyncio.get_running_loop()
        on_event_loop = True
    except RuntimeError:
        on_event_loop = False
    sem_results = semantic_recall(scan_text, entries, top_k=8) if not on_event_loop else []
    sem_scored: dict[str, float] = {}
    if sem_results:
        max_sim = max(s for s, _ in sem_results) or 1.0
        for sim, line in sem_results:
            if sim > 0.3:
                sem_scored[line] = (sim / max_sim) * 3.0

    # Merge: union of both, sum their scores
    all_lines = set(keyword_scored) | set(sem_scored)
    merged = [(keyword_scored.get(l, 0) + sem_scored.get(l, 0), l) for l in all_lines]
    merged.sort(key=lambda x: x[0], reverse=True)

    out = []
    budget = MEMORY_TOKEN_BUDGET
    for _, line in merged:
        cost = _est_tokens(line)
        if cost > budget:
            continue
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
    r = _get_session().get(url, timeout=10)
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
        log.warning("[weather] fetch failed: %s", e)


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
        value = {"score": round(valence, 3), "label": label[:160], "ts": time.time()}
        if _MAIN_LOOP:
            _MAIN_LOOP.call_soon_threadsafe(moods.__setitem__, chat_id, value)
            _MAIN_LOOP.call_soon_threadsafe(save_state)
        else:
            moods[chat_id] = value
            save_state()
        print(f"[mood] {label} ({valence:+.0f})")


async def update_mood(chat_id: int):
    if not MOOD_AUTO:
        return
    hist = conversation_history.get(chat_id, [])[-4:]
    if not hist:
        return
    uname = user_names.get(chat_id, "user")
    tail = "\n".join(f"{(NAME if m['role'] == 'assistant' else uname)}: {m['content']}" for m in hist)
    try:
        await asyncio.to_thread(_appraise_mood, chat_id, tail)
    except Exception as e:
        log.warning("[mood] appraisal failed: %s", e)


def _post_reply_analysis(chat_id: int, hist_tail: list,
                         want_mood: bool, want_note: bool, want_memory: bool):
    """Sync worker: one LLM call covering mood + user note + NPC memory.
    hist_tail is snapshotted by the caller on the event loop — never read the live
    conversation_history from this thread."""
    uname = user_names.get(chat_id, "you")
    cur = moods.get(chat_id) or {}
    gap_hours = cur.pop("_gap_hours", 0)
    gap_note = ""
    if gap_hours > 4:
        gap_note = f" Note: it's been {gap_hours:.0f}h since they last talked — factor the time gap into her state."
    tail = "\n".join(f"{(NAME if m['role'] == 'assistant' else uname)}: {m['content']}" for m in hist_tail)
    sys_prompt = (
        f"You analyze the latest exchange between {uname} and {NAME}, and you track {NAME}'s "
        f"emotional state across the conversation. Output ONLY a JSON object — no prose, no code "
        f"fences — with exactly these keys:\n"
        f'"mood": short, specific, in-character description of how {NAME} feels right now and why '
        f"(e.g. 'pissed off, some guy doored her on her route' or 'cozy and content, slow morning'). "
        f"Moods persist: if nothing notable happened, stay close to the current mood rather than "
        f"resetting to neutral.\n"
        f'"valence": integer from -3 to 3 for that mood.\n'
        f'"user_note": if {uname} mentioned something specific and upcoming — an event, appointment, '
        f"deadline, worry, or plan that would be natural to ask about later — a single brief "
        f"third-person note (e.g. 'has a job interview on Tuesday'). Otherwise null.\n"
        f'"user_note_date": if the user_note refers to a specific or inferable day '
        f"('Tuesday', 'tomorrow', 'next week' means its first day), that date as YYYY-MM-DD. "
        f"Otherwise null.\n"
        f'"memory": if the exchange revealed something notable about a third party, NPC, or '
        f"relationship dynamic (not about {uname} themselves) worth remembering — one brief memory "
        f"line in third person (e.g. 'Bob reacted badly when {uname} mentioned their ex'). "
        f"Otherwise null.\n"
        f'"memory_quote": the EXACT sentence or clause from {uname}\'s messages that supports '
        f"the memory you extracted. Must be a verbatim substring of what {uname} said — not "
        f"paraphrased, not from {NAME}'s lines. null if memory is null.\n"
        f'"memory_confidence": integer 1-10, how confident you are this is worth remembering '
        f"long-term (10 = clearly important fact, 1 = trivial/ambiguous). null if memory is null.\n"
        f'"availability": if {uname} EXPLICITLY stated they are driving, working, or busy '
        f'(e.g. "gotta drive", "heading into a meeting", "at work rn"), return '
        f'"driving"|"working"|"busy". ONLY when clearly stated — do not infer. Otherwise null.\n'
        f"CRITICAL for user_note and memory: extract ONLY from what {uname} actually said. "
        f"{NAME}'s own lines describe her fictional day-to-day life — never turn {NAME}'s own "
        f"statements, events, or plans into notes or memories; they are not real-world facts."
    )
    if THREADS_ENABLED:
        sys_prompt += (
            f'\n"thread_update": object with "add" (string|null — a new open topic/thread '
            f"between them, e.g. 'planning weekend trip') and \"resolved\" (string|null — "
            f"an existing thread that was wrapped up this exchange). Both null if nothing changed."
        )
    if JOKE_CANDIDATES:
        sys_prompt += (
            f'\n"joke_candidate": object with "phrase", "meaning", "tone" IF both parties '
            f"laughed at something with callback potential (could become a recurring bit). "
            f"Extremely strict — most exchanges produce null. null otherwise."
        )
    now_local = datetime.now(TZ) if TZ else datetime.now()
    user = (f"Today is {now_local.strftime('%A, %Y-%m-%d')}.\n"
            f"Current mood: {cur.get('label') or 'neutral'} (valence {round(cur.get('score', 0), 1)}).{gap_note}\n\n"
            f"Latest exchange:\n{tail}")
    raw = call_nanogpt(
        [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
        model=MOOD_MODEL,
    )
    data = _extract_json(raw)

    if want_mood:
        label = (data.get("mood") or "").strip() if isinstance(data.get("mood"), str) else ""
        try:
            valence = max(-3.0, min(3.0, float(data.get("valence"))))
        except (TypeError, ValueError):
            valence = cur.get("score", 0.0)
        if label:
            value = {"score": round(valence, 3), "label": label[:160], "ts": time.time()}
            if _MAIN_LOOP:
                _MAIN_LOOP.call_soon_threadsafe(moods.__setitem__, chat_id, value)
                _MAIN_LOOP.call_soon_threadsafe(save_state)
            else:
                moods[chat_id] = value
                save_state()
            print(f"[mood] {label} ({valence:+.0f})")

    def _clean_field(key: str) -> str:
        val = data.get(key)
        if not isinstance(val, str):
            return ""
        val = val.strip()
        return "" if re.match(r"^(none|null|no|nothing|n/a|not\b)", val.lower()) else val

    if want_note:
        note = _clean_field("user_note")
        if note:
            due = _clean_field("user_note_date")
            # Sanity: proper format, today..+1y — a hallucinated date is worse than none.
            if due:
                try:
                    d = date.fromisoformat(due)
                    if not (now_local.date() <= d <= now_local.date() + timedelta(days=366)):
                        due = ""
                except ValueError:
                    due = ""
            _append_user_note(note, due=due)
            print(f"[user-notes] added: {note}" + (f" (due {due})" if due else ""))

    if want_memory:
        mem = _clean_field("memory")
        if mem:
            quote = _clean_field("memory_quote")
            user_lines = [m["content"] for m in hist_tail if m.get("role") == "user"]
            grounded = _quote_grounded(quote, user_lines) if quote else False
            if not grounded:
                _count_error("memory_ungrounded")
                print(f"[memories] REJECTED (ungrounded): {mem}")
            else:
                try:
                    conf = max(1, min(10, int(data.get("memory_confidence", 5))))
                except (TypeError, ValueError):
                    conf = 5
                mem_meta = {
                    "ts": time.time(), "chat_id": chat_id, "origin": "auto",
                    "confidence": conf, "source": quote[:300],
                }
                if conf >= MEMORY_AUTOCONF:
                    _append_memory(mem, auto=True, meta=mem_meta)
                    print(f"[memories] added (conf={conf}): {mem}")
                else:
                    queue = _load_memory_review()
                    queue.append({"text": mem, "meta": mem_meta})
                    if len(queue) > MEMORY_REVIEW_MAX:
                        dropped = queue.pop(0)
                        _memory_log("REVIEW-DROP", dropped.get("text", ""), "queue full")
                    _save_memory_review(queue)
                    _memory_log("REVIEW-QUEUE", mem, f"conf={conf}")
                    print(f"[memories] queued for review (conf={conf}): {mem}")

    avail = _clean_field("availability").lower()
    if avail in ("driving", "working", "busy") and not _is_away(chat_id):
        exp = time.time() + AWAY_AUTO_HOURS * 3600 if AWAY_AUTO_HOURS > 0 else None
        value = {
            "reason": avail, "since": time.time(),
            "origin": "auto", "expires": exp,
        }
        if _MAIN_LOOP:
            _MAIN_LOOP.call_soon_threadsafe(away.__setitem__, chat_id, value)
            _MAIN_LOOP.call_soon_threadsafe(save_state)
        else:
            away[chat_id] = value
            save_state()
        print(f"[away] auto-set: {avail} (expires in {AWAY_AUTO_HOURS}h)")

    if THREADS_ENABLED:
        tu = data.get("thread_update")
        if isinstance(tu, dict):
            resolved = (tu.get("resolved") or "").strip()
            add = (tu.get("add") or "").strip()
            threads = open_threads.get(chat_id, [])
            changed = False
            if resolved:
                threads = [t for t in threads if resolved.lower() not in t.lower()]
                changed = True
            if add and add.lower() not in ("null", "none") and len(threads) < 3:
                threads.append(add[:200])
                changed = True
            if changed:
                def _set_threads():
                    open_threads[chat_id] = threads
                    save_state()
                if _MAIN_LOOP:
                    _MAIN_LOOP.call_soon_threadsafe(_set_threads)
                else:
                    _set_threads()
                print(f"[threads] updated: {threads}")

    if JOKE_CANDIDATES:
        jc = data.get("joke_candidate")
        if isinstance(jc, dict) and jc.get("phrase"):
            entry = {
                "text": f"joke candidate: \"{jc['phrase']}\" — {jc.get('meaning', '')} ({jc.get('tone', '')})",
                "meta": {"ts": time.time(), "chat_id": chat_id, "origin": "joke-candidate",
                         "confidence": 5, "source": jc.get("phrase", "")[:80]},
            }
            queue = _load_memory_review()
            queue.append(entry)
            if len(queue) > MEMORY_REVIEW_MAX:
                queue.pop(0)
            _save_memory_review(queue)
            print(f"[jokes] candidate queued for review: {jc['phrase']}")


async def post_reply_analysis(chat_id: int, user_msg: str):
    """One combined background pass per exchange: mood + user note + NPC memory.

    Replaces three separate LLM calls — on a phone connection the side calls
    compete with the user-facing reply for bandwidth, so fewer round-trips
    matter more than prompt purity.
    """
    is_text = bool(user_msg) and not user_msg.startswith("[sent ")
    want_mood = MOOD_AUTO and bool(conversation_history.get(chat_id))
    want_note = is_text and len(user_msg.split()) >= 4
    want_memory = MEMORY_AUTO and is_text and any(
        w not in _MEMORY_STOPWORDS for w in re.findall(r"\b[a-z]{4,}\b", user_msg.lower()))
    if not (want_mood or want_note or want_memory):
        return
    try:
        # Snapshot the history tail ON the loop — the worker must not slice the live
        # list while handlers keep appending to it.
        hist_tail = list(conversation_history.get(chat_id, [])[-4:])
        await asyncio.to_thread(_post_reply_analysis, chat_id, hist_tail,
                                want_mood, want_note, want_memory)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.warning("[analysis] post-reply pass failed: %s", e)
        _count_error("memory")


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


# --- Self-image (core beliefs) + recommendation/outcome tracking ---
def _today_messages(chat_id: int) -> list:
    """Verbatim messages from conversation_history with a timestamp in the local 'today'."""
    now = datetime.now(TZ) if TZ else datetime.now()
    start = datetime.combine(now.date(), dtime(0, 0), tzinfo=TZ) if TZ else datetime.combine(now.date(), dtime(0, 0))
    cutoff = start.timestamp()
    return [m for m in conversation_history.get(chat_id, []) if m.get("ts", 0) >= cutoff]


def _seed_beliefs() -> dict:
    """Derive ~BELIEF_TRAITS core self-image traits + baseline (anchor) scores from the character card."""
    sys = (
        f"Based on this character description of {NAME}, identify {BELIEF_TRAITS} core "
        f"personality traits that describe how {NAME} sees herself — single words or short "
        f"phrases (e.g. \"guarded\", \"fiercely independent\", \"insecure about her work\"). "
        f"For each, give a baseline score from 1-10 for how strongly that trait shows, based on "
        f"the character description. Respond with ONLY a JSON object: "
        f'{{"trait name": score, ...}}. No prose, no code fences.'
    )
    raw = call_nanogpt(
        [{"role": "system", "content": sys}, {"role": "user", "content": SYSTEM_PROMPT_RAW[:4000]}],
        model=SUMMARY_MODEL,
    )
    data = _extract_json(raw)
    items = {}
    for trait, score in data.items():
        if not isinstance(trait, str) or not trait.strip():
            continue
        try:
            v = max(1.0, min(10.0, float(score)))
        except (TypeError, ValueError):
            continue
        items[trait.strip()[:60]] = {"score": round(v, 1), "anchor": round(v, 1)}
        if len(items) >= BELIEF_TRAITS:
            break
    return items


async def reflect(chat_id: int):
    """Nightly: gently update her self-image (bounded by her card-derived baseline) and check
    on past recommendations against today's conversation."""
    uname = user_names.get(chat_id, "you")
    items = beliefs.get(chat_id, {}).get("items")
    if not items:
        try:
            items = await asyncio.to_thread(_seed_beliefs)
        except Exception as e:
            log.warning("[reflect] belief seeding failed: %s", e)
            items = {}
        if items:
            beliefs[chat_id] = {"items": items}
            save_state()
            print(f"[reflect] Seeded self-image for chat {chat_id}: {list(items)}")

    todays = _today_messages(chat_id)
    if not items or not todays:
        return

    convo = "\n".join(
        f"{(NAME if m['role'] == 'assistant' else uname)}: {m['content']}" for m in todays
    )
    open_recs = [r for r in recommendations.get(chat_id, []) if r["status"] == "open"]
    belief_lines = "\n".join(f"- {t}: {d['score']}/10" for t, d in items.items())
    rec_lines = "\n".join(f"- (#{r['id']}) {r['text']}" for r in open_recs) or "(none)"
    cur_goal = (next_goals.get(chat_id) or "").strip()

    existing_milestones = milestones.get(chat_id) or []
    ms_lines = (", ".join(m["text"] for m in existing_milestones[-10:])
                if existing_milestones else "(none yet)")
    sys = (
        f"You help {NAME} do a private nightly reflection on her day with {uname}. You're given "
        f"her current self-image (a handful of traits she rates herself on, 1-10), any open "
        f"things she's recommended or said she'd check on, her current next-conversation goal, "
        f"today's conversation, and a list of relationship milestones already recorded. "
        f"Update her self-image based on how she actually behaved today — small shifts only, "
        f"not dramatic swings. Note any NEW recommendation or piece of advice she gave {uname} "
        f"today that she'd plausibly want to follow up on later. For any OPEN item, say whether "
        f"today's conversation reveals an outcome (good, bad, or still open/no update).\n\n"
        f"Also maintain a \"next_goal\": one specific, concrete thing {NAME} wants to bring up, "
        f"ask about, or do the next time she talks to {uname} -- a thread to pick up so the next "
        f"conversation doesn't start cold (e.g. \"ask if he ate before his shift\" or \"tell him "
        f"about the thing her grandfather used to say about the Astros\"). If today's conversation already "
        f"covered the current goal, replace it with a fresh one; otherwise keep it or update it. "
        f"Leave it empty only if genuinely nothing comes to mind. Keep it short (<= 100 "
        f"characters).\n\n"
        f"Also look for relationship milestones — things that happened for the FIRST TIME in "
        f"today's conversation that aren't in the existing list: first time he opened up about "
        f"something painful, first real disagreement they worked through, first time she admitted "
        f"something she doesn't usually say, first inside joke, first time he asked for her "
        f"opinion on something big. Be selective — only flag genuine firsts that will matter "
        f"later. Keep each one short (one brief phrase). Return an empty list if today had "
        f"nothing new.\n\n"
        f"Respond with ONLY a JSON object:\n"
        f'{{"beliefs": {{"trait": score, ...}}, '
        f'"new_recommendations": ["..."], '
        f'"resolved": [{{"id": <int>, "outcome": "good"|"bad"|"open_loop", "note": "..."}}], '
        f'"next_goal": "...", '
        f'"milestones": ["first time he ..."]}}\n'
        f"Keep the exact same trait names as given. No prose, no code fences."
    )
    user = (f"SELF-IMAGE:\n{belief_lines}\n\nOPEN ITEMS:\n{rec_lines}\n\n"
            f"CURRENT NEXT-CONVERSATION GOAL: {cur_goal or '(none)'}\n\n"
            f"EXISTING MILESTONES: {ms_lines}\n\n"
            f"TODAY'S CONVERSATION:\n{convo}")
    raw = await asyncio.to_thread(
        call_nanogpt, [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        SUMMARY_MODEL,
    )
    data = _extract_json(raw)

    new_scores = data.get("beliefs") or {}
    for trait, d in items.items():
        if trait not in new_scores:
            continue
        try:
            v = float(new_scores[trait])
        except (TypeError, ValueError):
            continue
        anchor = d["anchor"]
        v = max(anchor - BELIEF_DRIFT_MAX, min(anchor + BELIEF_DRIFT_MAX, v))
        d["score"] = round(max(1.0, min(10.0, v)), 1)

    recs = recommendations.setdefault(chat_id, [])
    seq = rec_seq.get(chat_id, 1)
    for text in data.get("new_recommendations") or []:
        if isinstance(text, str) and text.strip():
            recs.append({"id": seq, "text": text.strip()[:200], "ts": time.time(),
                         "status": "open", "outcome": None, "note": ""})
            seq += 1
    rec_seq[chat_id] = seq

    by_id = {r["id"]: r for r in recs}
    for item in data.get("resolved") or []:
        try:
            rid = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        r = by_id.get(rid)
        if not r or r["status"] != "open":
            continue
        outcome = item.get("outcome")
        if outcome in ("good", "bad"):
            r["status"] = "resolved"
            r["outcome"] = outcome
            r["note"] = (item.get("note") or "")[:200]

    if len(recs) > RECS_MAX:
        open_ones = [r for r in recs if r["status"] == "open"]
        resolved = sorted((r for r in recs if r["status"] != "open"), key=lambda r: r["ts"], reverse=True)
        keep_resolved = max(0, RECS_MAX - len(open_ones))
        recs[:] = sorted(open_ones + resolved[:keep_resolved], key=lambda r: r["ts"])

    goal = data.get("next_goal")
    if isinstance(goal, str):
        next_goals[chat_id] = goal.strip()[:200]

    new_ms = data.get("milestones") or []
    if isinstance(new_ms, list):
        ms_list = milestones.setdefault(chat_id, [])
        existing_texts = {m["text"].lower() for m in ms_list}
        for text in new_ms:
            if isinstance(text, str) and text.strip() and text.strip().lower() not in existing_texts:
                ms_list.append({"text": text.strip()[:150], "ts": time.time()})
                existing_texts.add(text.strip().lower())
        if len(ms_list) > MILESTONES_MAX:
            ms_list[:] = ms_list[-MILESTONES_MAX:]

    save_state()
    print(f"[reflect] Updated self-image and {len(recs)} tracked item(s) for chat {chat_id}.")


def belief_note(chat_id: int) -> str:
    items = beliefs.get(chat_id, {}).get("items")
    if not items:
        return ""
    desc = ", ".join(f"{t} ({d['score']:.0f}/10)" for t, d in items.items())
    note = (f"# Self-image\n{NAME}'s sense of herself lately: {desc}. This shapes how she carries "
            f"herself day to day — don't recite it or the numbers, just let it inform her tone "
            f"and reactions.")
    open_recs = [r for r in recommendations.get(chat_id, []) if r["status"] == "open"]
    if open_recs:
        items_txt = "; ".join(r["text"] for r in open_recs[:3])
        note += (f"\n\nThings she's been wondering how they turned out: {items_txt}. If it comes "
                 f"up naturally, she might ask about it — but don't force it.")
    if not THREADS_ENABLED:
        goal = (next_goals.get(chat_id) or "").strip()
        if goal:
            note += (f"\n\nSomething on her mind for next time: {goal}. Let it surface naturally if "
                     f"it fits — don't force it in.")
    ms_list = milestones.get(chat_id) or []
    if ms_list:
        recent_ms = "; ".join(m["text"] for m in ms_list[-5:])
        note += (f"\n\nMilestones in this relationship so far: {recent_ms}. These are part of "
                 f"their shared history — she knows them, doesn't need to announce them.")
    return note


# Provenance tag for the character's own generated day events archived into
# recent_facts by _rotate_day_context. These are HER generated fiction, not user
# facts — every memory consumer must treat them differently, or she asserts her
def memory_block(chat_id: int, uname: str) -> str:
    """Long-term (durable) + recent (last ~week) memory injected every request."""
    blocks = []

    parts = []
    summ = (summaries.get(chat_id) or "").strip()
    if summ:
        parts.append(f"How you remember things with {uname} so far:\n{summ}")
    fts, own_long = _split_own_day_facts(facts.get(chat_id))
    if fts:
        parts.append(f"Things you know about {uname}:\n" + "\n".join("- " + f for f in fts))
    if parts:
        blocks.append("# What you remember\n\n" + "\n\n".join(parts))

    rparts = []
    rsumm = (recent_summaries.get(chat_id) or "").strip()
    if rsumm:
        rparts.append(rsumm)
    rfts, own_days = _split_own_day_facts(recent_facts.get(chat_id))
    if rfts:
        rparts.append("Recent specifics:\n" + "\n".join("- " + f for f in rfts))
    if rparts:
        blocks.append("# What's been going on lately\n\n" + "\n\n".join(rparts))

    own_days = (own_long + own_days)[-OWN_DAYS_KEPT:]
    if own_days:
        lines = []
        for d in own_days:
            body = d[len(_OWN_DAY_PREFIX):].lstrip()  # "Jul 09] event text"
            lines.append("- " + body.replace("]", ":", 1))
        blocks.append(
            f"# Your own recent days\n"
            f"Things that happened in YOUR life on recent days — your own day-to-day, "
            f"NOT shared memories with {uname} and NOT things {uname} told you. Never "
            f"recall these as conversations, plans, or moments you had with {uname}:\n"
            + "\n".join(lines)
        )

    return "\n\n".join(blocks)


def assemble_messages(chat_id: int, latest_user_content: str, image_data_url: str = None,
                      inner_voice: str = None, group: bool = False):
    """Build the OpenAI-style message list the way SillyTavern layers a card.

    group=True (GROUP_CHAT_DESIGN.md §7): capabilities shrink to the react tag, a
    group-context block is added, and the two blocks that would leak private 1:1
    state in front of a third party — user_notes.txt and inside jokes — are omitted.
    Everything else keyed by chat_id is the group's own state and stays."""
    uname = user_names.get(chat_id, "you")
    history = conversation_history.get(chat_id, [])

    messages = [{"role": "system", "content": fill(SYSTEM_PROMPT_RAW, NAME, uname)}]

    if SETTING:
        messages.append({
            "role": "system",
            "content": "# Current setting\n" + fill(SETTING, NAME, uname),
        })

    # Stable character background: people in her life and ongoing projects.
    people = _read_people()
    if people:
        messages.append({"role": "system", "content": f"# People in {NAME}'s life\n{people}"})

    projects = _read_projects()
    if projects:
        messages.append({"role": "system", "content": (
            f"# What {NAME} has going on / is working on\n{projects}"
        )})

    life_arc = _read_life_arc()
    if life_arc:
        messages.append({"role": "system", "content": (
            f"# {NAME}'s current life arc\n{life_arc}\n"
            f"Draw on this naturally in conversation — it's the texture of her life right now."
        )})

    if ATLAS:
        picks = random.sample(ATLAS, min(ATLAS_SAMPLE, len(ATLAS)))
        messages.append({
            "role": "system",
            "content": (f"# Local places\nReal spots {NAME} knows and might naturally reference "
                        f"if it fits — don't force them, and don't invent fake businesses when "
                        f"a real area works: " + ", ".join(picks) + "."),
        })

    cap_lines = [
        f"# Capabilities\nA couple of things you can do with tags, used naturally and "
        f"sparingly — never announce them, just include the tag:",
        f"- React to {uname}'s message with a single emoji, like tapping a chat bubble: "
        f"[react: 👍]. Pick from: {REACTION_HINTS}. Always include your text reply too — "
        f"a reaction never replaces a message, it goes with it.",
    ]
    if not group and selfie_ready():
        cap_lines.append(
            f"- Send a selfie when it fits (e.g. {uname} asks for a pic, or to share a moment): "
            f"[selfie: a short visual description — your pose, expression, surroundings]. "
            f"If you describe what the selfie looks like in your text (the setting, lighting, "
            f"expression, what she's wearing), put those same details in the tag — the tag is "
            f"what generates the image, so they must match. Keep it casual, in-character, SFW, "
            f"and don't overuse it."
        )
    if not group and meme_ready():
        cap_lines.append(
            f"- Send a meme when the moment genuinely calls for it (a joke, a shared "
            f"reaction, something {uname} said that's begging for one): "
            f"[meme: top caption text | bottom caption text]. Keep both lines short and "
            f"punchy — this is classic meme-macro format, not a sentence. Don't overuse it."
        )
    if not group and SEARCH_ENABLED:
        cap_lines.append(
            f"- Look something up online when you genuinely don't know something and it'd "
            f"help — a fact, something {uname} mentioned, your own curiosity. Add "
            f"[search: your query] at the end of your reply on its own line. Don't write a "
            f"separate lead-in about looking it up — just reply naturally and include the tag; "
            f"the result will come back and you can follow up then."
        )
    if not group:
        cap_lines.append(
            f"- If {uname} disputes something you remembered ('that never happened', "
            f"'I never said that', 'that's wrong'), include [memcheck: short description "
            f"of what's disputed]. This lets them see the exact memory and fix it."
        )
    messages.append({"role": "system", "content": "\n".join(cap_lines)})

    if group:
        peers = ", ".join(GROUP_PEERS) if GROUP_PEERS else "a couple of other people"
        peer_lines = ""
        if GROUP_PEER_NOTES:
            peer_lines = "\n" + "\n".join(
                "- " + p.strip() for p in GROUP_PEER_NOTES.split(";") if p.strip()
            )
        messages.append({"role": "system", "content": (
            f"# Group chat\nYou're in a small group text thread with {uname} and {peers}. "
            f"To you they're all real people you know.{peer_lines}\n"
            f"Group texting rules: keep replies short (usually 1-2 bubbles); talk TO "
            f"people, not about them; messages from others appear as 'Name: text' — never "
            f"prefix your own replies with your name; you don't have to respond to "
            f"everything, it's fine to let a message pass; never answer on someone "
            f"else's behalf."
        )})

    messages += [{"role": m["role"], "content": m["content"]} for m in history]  # drop internal ts

    # Dynamic per-turn state kept close to the end, right before the final voice/style
    # instructions, so it stays salient for this specific reply.
    mem = memory_block(chat_id, uname)
    if mem:
        messages.append({"role": "system", "content": mem})

    # user_notes.txt is the private 1:1 relationship ledger — never read into group
    # prompts (GROUP_CHAT_DESIGN.md §5).
    unotes = "" if group else _read_user_notes()
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

    if vibe != "in-person":
        messages.append({"role": "system", "content": (
            f"You and {uname} are texting from different places — you're not physically "
            f"together unless the scene explicitly says so."
        )})

    aw = away.get(chat_id)
    if aw and _is_away(chat_id):
        reason = aw.get("reason", "away")
        messages.append({"role": "system", "content": (
            f"{uname} said they're away: {reason} — don't expect quick replies, "
            f"don't pile up messages."
        )})
    else:
        ret = _just_returned.pop(chat_id, None)
        if ret:
            reason = ret.get("reason", "away")
            messages.append({"role": "system", "content": (
                f"{uname} just got back from: {reason}"
            )})

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

    bnote = belief_note(chat_id)
    if bnote:
        messages.append({"role": "system", "content": bnote})

    if CLOSENESS_ENABLED:
        cl = closeness.get(chat_id)
        if cl:
            messages.append({"role": "system", "content": (
                f"[Relationship stage: you're {cl['bucket']}.]"
            )})


    pn = pinned.get(chat_id) or []
    if pn:
        messages.append({"role": "system", "content": (
            f"# Core things you know and never forget\n"
            + "\n".join("- " + p for p in pn)
        )})

    # inside_jokes is a GLOBAL list (not per-chat) — a DM's private bits must not be
    # performed in front of the group (GROUP_CHAT_DESIGN.md §5).
    avail_jokes = [] if group else _available_jokes()
    if avail_jokes:
        joke_lines = "\n".join(
            f'- "{j["phrase"]}" ({j["tone"]}): {j["meaning"]}' for j in avail_jokes
        )
        messages.append({"role": "system", "content": (
            f"# Inside jokes\nShared bits between {NAME} and {uname} — use them sparingly "
            f"and only when they genuinely fit the moment. Not every message:\n{joke_lines}"
        )})

    # Feedback-miss: one-turn note after a 👎 reaction
    if FEEDBACK_REACTIONS and chat_id in _feedback_miss:
        _feedback_miss.discard(chat_id)
        messages.append({"role": "system", "content": (
            f"[That last message didn't land — recalibrate, don't apologize.]"
        )})

    # Open threads (replaces single next_goal when enabled)
    if THREADS_ENABLED:
        threads = open_threads.get(chat_id, [])
        if threads:
            tl = "\n".join(f"- {t}" for t in threads[:3])
            messages.append({"role": "system", "content": (
                f"# Open threads between you two\n{tl}\n"
                f"Let them surface naturally if one fits — don't force."
            )})

    rq = _recent_questions.get(chat_id) or []
    if rq:
        messages.append({"role": "system", "content": (
            f"# Questions you've recently asked {uname} — don't repeat these:\n"
            + "\n".join("- " + q for q in rq[-5:])
        )})

    scan_text = latest_user_content + " " + " ".join(m["content"] for m in history[-8:])
    lore = triggered_lore(scan_text)
    if lore:
        messages.append({
            "role": "system",
            "content": "# Relevant background\n\n" + fill("\n\n".join(lore), NAME, uname),
        })

    mems = triggered_memories(scan_text)
    if mems:
        messages.append({"role": "system", "content": (
            "# Relevant memories\n" + "\n".join("- " + m for m in mems)
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

    # Live context (local time + weather) kept near the end so it's salient.
    messages.append({"role": "system", "content": environment_note()})

    # Today's schedule section, if a schedule file exists for this instance.
    sched = _read_schedule_today()
    if sched:
        messages.append({"role": "system", "content": f"# {NAME}'s schedule today\n{sched}"})

    # What she looks like — so she can reference her own appearance naturally.
    if SELFIE_APPEARANCE:
        messages.append({"role": "system", "content": (
            f"# Your appearance\n{SELFIE_APPEARANCE}"
        )})

    # Day context — what's been happening today; drives continuity across conversations.
    day_ctx = _read_day_context()
    if day_ctx:
        messages.append({"role": "system", "content": (
            f"# What's going on today\n{day_ctx}\n\n"
            f"Let this color what you say when it fits — don't narrate it like a list."
        )})

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

    return _trim_history_to_budget(messages, CONTEXT_TOKEN_BUDGET)


# --- NanoGPT ---
_THINK_RE = re.compile(r"(?s)<think>.*?</think>")

# Native tool-call syntax (Hermes/GLM/DeepSeek style). Models taught the bracket
# [search: …] tag sometimes render that intent in their NATIVE function-call format
# instead — which nothing downstream parses, so the raw XML reached the user verbatim
# (observed 2026-07-09, Priya: "<tool_call>\n<function=search>\n<parameter=query>
# Seattle news today July 9 2026</parameter>…"). Search-like calls are converted to
# the bracket tag so maybe_search still runs; anything else is stripped.
_TOOL_CALL_RE = re.compile(r"(?s)<tool_call>\s*(.*?)\s*</tool_call>")
_TOOL_CALL_OPEN_RE = re.compile(r"(?s)<tool_call>.*$")  # truncated/unclosed block
_FUNC_BLOCK_RE = re.compile(r"(?s)<function[=\s][^>]*>.*?(?:</function>|$)")
_FUNC_NAME_RE = re.compile(r'<function[=\s]"?([\w.\-]+)')
_TOOL_QUERY_RE = re.compile(r'(?s)<parameter[=\s]"?query"?\s*>\s*(.*?)\s*</parameter>')


def _convert_tool_call_block(block: str) -> str:
    """One native tool-call block → '[search: q]' if it's a search, else ''."""
    name = _FUNC_NAME_RE.search(block)
    if name and "search" in name.group(1).lower():
        q = _TOOL_QUERY_RE.search(block)
        if q and q.group(1).strip():
            return f"[search: {q.group(1).strip()}]"
    return ""


def _strip_native_tool_calls(text: str) -> str:
    """Convert/remove native tool-call XML so it never reaches the user as text."""
    if "<tool_call" not in text and "<function" not in text:
        return text
    sub = lambda m: _convert_tool_call_block(m.group(0))
    text = _TOOL_CALL_RE.sub(sub, text)
    text = _TOOL_CALL_OPEN_RE.sub(sub, text)
    text = _FUNC_BLOCK_RE.sub(sub, text)
    return text.strip()

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

def _fix_mojibake(text: str) -> str:
    """Reverse UTF-8 → Latin-1 → UTF-8 double-encoding from upstream SSE servers."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text

def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks emitted by reasoning models."""
    return _THINK_RE.sub("", text).strip()

def _strip_slop(text: str) -> str:
    """Remove hollow AI openers from the start of a response."""
    return _SLOP_OPENER_RE.sub("", text).strip()


_PERSONA_BREAK_RE = re.compile(
    r"(?i)\b(?:"
    r"I'?m an AI\b"
    r"|as an AI(?: language model)?"
    r"|I am an AI\b"
    r"|large language model"
    r"|I don'?t have (?:feelings|a body|personal experiences)"
    r")"
)


def _strip_persona_breaks(text: str) -> str:
    if not _PERSONA_BREAK_RE.search(text):
        return text
    sentences = re.split(r'(?<=[.!?])\s+', text)
    kept = [s for s in sentences if not _PERSONA_BREAK_RE.search(s)]
    if not kept:
        _count_error("persona_break")
        return ""
    _count_error("persona_break")
    return " ".join(kept)


def _extract_content(choice: dict) -> str:
    """Pull the reply text from a choices entry, falling back to reasoning_content."""
    msg = choice.get("message", {})
    text = (msg.get("content") or "").strip()
    if not text:
        text = (msg.get("reasoning_content") or "").strip()
    return _strip_native_tool_calls(_strip_thinking(text))

_no_stream_models: set[str] = set()

def _do_request(payload: dict, model: str, stream: bool) -> str:
    headers = {"Authorization": f"Bearer {NANOGPT_API_KEY}", "Content-Type": "application/json"}
    if stream:
        resp = _get_session().post(
            f"{NANOGPT_BASE_URL}/chat/completions", headers=headers,
            json=payload, timeout=(10, STREAM_TIMEOUT), stream=True,
        )
        try:
            if resp.status_code >= 400:
                _ = resp.content
                resp.raise_for_status()
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            for raw in resp.iter_lines():
                line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {})
                    c = delta.get("content") or ""
                    r = delta.get("reasoning_content") or ""
                    if c:
                        content_parts.append(c)
                    if r:
                        reasoning_parts.append(r)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        finally:
            resp.close()
        text = "".join(content_parts)
        if not text:
            text = "".join(reasoning_parts)
        return _fix_mojibake(_strip_native_tool_calls(_strip_thinking(text)))
    else:
        resp = _get_session().post(
            f"{NANOGPT_BASE_URL}/chat/completions", headers=headers,
            json=payload, timeout=(10, REQUEST_TIMEOUT),
        )
        resp.raise_for_status()
        return _fix_mojibake(_extract_content(resp.json()["choices"][0]))


def _one_call(messages: list, model: str) -> str:
    use_stream = model not in _no_stream_models
    payload: dict = {"model": model, "messages": messages}
    if use_stream:
        payload["stream"] = True
        payload["max_tokens"] = MAX_TOKENS
    else:
        payload["stream"] = False
    if TEMPERATURE is not None:
        payload["temperature"] = TEMPERATURE
    try:
        return _do_request(payload, model, stream=use_stream)
    except requests.exceptions.HTTPError as e:
        if use_stream and getattr(e.response, "status_code", 0) == 400:
            log.warning("[model] %s rejected streaming, retrying without", model)
            _no_stream_models.add(model)
            payload["stream"] = False
            payload.pop("max_tokens", None)
            return _do_request(payload, model, stream=False)
        raise


_CHAT_RETRIES = 2        # attempts per model before moving to the next
_RETRY_BACKOFF = (2, 4)  # seconds to wait between retries
_CALL_BUDGET = 150       # max wall-clock seconds on the primary before forcing fallback

def call_nanogpt(messages: list, model: str = None, fallback: str = None) -> str:
    """Try each model up to _CHAT_RETRIES times with backoff; fall to fallback on transient errors."""
    models = [model or NANOGPT_MODEL]
    if fallback and fallback not in models:
        models.append(fallback)
    last_err = None
    t0 = time.time()
    for i, m in enumerate(models):
        for attempt in range(_CHAT_RETRIES):
            if time.time() - t0 > _CALL_BUDGET and i < len(models) - 1:
                log.warning("[model] %s: budget exceeded (%.0fs), falling back to %s",
                           m, time.time() - t0, models[i + 1])
                _count_error("api")
                _count_error("fallback")
                break
            try:
                result = _one_call(messages, m)
                _track_llm_usage(messages, result)
                return result
            except (requests.exceptions.HTTPError, requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError) as e:
                last_err = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                transient = status is None or status == 429 or 500 <= status < 600
                if not transient:
                    raise
                if attempt < _CHAT_RETRIES - 1:
                    wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                    log.warning("[model] %s transient error (%s), retry %d/%d in %ds...",
                               m, status or e.__class__.__name__, attempt + 1, _CHAT_RETRIES - 1, wait)
                    _count_error("api")
                    time.sleep(wait)
                elif i < len(models) - 1:
                    log.warning("[model] %s failed after %d attempts; falling back to %s",
                               m, _CHAT_RETRIES, models[i + 1])
                    _count_error("api")
                    _count_error("fallback")
    raise last_err


_replies_in_flight = 0  # gates optional side calls (auto-react) off active replies

async def generate_reply(messages: list, model: str = None, fallback: str = None) -> str:
    global _replies_in_flight
    loop = asyncio.get_running_loop()
    _replies_in_flight += 1
    try:
        return await loop.run_in_executor(_REPLY_POOL, call_nanogpt, messages, model, fallback)
    finally:
        _replies_in_flight -= 1


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
    """Pull [react: ..], [selfie: ..], and [meme: ..] tags out, return
    (clean_text, reaction, selfie_hint, meme_caption). meme_caption is a (top, bottom)
    tuple or None."""
    reaction = None
    rm = re.search(r"\[react:\s*([^\]]+?)\]", text, re.IGNORECASE)
    if rm:
        reaction = norm_emoji(rm.group(1))
        text = re.sub(r"\[react:\s*[^\]]+?\]", "", text, flags=re.IGNORECASE)
    selfie_hint = None
    sm = re.search(r"\[selfie:\s*(.*?)\]", text, re.IGNORECASE | re.DOTALL)
    if sm:
        selfie_hint = sm.group(1).strip()
        text = re.sub(r"\[selfie:\s*.*?\]", "", text, flags=re.IGNORECASE | re.DOTALL)
    meme_caption = None
    mm = re.search(r"\[meme:\s*(.*?)\]", text, re.IGNORECASE | re.DOTALL)
    if mm:
        parts = mm.group(1).split("|", 1)
        meme_caption = (parts[0].strip(), parts[1].strip() if len(parts) > 1 else "")
        text = re.sub(r"\[meme:\s*.*?\]", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Safety net: a [search: ..] tag should already be consumed by maybe_search, but if a
    # regenerated reply emits another one, strip it rather than leak the literal tag.
    sr = re.search(r"\[search:\s*.*?\]", text, re.IGNORECASE | re.DOTALL)
    if sr:
        text = re.sub(r"\[search:\s*.*?\]", "", text, flags=re.IGNORECASE | re.DOTALL)
    if reaction or sm or mm or sr:
        text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip(), reaction, selfie_hint, meme_caption


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
        result = await asyncio.wait_for(
            asyncio.to_thread(
                call_nanogpt,
                [{"role": "system", "content": sys_msg},
                 {"role": "user", "content": "\n\n".join(ctx_parts)}],
                model=INNER_VOICE_MODEL,
            ),
            timeout=8.0,
        )
        return result.strip()
    except asyncio.TimeoutError:
        log.warning("[inner-voice] timed out, skipping")
        return ""
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
    if _replies_in_flight:
        return  # never compete with an active reply for bandwidth
    try:
        emoji = await asyncio.to_thread(_decide_reaction, user_message)
        if emoji and emoji in ALLOWED_REACTIONS:
            await update.message.set_reaction(emoji)
            print("[react-auto] applied", emoji)
    except Exception as e:
        log.warning("[react-auto] failed: %s", e)


def _typing_delay_secs(text: str) -> float:
    """Simulated typing delay: word count at TYPING_WPM, clamped to [min, max], ±20% jitter."""
    if not TYPING_DELAY:
        return 0.0
    words = max(1, len(text.split()))
    secs = (words / TYPING_WPM) * 60
    secs *= random.uniform(0.8, 1.2)
    return max(TYPING_DELAY_MIN, min(TYPING_DELAY_MAX, secs))


async def send_bubbles(context, chat_id: int, text: str, pre_delay: float = 0.0,
                       reply_to_message_id: int = None):
    """Send a reply as a single message (chunked only if it exceeds Telegram's length limit).

    pre_delay: hold the typing indicator for this many seconds before actually sending,
    simulating realistic compose time. Pass _typing_delay_secs(text) from user-reply paths.
    reply_to_message_id: thread the first chunk as a Telegram reply (used in groups).
    Returns the last sent Message (its message_id feeds the group ledger)."""
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
    last = None
    for i in range(0, len(text), _TELEGRAM_MAX_LEN):
        chunk = text[i:i + _TELEGRAM_MAX_LEN]
        reply_to = reply_to_message_id if i == 0 else None
        for attempt in range(3):
            try:
                if DEVICE_RENDER:
                    escaped = _HTML_ESCAPE_RE.sub(lambda m: _HTML_ESCAPE[m.group(0)], chunk)
                    last = await context.bot.send_message(
                        chat_id=chat_id, text=f"<code>{escaped}</code>", parse_mode="HTML",
                        reply_to_message_id=reply_to)
                else:
                    last = await context.bot.send_message(
                        chat_id=chat_id, text=chunk, reply_to_message_id=reply_to)
                break
            except (NetworkError, TimedOut) as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
    return last


# --- Selfies ---
def selfie_ready() -> bool:
    return (BASE_DIR / SELFIE_BASE).exists() or _APPEARANCE_FILE.exists()


def _has_base_image() -> bool:
    return (BASE_DIR / SELFIE_BASE).exists()


def _base_image() -> tuple:
    """Returns (raw bytes, mime type) for the selfie reference photo."""
    path = BASE_DIR / SELFIE_BASE
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
    outdoors = False
    if not hint and random.random() < 0.7:  # what she's doing (skip if user pinned a scene)
        if _weather_outdoor_ok():
            activity = random.choice(SELFIE_ACTIVITIES)
        else:
            indoor = [a for a in SELFIE_ACTIVITIES if a not in SELFIE_OUTDOOR_ACTIVITIES]
            activity = random.choice(indoor)
        bits.append(f"She's {activity}.")
        outdoors = activity in SELFIE_OUTDOOR_ACTIVITIES
    current_fit = wardrobe.get("current")
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
            return _get_session().post(url, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == _IMAGE_RETRIES - 1:
                raise
            print(f"[selfie] connection issue, retrying ({attempt + 1}/{_IMAGE_RETRIES})...")
            time.sleep(2 * (attempt + 1))


def _get_with_retries(url, **kwargs):
    for attempt in range(_IMAGE_RETRIES):
        try:
            return _get_session().get(url, **kwargs)
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
    headers = {"Authorization": f"Bearer {NANOGPT_API_KEY}", "Content-Type": "application/json"}
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
                text=(f"📷 No reference photo or appearance.txt set. Drop a photo at "
                      f"~/telegram-bot/{SELFIE_BASE} or write a description to "
                      f"~/telegram-bot/appearance.txt and restart."),
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
        log.error("[selfie] failed: %s", e)
        _count_error("media")
        if announce_errors:
            await context.bot.send_message(chat_id=chat_id, text=f"📷 Couldn't make that one: {e}")
    finally:
        uploading.cancel()


# --- Memes ---
def meme_ready() -> bool:
    return MEME_TEMPLATES_DIR.is_dir() and any(MEME_TEMPLATES_DIR.glob("*.jpg")) and MEME_FONT_PATH.exists()


def _pick_meme_template(chat_id: int) -> Path:
    templates = sorted(MEME_TEMPLATES_DIR.glob("*.jpg"))
    recent = _recent_meme_templates.get(chat_id, [])
    choices = [t for t in templates if t.name not in recent] or templates
    pick = random.choice(choices)
    buf = _recent_meme_templates.setdefault(chat_id, [])
    buf.append(pick.name)
    if len(buf) > MEME_DEDUP_SIZE:
        buf.pop(0)
    return pick


def _wrap_meme_text(draw, text: str, font, max_width: int) -> list:
    """Greedy word-wrap: return a list of lines that each fit within max_width."""
    words = text.split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_meme_text(draw, text: str, max_width: int, max_height: int, start_size: int):
    """Shrink font size in steps until the wrapped text fits max_width/max_height.
    Returns (font, lines, line_height)."""
    size = start_size
    while size >= MEME_MIN_FONT_SIZE:
        font = ImageFont.truetype(str(MEME_FONT_PATH), size)
        lines = _wrap_meme_text(draw, text, font, max_width)
        line_height = font.getbbox("Ag")[3] - font.getbbox("Ag")[1]
        total_height = line_height * len(lines) * 1.15
        widest = max((draw.textbbox((0, 0), l, font=font)[2] for l in lines), default=0)
        if total_height <= max_height and widest <= max_width:
            return font, lines, line_height
        size -= 4
    font = ImageFont.truetype(str(MEME_FONT_PATH), MEME_MIN_FONT_SIZE)
    lines = _wrap_meme_text(draw, text, font, max_width)
    line_height = font.getbbox("Ag")[3] - font.getbbox("Ag")[1]
    return font, lines, line_height


def _draw_meme_caption(draw, lines: list, font, line_height: float, img_width: int, y_start: float):
    y = y_start
    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        x = (img_width - w) / 2
        draw.text((x, y), line, font=font, fill="white",
                   stroke_width=max(2, font.size // 18), stroke_fill="black")
        y += line_height * 1.15


def render_meme(template_path: Path, top_text: str, bottom_text: str) -> bytes:
    """Sync/CPU-bound Pillow work — call via asyncio.to_thread."""
    img = Image.open(template_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    margin = int(w * 0.04)
    max_width = w - 2 * margin
    max_block_height = h * 0.28  # each caption gets up to ~28% of image height

    if top_text:
        font, lines, lh = _fit_meme_text(draw, top_text.upper(), max_width, max_block_height, MEME_FONT_SIZE)
        _draw_meme_caption(draw, lines, font, lh, w, margin)

    if bottom_text:
        font, lines, lh = _fit_meme_text(draw, bottom_text.upper(), max_width, max_block_height, MEME_FONT_SIZE)
        total_h = lh * 1.15 * len(lines)
        _draw_meme_caption(draw, lines, font, lh, w, h - margin - total_h)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


async def _generate_meme_captions(hint: str, chat_id: int) -> tuple:
    """Ask the model for a short top/bottom meme caption pair. Mirrors _selfie_caption's
    context-gathering, but asks for structured JSON since two distinct fields are needed."""
    uname = user_names.get(chat_id, "you")
    recent = [m for m in conversation_history.get(chat_id, [])[-8:] if isinstance(m.get("content"), str)]
    mem = memory_block(chat_id, uname)
    history = (
        ([{"role": "system", "content": mem}] if mem else [])
        + [{"role": m["role"], "content": m["content"][:300]} for m in recent]
    )
    ask = (
        "Write a meme caption pair reacting to this conversation"
        + (f", specifically: {hint}" if hint else "")
        + ". Classic top-text/bottom-text meme-macro format — short, punchy, funny, in "
        "your own voice. Respond with ONLY a JSON object: "
        '{"top": "...", "bottom": "..."} — no prose, no code fences. Either field may be '
        "an empty string if the joke only needs one line."
    )
    messages = (
        [{"role": "system", "content": fill(SYSTEM_PROMPT_RAW, NAME, uname)}]
        + history
        + [{"role": "user", "content": ask}]
    )
    try:
        raw = await generate_reply(messages, model=SUMMARY_MODEL or NANOGPT_MODEL)
        data = _extract_json(raw)
        return (data.get("top") or "").strip(), (data.get("bottom") or "").strip()
    except Exception:
        return "", ""


async def send_meme(context, chat_id: int, hint: str = "", top: str = None, bottom: str = None,
                     announce_errors: bool = True):
    """top/bottom pre-supplied (from an in-character [meme:] tag) skips caption generation;
    otherwise (the /meme command path) captions are generated from hint + conversation."""
    if not meme_ready():
        if announce_errors:
            await context.bot.send_message(
                chat_id=chat_id,
                text="🖼️ No meme templates found. Drop some .jpg templates in "
                     "~/telegram-bot/meme_templates/ and a font at ~/telegram-bot/fonts/Anton-Regular.ttf.",
            )
        return
    uploading = asyncio.create_task(_keep_uploading(context.bot, chat_id))
    try:
        if top is None and bottom is None:
            top, bottom = await _generate_meme_captions(hint, chat_id)
        if not top and not bottom:
            return
        template = _pick_meme_template(chat_id)
        img = await asyncio.to_thread(render_meme, template, top, bottom)
        await context.bot.send_photo(chat_id=chat_id, photo=BytesIO(img))
    except Exception as e:
        log.error("[meme] failed: %s", e)
        _count_error("media")
        if announce_errors:
            await context.bot.send_message(chat_id=chat_id, text=f"🖼️ Couldn't make that one: {e}")
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
    save_state()


def _short_term_overflow(chat_id: int) -> int:
    """How many oldest messages should leave the verbatim window (time OR count)."""
    hist = conversation_history.get(chat_id, [])
    n = len(hist)
    if n <= KEEP_RECENT:
        return 0
    # Groups summarize half as often — banter is lower-density than DM conversation
    # and every summarization is a model call (GROUP_CHAT_DESIGN.md §4).
    mult = 2 if chat_id < 0 else 1
    by_count = max(0, n - MAX_HISTORY * mult)       # marathon-session safety cap
    cutoff = time.time() - SHORT_TERM_SECS * mult
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
            pass
    # Greedy span failed (e.g. a second '{' after the real object). Decode the
    # first balanced JSON object instead.
    start = raw.find("{")
    if start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[start:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
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
RECENT_FACTS_MAX = _env_int("RECENT_FACTS_MAX", "30")
RECENT_FACTS_TARGET = _env_int("RECENT_FACTS_TARGET", "20")

# Long-term (durable) facts list: same idea, but kept much smaller since it's permanent.
LONG_FACTS_MAX = _env_int("LONG_FACTS_MAX", "22")
LONG_FACTS_TARGET = _env_int("LONG_FACTS_TARGET", "15")

# How often (days) recent memory gets reviewed and folded into long-term memory.
PROMOTION_INTERVAL_DAYS = _env_float("PROMOTION_INTERVAL_DAYS", "7")


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
        async with _SUMMARIZE_SEM:
            batch = list(conversation_history.get(chat_id, [])[:drop_count])
            uname = user_names.get(chat_id, "you")
            try:
                real_facts, own_days = _split_own_day_facts(recent_facts.get(chat_id, []))
                summary, new_facts = await asyncio.to_thread(
                    _summarize, recent_summaries.get(chat_id, ""), real_facts,
                    batch, uname,
                )
                recent_summaries[chat_id] = summary
                recent_facts[chat_id] = new_facts + own_days
            except Exception as e:
                log.warning("[memory] summarize failed; dropping overflow without summary: %s", e)
                _count_error("memory")
            del conversation_history[chat_id][:drop_count]
            save_state()
            print(f"[memory] Summarized {drop_count} message(s) for chat {chat_id}.")

            if len(recent_facts.get(chat_id, [])) > RECENT_FACTS_MAX:
                try:
                    real_facts, own_days = _split_own_day_facts(recent_facts.get(chat_id, []))
                    summary, new_facts = await asyncio.to_thread(
                        _consolidate_facts, recent_summaries.get(chat_id, ""),
                        real_facts, uname, RECENT_FACTS_TARGET,
                    )
                    before = len(recent_facts.get(chat_id, []))
                    recent_summaries[chat_id] = summary
                    recent_facts[chat_id] = new_facts + own_days
                    save_state()
                    print(f"[memory] Consolidated recent facts {before} -> {len(new_facts)} for chat {chat_id}.")
                except Exception as e:
                    log.warning("[memory] recent fact consolidation failed (kept as-is): %s", e)
                    _count_error("memory")
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
        async with _SUMMARIZE_SEM:
            uname = user_names.get(chat_id, "you")
            if due and has_recent:
                try:
                    real_facts, own_days = _split_own_day_facts(recent_facts.get(chat_id, []))
                    summary, new_facts = await asyncio.to_thread(
                        _promote_to_long_term, summaries.get(chat_id, ""), facts.get(chat_id, []),
                        recent_summaries.get(chat_id, ""), real_facts, uname,
                    )
                    summaries[chat_id] = summary
                    facts[chat_id] = new_facts
                    recent_summaries[chat_id] = ""
                    recent_facts[chat_id] = own_days
                    save_state()
                    print(f"[memory] Promoted recent memory to long-term for chat {chat_id}.")
                except Exception as e:
                    log.warning("[memory] promotion failed: %s", e)
                    _count_error("memory")
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
                    log.warning("[memory] long-term fact consolidation failed (kept as-is): %s", e)
                    _count_error("memory")
    finally:
        summarizing.discard(chat_id)


# --- Telegram command handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if context.args and context.args[0].lower() == "full":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Yes, wipe everything", callback_data="start_full:confirm"),
            InlineKeyboardButton("Cancel", callback_data="start_full:cancel"),
        ]])
        await update.message.reply_text(
            "⚠️ This will wipe conversation history AND all per-chat memory "
            "(summaries, facts, milestones, pinned, moods, beliefs) for this chat. "
            "Character-level memories (memories.txt) are kept.\n\nAre you sure?",
            reply_markup=kb)
        return
    conversation_history[chat_id] = []
    last_seen[chat_id] = time.time()
    user_names[chat_id] = update.effective_user.first_name or "you"
    set_owner(chat_id)
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
        "*Inside jokes & wardrobe*",
        "/addjoke phrase | meaning | tone — add an inside joke",
        "/jokes — list inside jokes",
        "/deljoke <id> — remove a joke",
        "/wardrobe — list outfits",
        "/addoutfit <desc> — add an outfit",
        "/outfit <n> — set current outfit (used in selfies)",
        "/deloutfit <n> — remove an outfit",
        "",
        "*Selfie*",
        "/selfie [hint] — generate a selfie",
        "/selfimage — view her current self-image",
        "/reflect — trigger nightly reflection now",
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
        "*Maps (routing & places)*",
        "/route <from> to <dest> — travel time & distance",
        "/nearby <thing> — places near your shared location",
        "/place <name> — look up an address or business",
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
        r = _get_session().get("https://nano-gpt.com/api/subscription/v1/models",
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
        log.warning("[models] subscription model list failed: %s", e)

    if not models:
        try:
            r = _get_session().get(f"{NANOGPT_BASE_URL}/models", headers=headers, timeout=30)
            r.raise_for_status()
            for m in r.json().get("data", []):
                if any(m.get(k) for k in ("subscription", "is_subscription", "subscription_only")):
                    models.append(m["id"])
            filtered = bool(models)
            if not models:  # subscription flag not present -- fall back to the full list
                models = [m["id"] for m in r.json().get("data", []) if m.get("id")]
        except Exception as e:
            log.warning("[models] general model list failed: %s", e)

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
    globals()[var] = model_id
    model_overrides[var] = model_id
    save_state()
    await update.message.reply_text(f"✅ {role} model set to `{model_id}`", parse_mode="Markdown")


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
    goal = (next_goals.get(chat_id) or "").strip() or "(none)"
    items = beliefs.get(chat_id, {}).get("items") or {}
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
        "",
        "=== SELF-IMAGE ===",
        "\n".join(f"- {t}: {d['score']}/10" for t, d in items.items()) or "(none yet)",
        "",
        f"Next-conversation goal: {goal}",
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


# --- Inside joke bank ---
async def add_joke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip() if context.args else ""
    if not text or "|" not in text:
        await update.message.reply_text(
            "Usage: /addjoke <phrase> | <meaning> [| tone]\n\n"
            "Example: /addjoke the soup incident | failed at reheating soup | playful\n"
            "Tone defaults to 'playful' if not specified."
        )
        return
    parts = [p.strip() for p in text.split("|")]
    phrase = parts[0]
    meaning = parts[1] if len(parts) > 1 else ""
    tone = parts[2] if len(parts) > 2 else "playful"
    if not phrase or not meaning:
        await update.message.reply_text("Need at least a phrase and a meaning.")
        return
    inside_jokes.append({
        "id": _new_joke_id(),
        "phrase": phrase[:80],
        "meaning": meaning[:160],
        "tone": tone[:30],
        "last_used": 0,
        "cooldown_days": 7,
    })
    save_jokes()
    await update.message.reply_text(f'😂 Added joke: "{phrase}"')


async def list_jokes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not inside_jokes:
        await update.message.reply_text(
            "No inside jokes yet. Use /addjoke to add one.\n\n"
            "Format: /addjoke <phrase> | <meaning> [| tone]"
        )
        return
    now = time.time()
    lines = []
    for j in inside_jokes:
        last = j.get("last_used", 0)
        cd = j.get("cooldown_days", 7)
        ready_in = max(0, (last + cd * 86400 - now) / 3600)
        status = "ready" if ready_in <= 0 else f"on cooldown ({round(ready_in)}h left)"
        lines.append(f"{j['id']}. \"{j['phrase']}\" ({j['tone']}) — {j['meaning']} [{status}]")
    await _reply_chunked(update, "😂 Inside jokes:\n\n" + "\n".join(lines)
                         + "\n\nUse /deljoke <id> to remove one.")


async def del_joke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /deljoke <id from /jokes>")
        return
    jid = int(context.args[0])
    target = next((j for j in inside_jokes if j["id"] == jid), None)
    if not target:
        await update.message.reply_text("No joke with that id.")
        return
    inside_jokes.remove(target)
    save_jokes()
    await update.message.reply_text(f'🗑️ Removed joke: "{target["phrase"]}"')


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
def _inworld_tts(text: str) -> bytes:
    """Synthesize speech via Inworld's TTS API; returns OGG/Opus bytes for Telegram."""
    resp = _get_session().post(
        "https://api.inworld.ai/tts/v1/voice",
        headers={"Authorization": f"Basic {INWORLD_API_KEY}",
                 "Content-Type": "application/json"},
        json={
            "text": text,
            "voiceId": TTS_VOICE,
            "modelId": INWORLD_TTS_MODEL,
            "audioConfig": {"audioEncoding": "OGG_OPUS"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    return base64.b64decode(resp.json()["audioContent"])


def _nanogpt_tts(text: str) -> bytes:
    resp = _get_session().post(
        f"{NANOGPT_BASE_URL}/audio/speech",
        headers={"Authorization": f"Bearer {NANOGPT_API_KEY}"},
        json={"model": TTS_MODEL, "input": text, "voice": TTS_VOICE},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


async def _send_voice_reply(context, chat_id: int, text: str):
    """Generate TTS audio and send as a Telegram voice message."""
    try:
        tts = _inworld_tts if INWORLD_API_KEY else _nanogpt_tts
        audio = await asyncio.to_thread(tts, text)
        await context.bot.send_voice(chat_id=chat_id, voice=BytesIO(audio))
    except requests.exceptions.HTTPError as e:
        log.warning("TTS failed: %s — %s", e, e.response.text[:300])
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
         InlineKeyboardButton("😂 Jokes", callback_data="cmd:jokes"),
         InlineKeyboardButton("👗 Wardrobe", callback_data="cmd:wardrobe")],
        [InlineKeyboardButton("📸 Selfie", callback_data="cmd:selfie"),
         InlineKeyboardButton("🪞 Self-image", callback_data="cmd:selfimage"),
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
        goal = (next_goals.get(chat_id) or "").strip() or "(none)"
        items = beliefs.get(chat_id, {}).get("items") or {}
        lines = [
            f"Memory export — {NAME} / {now_str}", "",
            "=== LONG-TERM ===", f"Summary:\n{summ}", "",
            "Facts:\n" + ("\n".join("- " + f for f in fts) or "(none)"), "",
            "=== RECENT ===", f"Summary:\n{rsumm}", "",
            "Facts:\n" + ("\n".join("- " + f for f in rfts) or "(none)"), "",
            "=== SELF-IMAGE ===",
            "\n".join(f"- {t}: {d['score']}/10" for t, d in items.items()) or "(none yet)", "",
            f"Next goal: {goal}",
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

    elif data == "cmd:jokes":
        if not inside_jokes:
            await _send("No inside jokes yet. Use /addjoke.")
        else:
            now = time.time()
            lines = []
            for j in inside_jokes:
                last = j.get("last_used", 0)
                cd = j.get("cooldown_days", 7)
                ready_in = max(0, (last + cd * 86400 - now) / 3600)
                status = "ready" if ready_in <= 0 else f"~{round(ready_in)}h cooldown"
                lines.append(f'• "{j["phrase"]}" — {status}')
            await _send("😂 Inside jokes:\n" + "\n".join(lines))

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

    elif data == "cmd:selfimage":
        items = beliefs.get(chat_id, {}).get("items") or {}
        if not items:
            await _send("Nothing yet — runs at the first nightly reflection.")
        else:
            lines = [f"• {t}: {d['score']}/10" for t, d in items.items()]
            goal = (next_goals.get(chat_id) or "").strip() or "(none)"
            await _send("🪞 Self-image:\n" + "\n".join(lines) + f"\n\nNext goal: {goal}")

    elif data == "cmd:heartbeat":
        try:
            await send_proactive(context, chat_id)
        except Exception as e:
            await _send(f"❌ {e}")

    elif data == "start_full:confirm":
        conversation_history[chat_id] = []
        summaries[chat_id] = ""
        facts[chat_id] = []
        recent_summaries[chat_id] = ""
        recent_facts[chat_id] = []
        milestones[chat_id] = []
        pinned[chat_id] = []
        moods.pop(chat_id, None)
        beliefs.pop(chat_id, None)
        save_state()
        greeting = fill(FIRST_MES_RAW, NAME, user_names.get(chat_id, "you")) or f"Hi, I'm {NAME}."
        await _send(f"🧹 Full reset complete.\n\n{greeting}")

    elif data == "start_full:cancel":
        await _send("Cancelled — nothing changed.")

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
            removed = entries[idx]
            await asyncio.to_thread(_memory_replace, removed, None)
            _memory_log("DEL", removed)
            await update.message.reply_text(f"✓ Removed: {removed}")
        else:
            await update.message.reply_text("No memory at that number.")
    else:
        before = len(entries)
        to_remove = [e for e in entries if arg.lower() in e.lower()]
        if to_remove:
            for e in to_remove:
                await asyncio.to_thread(_memory_replace, e, None)
                _memory_log("DEL", e)
            await update.message.reply_text(
                f"✓ Removed {len(to_remove)} entr(ies) matching '{arg}'."
            )
        else:
            await update.message.reply_text(f"No memories matched '{arg}'.")


async def editmem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id):
        return
    args = " ".join(context.args).strip() if context.args else ""
    parts = args.split(None, 1)
    if len(parts) < 2 or not parts[0].isdigit():
        await update.message.reply_text("Usage: /editmem <number> <new text>")
        return
    idx = int(parts[0]) - 1
    new_text = parts[1].strip()
    entries = _read_memories()
    if not (0 <= idx < len(entries)):
        await update.message.reply_text("No memory at that number.")
        return
    old = entries[idx]
    old_meta = _memory_meta.get(old.strip(), {})
    new_meta = {**old_meta, "origin": "manual-edit", "ts": time.time()}
    await asyncio.to_thread(_memory_replace, old, new_text, new_meta)
    _memory_log("EDIT", new_text, f'was="{old[:80]}"')
    await update.message.reply_text(f"✓ Updated #{parts[0]}:\n  was: {old}\n  now: {new_text}")


async def sourcemem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id):
        return
    arg = " ".join(context.args).strip() if context.args else ""
    if not arg or not arg.isdigit():
        await update.message.reply_text("Usage: /sourcemem <number>")
        return
    idx = int(arg) - 1
    entries = _read_memories()
    if not (0 <= idx < len(entries)):
        await update.message.reply_text("No memory at that number.")
        return
    entry = entries[idx]
    meta = _memory_meta.get(entry.strip())
    if not meta:
        await update.message.reply_text(
            f"#{int(arg)}: {entry}\n\n(no source recorded — pre-2026-07)")
        return
    ts = meta.get("ts")
    ts_str = datetime.fromtimestamp(ts, tz=TZ).strftime("%Y-%m-%d %H:%M") if ts and TZ else (
        datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "?")
    lines = [
        f"#{int(arg)}: {entry}",
        f"Origin: {meta.get('origin', '?')}",
        f"Recorded: {ts_str}",
    ]
    if meta.get("confidence") is not None:
        lines.append(f"Confidence: {meta['confidence']}/10")
    if meta.get("source"):
        lines.append(f'Source: "{meta["source"]}"')
    await update.message.reply_text("\n".join(lines))


async def reviewmem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id):
        return
    args = context.args or []
    queue = _load_memory_review()
    if not args:
        if not queue:
            await update.message.reply_text("No memories pending review.")
            return
        lines = []
        for i, item in enumerate(queue):
            conf = item.get("meta", {}).get("confidence", "?")
            src = item.get("meta", {}).get("source", "")
            lines.append(f"{i+1}. [conf={conf}] {item['text']}")
            if src:
                lines.append(f"   src: \"{src[:80]}\"")
        await update.message.reply_text(
            f"📋 {len(queue)} pending review:\n\n" + "\n".join(lines)
            + "\n\nUse /reviewmem ok <n> or /reviewmem no <n>")
        return
    action = args[0].lower()
    if action not in ("ok", "no") or len(args) < 2 or not args[1].isdigit():
        await update.message.reply_text("Usage: /reviewmem [ok|no] <number>")
        return
    idx = int(args[1]) - 1
    if not (0 <= idx < len(queue)):
        await update.message.reply_text("No review item at that number.")
        return
    item = queue.pop(idx)
    _save_memory_review(queue)
    if action == "ok":
        _append_memory(item["text"], auto=True, meta=item.get("meta"))
        _memory_log("REVIEW-OK", item["text"])
        await update.message.reply_text(f"✓ Promoted to memory: {item['text']}")
    else:
        _memory_log("REVIEW-NO", item["text"])
        await update.message.reply_text(f"✗ Dropped: {item['text']}")


async def recall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search facts, summaries, and memories for a keyword (+ semantic similarity)."""
    chat_id = update.effective_chat.id
    keyword = " ".join(context.args).strip().lower() if context.args else ""
    if not keyword:
        await update.message.reply_text("Usage: /recall <keyword or phrase>")
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
    # Semantic recall over memories.txt
    seen_texts = {h.split("] ", 1)[-1] if "] " in h else h for h in hits}
    sem = await asyncio.to_thread(semantic_recall, keyword, _read_memories(), 5)
    for sim, line in sem:
        if sim > 0.3 and line not in seen_texts:
            hits.append(f"[memory ~{sim:.0%}] {line}")
            seen_texts.add(line)
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
_BACKUP_FILENAMES = ("payments.json", "state.json", "reminders.json",
                     "memories.txt", "user_notes.txt", "setting.txt")


def backup_file_list() -> list[Path]:
    """Existing backup files for this instance, in send order."""
    return [p for p in (BASE_DIR / f for f in _BACKUP_FILENAMES) if p.exists()]


def build_backup_zip() -> bytes:
    """Zip the same files backup_file_list() names, for a single-response download
    (the admin HTTP API can't send multiple Telegram documents)."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in backup_file_list():
            try:
                zf.write(path, arcname=path.name)
            except FileNotFoundError:
                continue  # rotated/removed between listing and open — skip, don't die
    return buf.getvalue()


async def _send_backup(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    sent = []
    for path in backup_file_list():
        try:
            with path.open("rb") as fh:
                await context.bot.send_document(chat_id=chat_id, document=fh, filename=path.name)
        except FileNotFoundError:
            continue  # rotated/removed between listing and open — skip, don't die
        sent.append(path.name)
    return sent


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    sent = await _send_backup(context, update.effective_chat.id)
    if sent:
        await update.message.reply_text("💾 Backup sent: " + ", ".join(sent) +
                                        "\n(Save these — restore by copying them back into the bot folder. "
                                        ".env is not included; keep your tokens somewhere safe separately.)")
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
    raw = await asyncio.to_thread(
        call_nanogpt,
        [{"role": "system", "content": sys_msg}, {"role": "user", "content": "\n\n".join(parts)}],
        MOOD_MODEL,
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


_DOW_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_DOW_DISPLAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


async def quietwin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/quietwin add Fri 23:00-08:00 | /quietwin list | /quietwin del <n>"""
    chat_id = update.effective_chat.id
    args = context.args or []
    sub = args[0].lower() if args else "list"

    if sub == "list":
        wins = quiet_windows.get(chat_id, [])
        if not wins:
            await update.message.reply_text("No recurring quiet windows set.\nUse: /quietwin add Fri 23:00-08:00")
            return
        lines = ["*Quiet windows:*"]
        for i, w in enumerate(wins, 1):
            sh = f"{w['start'] // 60:02d}:{w['start'] % 60:02d}"
            eh = f"{w['end'] // 60:02d}:{w['end'] % 60:02d}"
            lines.append(f"{i}. {_DOW_DISPLAY[w['dow']]} {sh}–{eh}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    if sub == "del":
        if len(args) < 2:
            await update.message.reply_text("Usage: /quietwin del <number>")
            return
        wins = quiet_windows.get(chat_id, [])
        try:
            idx = int(args[1]) - 1
            if idx < 0 or idx >= len(wins):
                raise ValueError
        except ValueError:
            await update.message.reply_text(f"Invalid index. You have {len(wins)} window(s).")
            return
        removed = wins.pop(idx)
        if not wins:
            quiet_windows.pop(chat_id, None)
        save_state()
        sh = f"{removed['start'] // 60:02d}:{removed['start'] % 60:02d}"
        eh = f"{removed['end'] // 60:02d}:{removed['end'] % 60:02d}"
        await update.message.reply_text(f"Removed: {_DOW_DISPLAY[removed['dow']]} {sh}–{eh}")
        return

    if sub == "add":
        if len(args) < 3:
            await update.message.reply_text("Usage: /quietwin add Fri 23:00-08:00")
            return
        dow_str = args[1].lower()[:3]
        if dow_str not in _DOW_NAMES:
            await update.message.reply_text(f"Unknown day: {args[1]}. Use Mon/Tue/Wed/Thu/Fri/Sat/Sun.")
            return
        dow = _DOW_NAMES.index(dow_str)
        time_range = args[2]
        if "-" not in time_range:
            await update.message.reply_text("Time range format: HH:MM-HH:MM (e.g. 23:00-08:00)")
            return
        parts = time_range.split("-", 1)
        try:
            sp = parts[0].split(":")
            ep = parts[1].split(":")
            start_min = int(sp[0]) * 60 + int(sp[1])
            end_min = int(ep[0]) * 60 + int(ep[1])
            if not (0 <= start_min < 1440 and 0 <= end_min < 1440):
                raise ValueError
            if start_min == end_min:
                raise ValueError
        except (ValueError, IndexError):
            await update.message.reply_text("Time range format: HH:MM-HH:MM (e.g. 23:00-08:00)")
            return
        entry = {"dow": dow, "start": start_min, "end": end_min}
        quiet_windows.setdefault(chat_id, []).append(entry)
        save_state()
        sh = f"{start_min // 60:02d}:{start_min % 60:02d}"
        eh = f"{end_min // 60:02d}:{end_min % 60:02d}"
        cross = " (crosses midnight)" if start_min > end_min else ""
        await update.message.reply_text(f"Added quiet window: {_DOW_DISPLAY[dow]} {sh}–{eh}{cross}")
        return

    await update.message.reply_text("Usage: /quietwin add|list|del")


async def reaction_feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 👍/👎 reactions on bot messages — mood nudge + feedback log."""
    if not FEEDBACK_REACTIONS:
        return
    reaction = update.message_reaction
    if not reaction or not reaction.new_reaction:
        return
    chat_id = reaction.chat.id
    if not _is_allowed(reaction.user.id if reaction.user else 0):
        return
    emoji = None
    for r in reaction.new_reaction:
        e = getattr(r, "emoji", None)
        if e in ("👍", "👎"):
            emoji = e
            break
    if not emoji:
        return
    snippet = ""
    hist = conversation_history.get(chat_id, [])
    if hist:
        last_bot = next((m for m in reversed(hist) if m.get("role") == "assistant"), None)
        if last_bot:
            snippet = (last_bot.get("content") or "")[:60]
    entry = {"emoji": emoji, "ts": time.time(), "msg_snippet": snippet}
    feedback_log.setdefault(chat_id, []).append(entry)
    if len(feedback_log[chat_id]) > 50:
        feedback_log[chat_id] = feedback_log[chat_id][-50:]
    cur = moods.get(chat_id) or {}
    score = cur.get("score", 0.0)
    nudge = 0.3 if emoji == "👍" else -0.3
    new_score = max(-3.0, min(3.0, score + nudge))
    moods[chat_id] = {**cur, "score": new_score, "ts": time.time()}
    if emoji == "👎":
        _feedback_miss.add(chat_id)
    save_state()


_feedback_miss: set = set()


async def away_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/away <reason> — suppress proactives until /back or next message."""
    chat_id = update.effective_chat.id
    reason = " ".join(context.args).strip() if context.args else "away"
    away[chat_id] = {
        "reason": reason, "since": time.time(),
        "origin": "manual", "expires": None,
    }
    save_state()
    await update.message.reply_text(f"Away mode on: {reason}\nHeartbeats paused. Send /back or any message to clear.")


async def back_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/back — clear away mode."""
    chat_id = update.effective_chat.id
    old = _clear_away(chat_id)
    if old:
        save_state()
        await update.message.reply_text("Welcome back! Away mode cleared.")
    else:
        await update.message.reply_text("You weren't marked as away.")


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
    if (due.tzinfo is None) != (now.tzinfo is None):
        # A stored aware/naive timestamp can outlive a tzdata hiccup (e.g. TZ falling
        # back to None after a venv rebuild missing the `tzdata` package) — comparing
        # mismatched awareness raises TypeError and would crash startup for every
        # reminder behind this one. Strip tzinfo from both rather than let one bad
        # timestamp take the whole bot down.
        due, now = due.replace(tzinfo=None), now.replace(tzinfo=None)
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


def _transcribe_audio(data: bytes, filename: str, mime: str) -> str:
    """Blocking Whisper call — always run via asyncio.to_thread. Calling it bare in an
    async handler freezes the whole bot for up to 60s (every chat, every job)."""
    resp = _get_session().post(
        f"{NANOGPT_BASE_URL}/audio/transcriptions",
        headers={"Authorization": f"Bearer {NANOGPT_API_KEY}"},
        files={"file": (filename, data, mime)},
        data={"model": WHISPER_MODEL},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("text", "").strip()


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
        transcript = await asyncio.to_thread(
            _transcribe_audio, bytes(voice_bytes), "voice.ogg", "audio/ogg")
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
        await _deliver(update, context, chat_id, transcript, ai_response,
                       voice_input=True)
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
                    transcript = await asyncio.to_thread(
                        _transcribe_audio, audio_bytes, "audio.ogg", "audio/ogg") or None
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


PDF_MAX_SIZE_MB = _env_int("PDF_MAX_SIZE_MB", "20")
PDF_MAX_CHARS = _env_int("PDF_MAX_CHARS", "16000")
PDF_OCR_MAX_PAGES = _env_int("PDF_OCR_MAX_PAGES", "4")


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
    # to_thread: a bare requests call here would freeze the whole event loop for
    # up to 30s on a slow phone connection.
    response = await asyncio.to_thread(
        lambda: _get_session().get(
            "https://nano-gpt.com/api/subscription/v1/usage",
            headers=headers,
            timeout=30,
        ))
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


_MEMCHECK_RE = re.compile(r"\[memcheck:\s*(.+?)\]", re.IGNORECASE)


async def _handle_memcheck(context, chat_id: int, query: str):
    """Run recall machinery over the query and DM the numbered hits with fix commands."""
    entries = await asyncio.to_thread(_read_memories)
    hits = []
    for i, e in enumerate(entries):
        if query.lower() in e.lower():
            hits.append((i + 1, e))
    sem = await asyncio.to_thread(semantic_recall, query, entries, 5)
    seen = {e for _, e in hits}
    for sim, line in sem:
        if sim > 0.3 and line not in seen:
            idx = next((j + 1 for j, el in enumerate(entries) if el == line), None)
            if idx:
                hits.append((idx, line))
                seen.add(line)
    if not hits:
        await context.bot.send_message(chat_id=chat_id,
            text=f"🔍 Memcheck \"{query}\" — no matching memories found.")
        _memory_log("MEMCHECK", query, "-> 0 hits")
        return
    lines = [f"🔍 Memcheck \"{query}\" — {len(hits)} hit(s):\n"]
    for num, entry in hits[:8]:
        meta = _memory_meta.get(entry.strip())
        src_note = ""
        if meta and meta.get("source"):
            src_note = f'\n   src: "{meta["source"][:80]}"'
        lines.append(f"  #{num}: {entry}{src_note}")
        lines.append(f"  → /delmem {num}  or  /editmem {num} <corrected text>")
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines))
    _memory_log("MEMCHECK", query, f"-> {len(hits)} hits")


async def _deliver(update, context, chat_id, user_memory_text, ai_response,
                   voice_input=False):
    """Shared tail for text and photo handlers: tags, reaction, bubbles, selfie, memory."""
    memcheck_m = _MEMCHECK_RE.search(ai_response)
    if memcheck_m:
        ai_response = _MEMCHECK_RE.sub("", ai_response).strip()
        asyncio.create_task(_handle_memcheck(context, chat_id, memcheck_m.group(1).strip()))
    clean, reaction, selfie_hint, meme_caption = extract_tags(ai_response)
    if clean:
        clean = _strip_slop(clean)
        clean = _strip_persona_breaks(clean)
    placeholder = clean or (
        "[sent a selfie]" if selfie_hint is not None else
        "[sent a meme]" if meme_caption is not None else
        (f"[reacted {reaction}]" if reaction else "")
    )
    remember(chat_id, "user", user_memory_text)
    remember(chat_id, "assistant", placeholder)

    reacted = False
    if reaction and reaction in ALLOWED_REACTIONS:
        try:
            await update.message.set_reaction(reaction)
            reacted = True
        except Exception as e:
            log.warning("[react] failed: %s", e)
    if clean:
        await send_bubbles(context, chat_id, clean, pre_delay=_typing_delay_secs(clean))
        tts_prob = VOICE_REPLY_TO_VOICE if voice_input else TTS_CHANCE
        if voice_reply.get(chat_id) and random.random() < tts_prob:
            asyncio.create_task(_send_voice_reply(context, chat_id, clean))
    if selfie_hint is not None:
        await send_selfie(context, chat_id, selfie_hint, announce_errors=False)
    if meme_caption is not None:
        await send_meme(context, chat_id, top=meme_caption[0], bottom=meme_caption[1], announce_errors=False)
    if inside_jokes and clean:
        _check_joke_used(clean)
    if clean:
        q = _extract_last_question(clean)
        if q and len(q) > 12:
            buf = _recent_questions.setdefault(chat_id, [])
            buf.append(q)
            if len(buf) > QUESTION_MEMORY_SIZE:
                buf.pop(0)
    asyncio.create_task(maintain_memory(chat_id))  # background, doesn't delay reply
    # One combined background pass: mood + user note + NPC memory (was 3 separate calls)
    asyncio.create_task(post_reply_analysis(chat_id, user_memory_text))
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
    resolved = _get_session().get("https://oauth.reddit.com" + path, headers=headers,
                            timeout=LINK_FETCH_TIMEOUT, allow_redirects=True)
    base = "https://oauth.reddit.com" + urlparse(resolved.url).path.rstrip("/")
    if not base.endswith(".json"):
        base += "/.json"
    resp = _get_session().get(base, headers=headers, timeout=LINK_FETCH_TIMEOUT)
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
    html = _get_session().get(url, headers={"User-Agent": _HTTP_UA},
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
        r = _get_session().post(
            "https://html.duckduckgo.com/html/", data={"q": query},
            headers={"User-Agent": _SEARCH_UA}, timeout=LINK_FETCH_TIMEOUT,
        )
        r.raise_for_status()
        page = r.text
    except Exception as e:
        log.warning("[search] failed: %s", e)
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
        log.warning("[link] fetch failed: %s", e)
        return None


async def group_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Single choke point for ALL group traffic, registered in handler group -1
    (GROUP_CHAT_DESIGN.md §5/§6). Fleet-wide, GROUP_MODE or not: in a group chat only
    two things ever flow to feature handlers — allowlisted commands (/chatid), and
    plain text messages for an instance that participates in that group. Everything
    else (other commands, media, stickers, locations, callbacks, edits, future update
    types) stops here by construction."""
    chat = update.effective_chat
    if chat is None or chat.id >= 0:
        return  # private chats: the guard is a no-op
    msg = update.effective_message
    text = (msg.text or "") if msg else ""
    if text.startswith("/"):
        cmd = text.split()[0][1:].split("@")[0].lower()
        if cmd in GROUP_ALLOWED_COMMANDS:
            return
        # In a participating group, refuse audibly once; everywhere else, total silence.
        if GROUP_MODE and chat.id in GROUP_ALLOWED_CHATS and msg is not None:
            try:
                await msg.reply_text("(commands are a DM thing — text me directly)")
            except Exception:
                pass
        raise ApplicationHandlerStop
    if (GROUP_MODE and chat.id in GROUP_ALLOWED_CHATS
            and update.message is not None and update.message.text):
        return  # live plain-text message in a participating group → handle_message
    raise ApplicationHandlerStop


async def _handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group counterpart of handle_message's core: ledger, turn-taking, reply.
    Reached only for live human text in a participating group (guard + branch)."""
    chat_id = update.effective_chat.id
    msg = update.message
    sender = (update.effective_user.first_name or "Someone").strip()
    text = msg.text
    # {{user}} in group prompts is the human — only human messages may set it (§5).
    user_names[chat_id] = sender
    entry = {
        "ts": time.time(), "msg_id": msg.message_id, "sender": sender, "kind": "human",
        "text": text[:1000],
        "reply_to": msg.reply_to_message.message_id if msg.reply_to_message else None,
    }
    await asyncio.to_thread(_ledger_append, chat_id, entry)

    replied_to_own = bool(
        msg.reply_to_message and msg.reply_to_message.from_user
        and msg.reply_to_message.from_user.id == context.bot.id
    )
    content = f"{sender}: {text}"
    addressed = _is_addressed(text, NAME, context.bot.username or "", replied_to_own)
    if not addressed:
        tail = await asyncio.to_thread(_ledger_tail, chat_id)
        # MUST stay an asyncio.sleep — a blocking sleep here freezes every DM,
        # the poll job, and the watchdog heartbeat (design §2).
        await asyncio.sleep(_claim_delay(tail, NAME, random.random()))
        if not await asyncio.to_thread(_try_claim, chat_id, msg.message_id):
            # A peer claimed it; stay silent — but the message still belongs in
            # this instance's group history, or her context grows holes.
            remember(chat_id, "user", content)
            return
    if not _group_gap_ok(chat_id):
        remember(chat_id, "user", content)
        return
    try:
        messages = assemble_messages(chat_id, content, group=True)
        ai_response = await reply_with_typing(context, chat_id, messages, fallback=FALLBACK_MODEL)
        await _group_deliver(context, chat_id, content, ai_response,
                             reply_to=msg.message_id if addressed else None,
                             react_msg_id=msg.message_id)
    except Exception as e:
        log.warning("[group] reply failed: %s", e)
        _count_error("group_ledger")


async def _group_deliver(context, chat_id: int, user_content: str, ai_response: str,
                         reply_to: int = None, react_msg_id: int = None):
    """Group delivery tail — allowlist-BUILT, not _deliver-with-skips: remember, react,
    send, ledger-append. Nothing else. The group-deliver-clean eval greps this body
    (GROUP_CHAT_DESIGN.md §5/§12)."""
    clean, reaction, _selfie_hint, _meme_caption = extract_tags(ai_response)
    if clean:
        clean = _strip_slop(clean)
    placeholder = clean or (f"[reacted {reaction}]" if reaction else "")
    remember(chat_id, "user", user_content)
    remember(chat_id, "assistant", placeholder)
    if reaction and reaction in ALLOWED_REACTIONS and react_msg_id:
        try:
            await context.bot.set_message_reaction(
                chat_id=chat_id, message_id=react_msg_id, reaction=reaction)
        except Exception as e:
            log.warning("[react] group failed: %s", e)
    if not clean:
        return
    sent = await send_bubbles(context, chat_id, clean,
                              pre_delay=_typing_delay_secs(clean),
                              reply_to_message_id=reply_to)
    if sent is not None:
        _group_last_send[chat_id] = time.time()
        await asyncio.to_thread(_ledger_append, chat_id, {
            "ts": time.time(), "msg_id": sent.message_id, "sender": _char_first_name(),
            "kind": "bot", "text": clean[:1000], "reply_to": reply_to,
        })
    asyncio.create_task(maintain_memory(chat_id))


async def _maybe_reply_to_bot(context, chat_id: int, e: dict):
    """Decide → claim → generate → re-check cap → send, for one peer-bot ledger entry.
    Every control from design §3 is applied here."""
    tail = await asyncio.to_thread(_ledger_tail, chat_id)
    my_first = _char_first_name()
    replied_to_own = any(
        t.get("msg_id") == e.get("reply_to") and t.get("sender") == my_first
        for t in tail
    ) if e.get("reply_to") else False
    addressed = _is_addressed(e.get("text", ""), NAME, context.bot.username or "", replied_to_own)
    content = f"{e.get('sender', '?')}: {e.get('text', '')}"
    if not _should_reply_to_bot(tail, random.random(), addressed):
        # Heard it, chose silence — it still belongs in the conversation record.
        remember(chat_id, "user", content)
        return
    if not _group_budget_ok(chat_id) or not _group_gap_ok(chat_id):
        remember(chat_id, "user", content)
        return
    await asyncio.sleep(_claim_delay(tail, NAME, random.random()))
    if not await asyncio.to_thread(_try_claim, chat_id, e["msg_id"]):
        remember(chat_id, "user", content)
        return
    try:
        messages = assemble_messages(chat_id, content, group=True)
        ai_response = await reply_with_typing(context, chat_id, messages, fallback=FALLBACK_MODEL)
        # Pre-send cap re-check (design §3): if the chain filled while we generated,
        # discard the reply — a wasted model call is the price of never exceeding it.
        if not await asyncio.to_thread(_chain_ok_under_lock, chat_id):
            remember(chat_id, "user", content)
            return
        _group_bump_budget(chat_id)
        await _group_deliver(context, chat_id, content, ai_response,
                             reply_to=e["msg_id"], react_msg_id=e["msg_id"])
    except Exception as ex:
        log.warning("[group] bot-to-bot reply failed: %s", ex)
        _count_error("group_ledger")


async def _group_poll_job(context: ContextTypes.DEFAULT_TYPE):
    """Ledger poll — the ONLY way bots hear each other (Telegram never delivers bot
    messages to bots). Processes kind=='bot' entries from peers exclusively; human
    entries are chain-reset markers, consumed silently (design §1 — acting on them
    here would double-answer messages already handled live)."""
    for gid in GROUP_ALLOWED_CHATS:
        try:
            entries = await asyncio.to_thread(_ledger_read_new, gid)
        except Exception:
            continue
        now = time.time()
        my_first = _char_first_name()
        for e in entries:
            if e.get("sender") == my_first:
                continue
            if now - float(e.get("ts", 0)) > GROUP_LEDGER_MAX_AGE_SECONDS:
                continue
            if e.get("kind") != "bot":
                if e.get("sender"):
                    user_names[gid] = e["sender"]  # cache {{user}}; nothing else
                continue
            await _maybe_reply_to_bot(context, gid, e)
    await asyncio.to_thread(_prune_claims)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not _is_allowed(update.effective_user.id):
        return
    if not _rate_ok(update.effective_user.id):
        return
    if chat_id < 0:
        # Only a participating instance's live human text gets this far (group_guard).
        if GROUP_MODE and chat_id in GROUP_ALLOWED_CHATS:
            await _handle_group_message(update, context)
        return
    old_away = _clear_away(chat_id)
    if old_away:
        _just_returned[chat_id] = {"reason": old_away.get("reason", "away")}
        save_state()
        print(f"[away] auto-cleared for {chat_id} (was: {old_away.get('reason')})")
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

        link_url = None
        if LINK_READING:
            link = _URL_RE.search(user_message)
            if link:
                link_url = link.group(0)
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # Run inner voice + link fetch in parallel to cut wall-clock latency.
        parallel = []
        if INNER_VOICE_ENABLED:
            parallel.append(generate_inner_voice(chat_id, user_message, user_names[chat_id]))
        if link_url:
            parallel.append(asyncio.to_thread(fetch_link, link_url))

        if parallel:
            results = await asyncio.gather(*parallel, return_exceptions=True)
        else:
            results = []

        idx = 0
        if INNER_VOICE_ENABLED:
            inner_voice = results[idx] if not isinstance(results[idx], BaseException) else ""
            idx += 1
        else:
            inner_voice = ""
        if link_url:
            fetched = results[idx] if not isinstance(results[idx], BaseException) else None
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

        messages = assemble_messages(chat_id, content_for_model, inner_voice=inner_voice)
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
        desc = await asyncio.to_thread(call_nanogpt, messages, VISION_MODEL, VISION_FALLBACK)
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
        log.error("[photo-memory] failed: %s", e)
        _count_error("media")


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
        log.warning("[followup] error for chat %s: %s", chat_id, e)


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
            f"⚠️ Vision API Error ({VISION_MODEL}): {e.response.status_code} — {e.response.text[:200]}")
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
        log.error("[sticker] error: %s", e)
        _count_error("media")


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
PHOTO_SELFIE_CHANCE = _env_float("PHOTO_SELFIE_CHANCE", "0.20")

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
FOLLOWUP_MIN = _env_float("FOLLOWUP_MIN_SECS", "45")
FOLLOWUP_MAX = _env_float("FOLLOWUP_MAX_SECS", "120")
_pending_followup: dict = {}  # chat_id -> scheduled job object (cancel if user replies first)

# Selfie scene deduplication — avoids repeating the same scenario in back-to-back selfies.
SELFIE_DEDUP_SIZE = _env_int("SELFIE_DEDUP_SIZE", "6")
_recent_selfie_hints: dict = {}  # chat_id -> list of recent scene descriptions

# Proactive hook dedup — avoids repeating the same pattern in back-to-back heartbeats.
PROACTIVE_HOOK_DEDUP_SIZE = _env_int("PROACTIVE_HOOK_DEDUP_SIZE", "8")
_recent_proactive_hooks: dict = {}  # chat_id -> list of recent hook sentences

# Question memory — tracks questions the bot has asked recently; avoids repeating them.
QUESTION_MEMORY_SIZE = _env_int("QUESTION_MEMORY_SIZE", "8")
_recent_questions: dict = {}  # chat_id -> list of recent questions

_QUESTION_RE = re.compile(r"[^.!?…]*\?")  # quick sentence-level question extractor


def _extract_last_question(text: str) -> str:
    matches = _QUESTION_RE.findall(text)
    return matches[-1].strip() if matches else ""

# Lull detection: consecutive terse replies trigger a gentle approach shift.
_terse_count: dict = {}  # chat_id -> int
LULL_THRESHOLD = _env_int("LULL_THRESHOLD", "3")

def _is_terse(text: str) -> bool:
    return len(text.strip()) <= 15

# Gap-aware opener: when user returns after a long absence, note it in that turn's context.
GAP_AWARE_HOURS = _env_float("GAP_AWARE_HOURS", "12")


async def send_triggered(context: ContextTypes.DEFAULT_TYPE, chat_id: int, trigger: str):
    """Generate and deliver an unprompted message from a [SYSTEM: ...] trigger (no user message to react to)."""
    uname = user_names.get(chat_id, "you")
    await ensure_weather()
    messages = assemble_messages(chat_id, trigger)
    text = await reply_with_typing(context, chat_id, messages, fallback=FALLBACK_MODEL)
    text = await maybe_search(context, chat_id, messages, text, uname)
    clean, _reaction, selfie_hint, meme_caption = extract_tags(text)
    if clean:
        clean = _strip_persona_breaks(clean)
    # Store a synthetic user entry so conversation history maintains proper user/assistant
    # alternation. Without it, two consecutive assistant turns confuse some models when
    # the user replies and the history is dumped into the next request.
    remember(chat_id, "user", f"[you reached out to {uname} first — no incoming message]")
    remember(chat_id, "assistant", clean or (
        "[sent a selfie]" if selfie_hint is not None else
        "[sent a meme]" if meme_caption is not None else ""
    ))
    if clean:
        await send_bubbles(context, chat_id, clean)
    if selfie_hint is not None:
        await send_selfie(context, chat_id, selfie_hint, announce_errors=False)
    if meme_caption is not None:
        await send_meme(context, chat_id, top=meme_caption[0], bottom=meme_caption[1], announce_errors=False)
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
        if _is_own_day_fact(f):
            continue  # her own archived days start with a date — not anniversaries
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
        log.error("[cron #%s] Error: %s", job_id, e)
        _count_error("cron")


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
    now_dt = datetime.now(TZ) if TZ else datetime.now()
    if _in_quiet_window(now_dt, quiet_windows.get(owner, [])):
        print("[heartbeat] In recurring quiet window; skipping.")
        return
    if _is_away(owner):
        print("[heartbeat] User /away active; skipping.")
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
        log.error("[heartbeat] Error: %s", e)
        _count_error("heartbeat")


_DUE_NOTE_RE = re.compile(r"^(?P<note>.*\S)\s+\(due (?P<date>\d{4}-\d{2}-\d{2})\)\s*$")

async def note_followup_job(context: ContextTypes.DEFAULT_TYPE):
    """Daily: if a dated user note has come due, reach out and ask how it went.

    At most one follow-up per firing — being remembered should feel rare and real,
    not like a notification system."""
    owner = get_owner()
    now_dt = datetime.now(TZ) if TZ else datetime.now()
    if owner is None or _is_quiet(owner) or _is_away(owner) or in_quiet_hours() or _in_quiet_window(now_dt, quiet_windows.get(owner, [])):
        return
    if not USER_NOTES_FILE.exists():
        return
    today = (datetime.now(TZ) if TZ else datetime.now()).date()
    lines = USER_NOTES_FILE.read_text(encoding="utf-8").splitlines()
    hit = None  # (line index, note text, due date) — oldest due note wins
    for i, line in enumerate(lines):
        m = _DUE_NOTE_RE.match(line.strip())
        if not m:
            continue
        try:
            d = date.fromisoformat(m.group("date"))
        except ValueError:
            continue
        if d <= today and (hit is None or d < hit[2]):
            hit = (i, m.group("note"), d)
    if hit is None:
        return
    if not _check_nudge_budget(owner):
        return  # budget spent; the (due) marker survives, so we retry tomorrow
    i, note, d = hit
    days_ago = (today - d).days
    when = "today" if days_ago == 0 else ("yesterday" if days_ago == 1 else f"{days_ago} days ago")
    uname = user_names.get(owner, "you")
    trigger = (
        f'[SYSTEM: {uname} mentioned this: "{note}" — that was {when}. Reach out unprompted '
        f"and ask how it went, specific and in character, 1-2 sentences. If it clearly hasn't "
        f"happened yet today, wish them luck instead. Don't mention this message is automated.]"
    )
    try:
        await send_triggered(context, owner, trigger)
        _consume_nudge(owner)
        lines[i] = f"{note} (asked {today.isoformat()})"
        USER_NOTES_FILE.write_text("\n".join(lines), encoding="utf-8")
        _user_notes_cache["text"] = None
        print(f"[note-followup] asked about: {note}")
    except Exception as e:
        log.warning("[note-followup] failed: %s", e)
        _count_error("heartbeat")


async def selfie_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_names[chat_id] = update.effective_user.first_name or "you"
    hint = " ".join(context.args).strip() if context.args else ""
    await ensure_weather()  # so the selfie reflects the current weather
    await send_selfie(context, chat_id, hint, announce_errors=True)


async def meme_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id):
        return
    chat_id = update.effective_chat.id
    user_names[chat_id] = update.effective_user.first_name or "you"
    hint = " ".join(context.args).strip() if context.args else ""
    await send_meme(context, chat_id, hint, announce_errors=True)


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


async def reflection_job(context: ContextTypes.DEFAULT_TYPE):
    owner = get_owner()
    if owner is None:
        return
    try:
        await reflect(owner)
    except Exception as e:
        log.error("[reflect] Error: %s", e)
    try:
        await maintain_long_term_memory(owner)
    except Exception as e:
        log.warning("[memory] long-term promotion error: %s", e)
        _count_error("memory")
    _overnight_mood_reset(owner)


async def reflect_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        await reflect(chat_id)
        await update.message.reply_text("🪞 Reflection done.")
    except Exception as e:
        await update.message.reply_text(f"❌ Reflection failed: {str(e)}")


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

    cl = closeness.get(chat_id)
    if cl:
        lines.append(f"*Closeness:* {cl['bucket']} ({cl['score']:.2f})")

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

    wins = quiet_windows.get(chat_id, [])
    if wins:
        win_strs = []
        for w in wins:
            sh = f"{w['start'] // 60:02d}:{w['start'] % 60:02d}"
            eh = f"{w['end'] // 60:02d}:{w['end'] % 60:02d}"
            win_strs.append(f"{_DOW_DISPLAY[w['dow']]} {sh}–{eh}")
        lines.append(f"*Quiet windows:* {', '.join(win_strs)}")

    aw = away.get(chat_id)
    if aw and _is_away(chat_id):
        since = aw.get("since", 0)
        ago = int((time.time() - since) / 60) if since else 0
        reason = aw.get("reason", "away")
        origin = aw.get("origin", "manual")
        exp = aw.get("expires")
        exp_str = ""
        if exp:
            remaining_m = max(0, int((exp - time.time()) / 60))
            exp_str = f" (auto-expires in {remaining_m}m)"
        lines.append(f"*Away:* {reason} ({ago}m, {origin}){exp_str}")

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

    # Conversation tail — last 3 messages truncated to ~80 chars
    hist = conversation_history.get(chat_id, [])
    if hist:
        lines.append("")
        lines.append("*Recent:*")
        for msg in hist[-3:]:
            role = msg.get("role", "user")
            speaker = "You" if role == "user" else NAME
            text = (msg.get("content") or "").replace("\n", " ").strip()
            if len(text) > 80:
                text = text[:77] + "…"
            lines.append(f"  {speaker}: {text}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _generate_daily_events(owner: int, yesterday: str = ""):
    """Generate 2-3 small life events for the day using the character's people, projects,
    and schedule as seeds. Writes the result to day.txt so it's ready when she texts.

    When yesterday's events are passed in, one of today's items may continue or pay off
    a hanging thread — multi-day micro-arcs instead of a life that resets at midnight."""
    try:
        people = _read_people()
        projects = _read_projects()
        schedule_today = _read_schedule_today()
        await ensure_weather()
        weather = (_weather_cache.get("text") or "").strip()

        world_ctx = _read_world_context()

        ctx_parts = []
        if world_ctx:
            ctx_parts.append(f"Shared world (same for everyone today):\n{world_ctx}")
        if schedule_today:
            ctx_parts.append(f"Her schedule today: {schedule_today}")
        if weather and not world_ctx:
            ctx_parts.append(f"Weather: {weather}")
        if projects:
            ctx_parts.append(f"Ongoing things in her life:\n{projects}")
        if people:
            ctx_parts.append(f"People in her life:\n{people}")
        if yesterday:
            ctx_parts.append(
                f"Yesterday: {yesterday[:400]}\n"
                f"If yesterday left something hanging — a plan, an errand, a person, a mood — "
                f"let ONE of today's items continue or pay it off naturally. The rest should be "
                f"fresh. Some days nothing carries over; that's fine."
            )

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
        events = await asyncio.to_thread(call_nanogpt, msgs, SUMMARY_MODEL)
        events = _strip_thinking(events).strip()
        if events:
            DAY_FILE.write_text(events, encoding="utf-8")
            _day_cache["text"] = events
            _day_cache["ts"] = time.time()
            print(f"[day-events] {NAME}: {events[:100]}…")
    except Exception as e:
        log.error("[day-events] failed: %s", e)


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
            log.error("[day-rotate] archive failed: %s", e)
        # Save a compact continuity note — tagged as her OWN day so memory consumers
        # never present it as a fact about the user (see _OWN_DAY_PREFIX).
        if owner is not None:
            fact = f"[own-day {yesterday.strftime('%b %d')}] {day_ctx[:300]}"
            rfts = recent_facts.setdefault(owner, [])
            rfts.append(fact)
            own = [f for f in rfts if _is_own_day_fact(f)]
            for stale in own[:-OWN_DAYS_KEPT]:  # her fiction must not crowd real facts
                rfts.remove(stale)
            if len(rfts) > RECENT_FACTS_MAX:
                rfts.pop(0)
            save_state()
        print(f"[day-rotate] archived {date_str}: {day_ctx[:80]}…")
    # If this instance is the world generator, produce world.txt before any instance
    # generates its day events — all instances read it as shared context.
    if WORLD_GENERATOR:
        try:
            await ensure_weather()
            weather = (_weather_cache.get("text") or "").strip()
            w_prompt = (
                f"Write a brief shared-world snapshot for today (2-3 lines max). "
                f"Include: the weather mood ({weather or 'unknown'}), and one or two "
                f"small ambient things happening in the area — a local event, construction, "
                f"a seasonal detail, something noticed on the street. Keep it terse and "
                f"grounded. No character names — this is the shared backdrop, not anyone's "
                f"personal day.\n\nWrite only the snapshot, no headers or bullets."
            )
            w_msgs = [{"role": "system", "content": "You describe the shared world."},
                      {"role": "user", "content": w_prompt}]
            world_text = await asyncio.to_thread(call_nanogpt, w_msgs, SUMMARY_MODEL)
            world_text = _strip_thinking(world_text).strip()
            if world_text:
                WORLD_FILE.write_text(world_text, encoding="utf-8")
                print(f"[world] generated: {world_text[:100]}…")
        except Exception as e:
            log.error("[world] generation failed: %s", e)

    # Generate fresh events for the new day (writes to day.txt, clears cache implicitly),
    # feeding in yesterday's events so unresolved threads can carry over.
    if owner is not None:
        await _generate_daily_events(owner, yesterday=day_ctx)
    else:
        # No owner yet — just clear the file
        try:
            DAY_FILE.write_text("", encoding="utf-8")
        except Exception:
            pass
        _day_cache["text"] = ""
        _day_cache["ts"] = time.time()

    # Recompute closeness for all active chats
    if CLOSENESS_ENABLED:
        _recompute_all_closeness()


def _recompute_all_closeness():
    today = _today_str()
    for cid in list(conversation_history.keys()):
        hist = conversation_history.get(cid, [])
        msg_count = len(hist)
        ms_count = len(milestones.get(cid, []))
        b_items = (beliefs.get(cid) or {}).get("items") or {}
        b_count = len(b_items)
        timestamps = [m.get("ts", 0) for m in hist if m.get("ts")]
        if timestamps:
            first_ts = min(timestamps)
            days_active = max(1, int((time.time() - first_ts) / 86400))
        else:
            days_active = 0
        score, bucket = _compute_closeness(days_active, msg_count, ms_count, b_count)
        closeness[cid] = {"score": score, "bucket": bucket, "updated": today}
    save_state()


async def selfimage_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    items = beliefs.get(chat_id, {}).get("items") or {}
    if not items:
        await update.message.reply_text("Nothing yet — runs at the first nightly reflection.")
        return
    lines = [f"• {t}: {d['score']}/10 (baseline {d['anchor']}/10)" for t, d in items.items()]
    recs = recommendations.get(chat_id, [])
    open_recs = [r for r in recs if r["status"] == "open"]
    resolved = [r for r in recs if r["status"] != "open"]
    rec_lines = [f"• {r['text']}" for r in open_recs] or ["(none)"]
    res_lines = [f"• {r['text']} — {r['outcome']}: {r['note']}" for r in resolved[-5:]] or ["(none)"]
    goal = (next_goals.get(chat_id) or "").strip() or "(none)"
    await update.message.reply_text(
        f"🪞 {NAME}'s self-image\n\n" + "\n".join(lines) +
        "\n\nOpen (waiting on an outcome):\n" + "\n".join(rec_lines) +
        "\n\nRecently resolved:\n" + "\n".join(res_lines) +
        f"\n\nNext-conversation goal:\n{goal}"
    )


# --- Reverse geocoding (OSM Nominatim — free, no key required) ---

def _reverse_geocode_sync(lat: float, lon: float) -> str:
    """Return a region name for coordinates, or '' on failure. Call via asyncio.to_thread."""
    try:
        url = (f"https://nominatim.openstreetmap.org/reverse"
               f"?lat={lat}&lon={lon}&format=json&zoom=10")
        r = _get_session().get(url, headers={"User-Agent": "SillyTavernBot/1.0"}, timeout=5)
        r.raise_for_status()
        addr = r.json().get("address", {})
        parts = [p for p in [
            addr.get("county") or addr.get("city"),
            addr.get("state"),
        ] if p]
        return ", ".join(parts)
    except Exception:
        return ""


# --- TomTom Maps integration (routing, place/POI search) ---
# bot.py calls the raw api.tomtom.com REST endpoints directly, which return
# TomTom's NATIVE JSON (results[]/routes[]), not the GeoJSON the MCP tools emit.
# Every parser below is defensive: each field access degrades to a safe default
# so a response-shape change can't crash a bot (same discipline as WSDOT below).

_TOMTOM_SEARCH_URL  = "https://api.tomtom.com/search/2/search/{q}.json"
_TOMTOM_GEOCODE_URL = "https://api.tomtom.com/search/2/geocode/{q}.json"
_TOMTOM_NEARBY_URL  = "https://api.tomtom.com/search/2/nearbySearch/.json"
_TOMTOM_ROUTE_URL   = "https://api.tomtom.com/routing/1/calculateRoute/{o}:{d}/json"
_TOMTOM_MODES       = {"car", "bicycle", "pedestrian", "truck", "taxi", "bus", "van", "motorcycle"}


def _tomtom_mode() -> str:
    """Validated per-instance travel mode; bad value warns and falls back to car."""
    m = os.getenv("TOMTOM_TRAVEL_MODE", "car").strip().lower()
    if m not in _TOMTOM_MODES:
        log.warning("[tomtom] invalid TOMTOM_TRAVEL_MODE %r; using 'car'", m)
        return "car"
    return m


def _fmt_distance(meters) -> str:
    """US-unit distance: feet under ~0.1 mi, else miles. Total on bad input."""
    try:
        m = float(meters)
    except (TypeError, ValueError):
        return "?"
    mi = m / 1609.344
    if mi < 0.1:
        return f"{round(m * 3.28084)} ft"
    return f"{mi:.1f} mi"


def _fmt_duration(seconds) -> str:
    """Human duration from seconds. Total on bad input."""
    try:
        s = max(0, int(seconds))
    except (TypeError, ValueError):
        return "?"
    mins = s // 60
    if mins < 60:
        return f"{mins} min"
    h, m = divmod(mins, 60)
    return f"{h} hr {m} min" if m else f"{h} hr"


def _parse_route_query(text: str):
    """'A to B' or 'from A to B' -> ('A','B'); None if unparseable.
    Splits on the LAST ' to ' so a destination containing ' to ' still parses."""
    if not text:
        return None
    t = text.strip()
    if t.lower().startswith("from "):
        t = t[5:]
    idx = t.lower().rfind(" to ")
    if idx == -1:
        return None
    origin, dest = t[:idx].strip(), t[idx + 4:].strip()
    if not origin or not dest:
        return None
    return origin, dest


def _format_route(route: dict, mode: str) -> str:
    """TomTom Routing native response -> summary line. Total/defensive."""
    routes = (route or {}).get("routes") or []
    if not routes:
        return "No route found."
    summ = (routes[0] or {}).get("summary") or {}
    verb = {"bicycle": "🚲 Bike", "pedestrian": "🚶 Walk"}.get(mode, "🚗 Drive")
    line = f"{verb}: {_fmt_duration(summ.get('travelTimeInSeconds'))} · {_fmt_distance(summ.get('lengthInMeters'))}"
    try:
        if int(summ.get("trafficDelayInSeconds") or 0) >= 60:
            line += f" (incl. +{_fmt_duration(summ.get('trafficDelayInSeconds'))} traffic)"
    except (TypeError, ValueError):
        pass
    return line


def _format_place_results(results: list, limit: int = 3) -> str:
    """TomTom Search native 'results' -> readable list. Total/defensive."""
    out = []
    for r in (results or [])[:limit]:
        poi = (r or {}).get("poi") or {}
        addr = (r or {}).get("address") or {}
        name = poi.get("name") or addr.get("freeformAddress") or "Unknown"
        line = f"📍 {name}"
        fa = addr.get("freeformAddress")
        if fa and fa != name:
            line += f"\n   {fa}"
        if poi.get("phone"):
            line += f"\n   ☎ {poi['phone']}"
        out.append(line)
    return "\n\n".join(out) if out else "No matches found."


def _format_nearby_results(results: list, limit: int = 5) -> str:
    """TomTom Search results carrying 'dist' (meters) -> distance-sorted list."""
    rows = [r for r in (results or []) if isinstance(r, dict)]
    rows.sort(key=lambda r: r.get("dist") if isinstance(r.get("dist"), (int, float)) else 9e9)
    out = []
    for r in rows[:limit]:
        poi = r.get("poi") or {}
        addr = r.get("address") or {}
        name = poi.get("name") or addr.get("freeformAddress") or "Unknown"
        dist = r.get("dist")
        tag = f" · {_fmt_distance(dist)}" if isinstance(dist, (int, float)) else ""
        line = f"📍 {name}{tag}"
        street = addr.get("streetName") or addr.get("freeformAddress")
        if street and street != name:
            line += f"\n   {street}"
        out.append(line)
    return "\n\n".join(out) if out else "Nothing found nearby."


def _tomtom_geocode(query: str):
    """Query -> (lat, lon, label) or None. Network; defensive."""
    try:
        from urllib.parse import quote
        r = _get_session().get(
            _TOMTOM_GEOCODE_URL.format(q=quote(query)),
            params={"key": TOMTOM_API_KEY, "limit": 1, "countrySet": "US"},
            timeout=(10, 30),
        )
        r.raise_for_status()
        results = (r.json() or {}).get("results") or []
        if not results:
            return None
        pos = (results[0] or {}).get("position") or {}
        lat, lon = pos.get("lat"), pos.get("lon")
        if lat is None or lon is None:
            return None
        label = ((results[0].get("address") or {}).get("freeformAddress")) or query
        return float(lat), float(lon), label
    except Exception as e:
        log.warning("[tomtom] geocode failed for %r: %s", query, e)
        return None


def _fetch_tomtom_route(o, d, mode: str):
    """o, d are (lat, lon) tuples. Returns native routing dict or None."""
    try:
        r = _get_session().get(
            _TOMTOM_ROUTE_URL.format(o=f"{o[0]},{o[1]}", d=f"{d[0]},{d[1]}"),
            params={"key": TOMTOM_API_KEY, "travelMode": mode, "traffic": "true", "routeType": "fast"},
            timeout=(10, 30),
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("[tomtom] route fetch failed: %s", e)
        return None


def _fetch_tomtom_search(query: str, lat=None, lon=None, radius_m=None) -> list:
    """Search/geocode a free-text query, optionally biased to a point. Returns results[]."""
    try:
        from urllib.parse import quote
        params = {"key": TOMTOM_API_KEY, "limit": 5, "countrySet": "US"}
        if lat is not None and lon is not None:
            params["lat"], params["lon"] = lat, lon
            if radius_m:
                params["radius"] = int(radius_m)
        r = _get_session().get(_TOMTOM_SEARCH_URL.format(q=quote(query)), params=params, timeout=(10, 30))
        r.raise_for_status()
        return (r.json() or {}).get("results") or []
    except Exception as e:
        log.warning("[tomtom] search failed for %r: %s", query, e)
        return []


async def route_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TOMTOM_ENABLED:
        await update.message.reply_text("Maps aren't set up (TOMTOM_API_KEY missing).")
        return
    parsed = _parse_route_query(" ".join(context.args) if context.args else "")
    if not parsed:
        await update.message.reply_text("Usage: /route <from> to <destination>\ne.g. /route Bellevue to SeaTac airport")
        return
    origin_q, dest_q = parsed
    mode = _tomtom_mode()
    o = await asyncio.to_thread(_tomtom_geocode, origin_q)
    if not o:
        await update.message.reply_text(f"Couldn't find “{origin_q}”.")
        return
    d = await asyncio.to_thread(_tomtom_geocode, dest_q)
    if not d:
        await update.message.reply_text(f"Couldn't find “{dest_q}”.")
        return
    route = await asyncio.to_thread(_fetch_tomtom_route, (o[0], o[1]), (d[0], d[1]), mode)
    await update.message.reply_text(f"🗺 {o[2]} → {d[2]}\n{_format_route(route, mode)}")


async def nearby_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TOMTOM_ENABLED:
        await update.message.reply_text("Maps aren't set up (TOMTOM_API_KEY missing).")
        return
    loc = user_location.get(update.effective_chat.id)
    if not loc:
        await update.message.reply_text("Share your location first (📎 → Location), then /nearby <thing>.")
        return
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /nearby <thing>\ne.g. /nearby coffee")
        return
    results = await asyncio.to_thread(_fetch_tomtom_search, query, loc["lat"], loc["lon"], 3000)
    await update.message.reply_text(f"📍 “{query}” near you\n\n{_format_nearby_results(results)}")


async def place_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TOMTOM_ENABLED:
        await update.message.reply_text("Maps aren't set up (TOMTOM_API_KEY missing).")
        return
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /place <name or address>\ne.g. /place Pike Place Market")
        return
    loc = user_location.get(update.effective_chat.id)
    lat = loc["lat"] if loc else None
    lon = loc["lon"] if loc else None
    results = await asyncio.to_thread(_fetch_tomtom_search, query, lat, lon, None)
    await update.message.reply_text(f"🔎 {query}\n\n{_format_place_results(results)}")


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
        r = _get_session().get(_WSDOT_ALERTS_URL, params={"AccessCode": WSDOT_API_KEY}, timeout=(10, 30))
        r.raise_for_status()
        data = r.json()
        # GetAlertsAsJson returns a bare array; older docs show {"Alerts": [...]}.
        if isinstance(data, list):
            return data
        return data.get("Alerts") or []
    except Exception as e:
        log.warning("[traffic] alerts fetch failed: %s", e)
        return []


def _fetch_wsdot_times() -> list:
    try:
        r = _get_session().get(_WSDOT_TIMES_URL, params={"AccessCode": WSDOT_API_KEY}, timeout=(10, 30))
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
        if _is_away(chat_id):
            continue

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


# --- Self-audit ---
def _log_startup_diagnostic():
    import platform, shutil
    disk = shutil.disk_usage(BASE_DIR)
    state_size = STATE_FILE.stat().st_size if STATE_FILE.exists() else 0
    err_size = _error_log_path.stat().st_size if _error_log_path.exists() else 0
    log.warning(
        "=== STARTUP AUDIT === v%s | Python %s | Instance: %s | Card: %s | "
        "Model: %s | Fallback: %s | Stream timeout: %ds | Max tokens: %d | "
        "Disk free: %d MB | state.json: %d bytes | errors.log: %d bytes | Chats: %d | PID: %d",
        BOT_VERSION, platform.python_version(), BASE_DIR.name, CARD_NAME,
        NANOGPT_MODEL, FALLBACK_MODEL or "(none)",
        STREAM_TIMEOUT, MAX_TOKENS,
        disk.free // (1024 * 1024), state_size, err_size,
        len(conversation_history), os.getpid(),
    )


_restart_alert_ts = 0.0  # cooldown: a restart storm alerts once, not every 30 min
_fallback_alert_ts = 0.0
_budget_alert_ts = 0.0

def _count_recent_restarts(window_s: int = 3600) -> int:
    """Count STARTUP AUDIT lines in errors.log newer than window_s seconds.
    Each line marks a process start, so >1 in an hour means something is killing us.

    Compares naive wall-clock datetimes directly (never converting through Unix epoch)
    so this stays correct even if the OS's local-time calibration is off — e.g. right
    after a pkg upgrade disrupts tzdata. time.mktime() would silently misjudge every
    historical line as "recent" in that case, which is exactly the false-alarm bug this
    replaced (every bot on the same phone would misfire identically)."""
    try:
        if not _error_log_path.exists():
            return 0
        cutoff = datetime.now() - timedelta(seconds=window_s)
        n = 0
        for line in _error_log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=== STARTUP AUDIT ===" not in line:
                continue
            try:
                ts = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if ts >= cutoff:
                n += 1
        return n
    except Exception:
        return 0


async def _self_audit(context: ContextTypes.DEFAULT_TYPE):
    global _restart_alert_ts, _fallback_alert_ts, _budget_alert_ts
    issues = []
    uptime_h = (time.time() - _BOOT_TIME) / 3600

    hour_ago = time.time() - 3600
    stale = [uid for uid, ts in list(_last_request.items()) if ts < hour_ago]
    for uid in stale:
        _last_request.pop(uid, None)
    # snapshot: _count_error appends from worker threads; iterating the live dict/lists
    # here can raise 'changed size during iteration'
    recent = {cat: sum(1 for t in list(ts) if t > hour_ago)
              for cat, ts in list(_error_counts.items())}
    total_recent = sum(recent.values())
    total_all = sum(len(ts) for ts in list(_error_counts.values()))

    try:
        if STATE_FILE.exists():
            json.loads(STATE_FILE.read_text(encoding="utf-8"))
        else:
            issues.append("state.json missing")
    except Exception as e:
        issues.append(f"state.json corrupt: {e}")

    try:
        err_size = _error_log_path.stat().st_size if _error_log_path.exists() else 0
    except Exception:
        err_size = -1
        issues.append("errors.log not accessible")

    try:
        import shutil
        free_mb = shutil.disk_usage(BASE_DIR).free // (1024 * 1024)
        if free_mb < 50:
            issues.append(f"low disk: {free_mb} MB free")
    except Exception:
        free_mb = -1

    # Restart-storm self-report: a revived bot tells on whatever keeps killing it.
    restarts = _count_recent_restarts()
    if restarts >= 3 and time.time() - _restart_alert_ts > 7200:
        _restart_alert_ts = time.time()
        issues.append(
            f"restarted {restarts}x in the last hour — something is killing the process. "
            f"Check /errors: a '[shutdown] graceful stop' line before a startup audit "
            f"means it was signaled (a real Termux/Android battery-management restriction, "
            f"not the phantom killer, which can't be caught at all — no line = SIGKILL, "
            f"check: adb shell settings get global settings_enable_monitor_phantom_procs)"
        )

    fallback_1h = recent.get("fallback", 0)
    if fallback_1h >= 3 and time.time() - _fallback_alert_ts > 7200:
        _fallback_alert_ts = time.time()
        issues.append(
            f"primary model falling back {fallback_1h}x in the last hour — "
            f"check /model and /errors; the fallback is serving replies silently"
        )

    if USAGE_BUDGET_MONTHLY:
        try:
            resp = await asyncio.to_thread(
                lambda: _get_session().get(
                    f"{NANOGPT_BASE_URL.rsplit('/v1', 1)[0]}/subscription/v1/usage",
                    headers={"Authorization": f"Bearer {NANOGPT_API_KEY}"},
                    timeout=15))
            usage = resp.json()
            if usage.get("active"):
                used = float(usage["monthly"]["used"])
                pct = used / USAGE_BUDGET_MONTHLY
                if pct >= 1.0 and time.time() - _budget_alert_ts > 86400:
                    _budget_alert_ts = time.time()
                    issues.append(f"monthly spend at {pct:.0%} of budget ({used:.0f}/{USAGE_BUDGET_MONTHLY:.0f})")
                elif pct >= 0.8 and time.time() - _budget_alert_ts > 86400:
                    _budget_alert_ts = time.time()
                    issues.append(f"monthly spend at {pct:.0%} of budget ({used:.0f}/{USAGE_BUDGET_MONTHLY:.0f})")
        except Exception as e:
            log.debug("[audit] usage check failed: %s", e)

    status = "ISSUES" if issues else "OK"
    summary = (f"[audit] {status} | uptime={uptime_h:.1f}h | "
               f"errors_1h={total_recent} total={total_all} | "
               f"disk_free={free_mb}MB | error_log={err_size}b")
    if recent:
        summary += " | " + " ".join(f"{k}={v}" for k, v in sorted(recent.items()) if v)

    if issues:
        log.warning("%s | issues: %s", summary, "; ".join(issues))
        owner = get_owner()
        if owner:
            try:
                await context.bot.send_message(chat_id=owner, text=f"🔧 {'; '.join(issues)}")
            except Exception:
                pass
    else:
        log.info(summary)

    # Dead man's switch: prove liveness to the external monitor. If these pings stop,
    # the service alerts the owner — covering everything a dead bot can't report.
    if HEALTHCHECK_URL:
        try:
            await asyncio.to_thread(
                lambda: _get_session().get(HEALTHCHECK_URL, timeout=10))
        except Exception as e:
            log.warning("[audit] healthcheck ping failed: %s", e)


def gather_audit_data() -> dict:
    """Self-audit facts as plain data — shared by /audit and the admin HTTP API."""
    uptime_h = (time.time() - _BOOT_TIME) / 3600
    hour_ago = time.time() - 3600
    # snapshot: _count_error appends from worker threads; iterating the live dict/lists
    # here can raise 'changed size during iteration'
    recent = {cat: sum(1 for t in list(ts) if t > hour_ago)
              for cat, ts in list(_error_counts.items())}
    total_all = sum(len(ts) for ts in list(_error_counts.values()))

    state_ok = "OK"
    try:
        if STATE_FILE.exists():
            json.loads(STATE_FILE.read_text(encoding="utf-8"))
        else:
            state_ok = "MISSING"
    except Exception:
        state_ok = "CORRUPT"

    err_size = _error_log_path.stat().st_size if _error_log_path.exists() else 0
    bot_log = BASE_DIR / "bot.log"
    bot_log_size = bot_log.stat().st_size if bot_log.exists() else 0

    review_count = len(_load_memory_review())

    return {
        "version": BOT_VERSION,
        "uptime_hours": round(uptime_h, 1),
        "errors_last_hour": {k: v for k, v in recent.items() if v},
        "errors_last_hour_total": sum(recent.values()),
        "errors_total": total_all,
        "state_file": state_ok,
        "errors_log_kb": round(err_size / 1024, 1),
        "bot_log_kb": round(bot_log_size / 1024, 1),
        "pid": os.getpid(),
        "memory_review_pending": review_count,
        "away_users": {str(k): v.get("reason", "away") for k, v in away.items()},
        "config_warnings": list(_CONFIG_WARNINGS),
        "llm_stats": dict(_llm_stats),
    }


async def audit_cmd(update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    d = gather_audit_data()
    lines = [
        f"🔧 *Self-Audit* (v{d['version']})",
        f"Uptime: {d['uptime_hours']}h",
        f"Errors (last hour): {d['errors_last_hour_total']}",
    ]
    if d["errors_last_hour"]:
        lines.append("  " + ", ".join(f"{k}: {v}" for k, v in sorted(d["errors_last_hour"].items())))
    lines += [
        f"Errors (total): {d['errors_total']}",
        f"State file: {d['state_file']}",
        f"errors.log: {d['errors_log_kb']} KB",
        f"bot.log: {d['bot_log_kb']} KB",
        f"PID: {d['pid']}",
    ]
    if d.get("memory_review_pending"):
        lines.append(f"Memory: {d['memory_review_pending']} pending review")
    llm = d.get("llm_stats", {})
    if llm.get("calls"):
        lines.append(
            f"LLM today: {llm['calls']} calls, "
            f"~{llm['tok_in'] // 1000}k in / ~{llm['tok_out'] // 1000}k out (est)")
    cw = d.get("config_warnings", [])
    if cw:
        lines.append(f"Config warnings: {len(cw)}")
        for w in cw[:3]:
            lines.append(f"  ⚠️ {w}")
    if GROUP_MODE and GROUP_ALLOWED_CHATS:
        # "Why did she stop replying to Jules?" must be answerable from Telegram:
        # budget or chain cap, and which (GROUP_CHAT_DESIGN.md §11).
        for gid in sorted(GROUP_ALLOWED_CHATS):
            lp = _group_ledger_path(gid)
            lsize = round(lp.stat().st_size / 1024, 1) if lp.exists() else 0
            b = group_bot_sends_today.get(gid) or {}
            chain = _bot_chain_len(await asyncio.to_thread(_ledger_tail, gid, 10))
            lines.append(
                f"Group {gid}: ledger {lsize} KB, bot-sends today "
                f"{b.get('count', 0)}/{GROUP_DAILY_BOT_BUDGET}, chain {chain}/{GROUP_BOT_CHAIN_MAX}"
            )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def tail_error_lines(n: int = 20) -> list[str]:
    """Last n non-blank lines of errors.log — shared by /errors and the admin HTTP API."""
    n = max(1, min(n, 50))
    try:
        lines = _error_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        lines = []
    return [l for l in lines if l.strip()][-n:]


async def errors_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the tail of errors.log so bug reports carry evidence."""
    if not _is_admin(update.effective_user.id):
        return
    args = context.args or []
    try:
        n = max(1, min(int(args[0]), 50)) if args else 20
    except ValueError:
        n = 20
    lines = tail_error_lines(n)
    if not lines:
        await update.message.reply_text("✅ No errors logged.")
        return
    text = "\n".join(lines)
    # Telegram cap is 4096 chars; drop oldest lines until it fits.
    while len(text) > 3800 and len(lines) > 1:
        lines = lines[1:]
        text = "\n".join(lines)
    await update.message.reply_text(f"🪵 Last {len(lines)} error line(s):\n\n{text[:3900]}")


_RAW_BOT_URL = ("https://raw.githubusercontent.com/biggieb327-lgtm/"
                "SillyTavernPresets/main/telegram-companion-bot/bot.py")


def _schedule_exit(delay_s: float = 1.0):
    """Save state and exit after a short delay, instead of immediately.

    Both a Telegram reply and an admin HTTP API response must actually leave the
    process before it exits, or the caller sees a reset connection instead of the
    reply they were just sent. Telegram replies are awaited before this is called, so
    they're already flushed by the time we get here; the admin API's HTTP response is
    written just before this call returns control to the caller, and still needs a
    moment to reach the socket. threading.Timer runs on its own thread regardless of
    which thread calls it, so this is safe from both the asyncio event loop thread and
    an admin API request-handling thread.
    """
    def _exit():
        for _ in range(10):
            if not _replies_in_flight:
                break
            time.sleep(0.5)
        _write_state()
        os._exit(0)
    threading.Timer(delay_s, _exit).start()


def perform_self_update(force: bool = False) -> dict:
    """Fetch latest bot.py from main, verify it compiles, swap it in.

    Plain function shared by /update and the admin HTTP API's /admin/update — neither
    restarts the process itself; callers decide how (and whether) to schedule the exit
    after reporting the result back to whoever asked.
    """
    code_dir = Path(__file__).resolve().parent
    target = code_dir / "bot.py"
    tmp = code_dir / "bot.py.new"
    try:
        resp = _get_session().get(_RAW_BOT_URL, timeout=(10, 60))
        resp.raise_for_status()
        source = resp.text
    except Exception as e:
        return {"ok": False, "reason": "download_failed", "detail": str(e)}
    m = re.search(r'^BOT_VERSION\s*=\s*"([^"]+)"', source, re.M)
    new_version = m.group(1) if m else "unknown"
    if new_version == BOT_VERSION and not force:
        return {"ok": False, "reason": "already_current", "version": BOT_VERSION}
    import py_compile
    tmp.write_text(source, encoding="utf-8")
    cfile = str(tmp) + "c"
    try:
        py_compile.compile(str(tmp), cfile=cfile, doraise=True)
    except py_compile.PyCompileError as e:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "reason": "compile_failed", "detail": str(e)[:300],
                "version": BOT_VERSION}
    finally:
        Path(cfile).unlink(missing_ok=True)
    (code_dir / "bot.py.bak").write_bytes(target.read_bytes())
    tmp.replace(target)
    log.warning("[update] v%s -> v%s; restarting", BOT_VERSION, new_version)
    return {"ok": True, "old_version": BOT_VERSION, "new_version": new_version}


async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Self-deploy: fetch latest bot.py from main, verify it compiles, restart.

    The supervisor (run-bot.sh, or systemd on a VPS) restarts the process
    automatically, so exiting after a successful swap is all it takes to come back on
    the new code.
    """
    if not _is_admin(update.effective_user.id):
        return
    force = bool(context.args) and context.args[0].lower() == "force"
    result = await asyncio.to_thread(perform_self_update, force)
    if not result["ok"]:
        reason = result["reason"]
        if reason == "download_failed":
            await update.message.reply_text(f"⚠️ Download failed: {result['detail']}")
        elif reason == "already_current":
            await update.message.reply_text(
                f"✅ Already on v{result['version']}. Use /update force to reinstall anyway.")
        elif reason == "compile_failed":
            await update.message.reply_text(
                f"❌ New bot.py does not compile — keeping v{result['version']}.\n{result['detail']}")
        return
    await update.message.reply_text(
        f"⬆️ Updated v{result['old_version']} → v{result['new_version']}. "
        f"Restarting now — back in ~15s.\n"
        f"Other instances keep running old code until they get /update too.")
    _schedule_exit()


async def restart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clean restart via the supervisor — picks up .env edits and a swapped bot.py."""
    if not _is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🔄 Restarting — back in ~15s.")
    log.warning("[restart] requested via /restart")
    _schedule_exit()


# --- Admin HTTP API (opt-in) ---
# Mirrors /audit /errors /backup /update /restart over HTTP so a non-Telegram client
# (e.g. a control-panel app) can drive the same operations — only one process can poll
# a bot token for Telegram updates at a time, so that client can't just be a second
# Telegram client. Fully inert unless ADMIN_API_ENABLED is set: existing Termux
# instances that never set these vars are unaffected. Meant to be reachable only over
# a private Tailscale network, never the public internet — ADMIN_API_BIND defaults to
# loopback (never 0.0.0.0) so a misconfigured instance fails closed rather than open;
# set it to the host's Tailscale IP to actually expose it on a VPS.
ADMIN_API_ENABLED = os.getenv("ADMIN_API_ENABLED", "").strip().lower() in ("1", "true", "yes")
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "").strip()
ADMIN_API_PORT = _env_int("ADMIN_API_PORT", "8765")
ADMIN_API_BIND = os.getenv("ADMIN_API_BIND", "127.0.0.1").strip() or "127.0.0.1"

_admin_httpd = None


def _admin_authorized(handler: "_AdminRequestHandler") -> bool:
    if not ADMIN_API_TOKEN:
        return False
    got = handler.headers.get("Authorization", "")
    return secrets.compare_digest(got, f"Bearer {ADMIN_API_TOKEN}")


class _AdminRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info("[admin-api] %s - %s", self.address_string(), fmt % args)

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/admin/health":
            self._json(200, {"ok": True, "version": BOT_VERSION})
            return
        if not _admin_authorized(self):
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        if path == "/admin/audit":
            self._json(200, gather_audit_data())
        elif path == "/admin/errors":
            qs = parse_qs(urlparse(self.path).query)
            try:
                n = max(1, min(int(qs.get("n", ["20"])[0]), 50))
            except ValueError:
                n = 20
            self._json(200, {"lines": tail_error_lines(n)})
        elif path == "/admin/backup":
            data = build_backup_zip()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="backup.zip"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()
        else:
            self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if not _admin_authorized(self):
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        if path == "/admin/update":
            qs = parse_qs(urlparse(self.path).query)
            force = qs.get("force", ["0"])[0].lower() in ("1", "true", "yes")
            result = perform_self_update(force)
            self._json(200 if result["ok"] else 409, result)
            if result["ok"]:
                _schedule_exit()
        elif path == "/admin/restart":
            log.warning("[restart] requested via admin API")
            self._json(200, {"ok": True})
            _schedule_exit()
        else:
            self._json(404, {"ok": False, "error": "not_found"})


async def _start_admin_api(application):
    global _admin_httpd
    if not ADMIN_API_ENABLED:
        return
    if not ADMIN_API_TOKEN:
        log.warning("[admin-api] ADMIN_API_ENABLED is set but ADMIN_API_TOKEN is "
                    "empty — refusing to start rather than serve an unauthenticated API.")
        return
    _admin_httpd = http.server.ThreadingHTTPServer(
        (ADMIN_API_BIND, ADMIN_API_PORT), _AdminRequestHandler)
    threading.Thread(target=_admin_httpd.serve_forever, name="admin-api", daemon=True).start()
    log.info("[admin-api] listening on %s:%d", ADMIN_API_BIND, ADMIN_API_PORT)


async def _stop_admin_api(application):
    global _admin_httpd
    if _admin_httpd is not None:
        _admin_httpd.shutdown()
        _admin_httpd = None


# --- Main ---
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Keep transient network blips from spamming the log or stopping the bot."""
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        log.warning("[net] transient: %s: %s", err.__class__.__name__, err)
        _count_error("network")
        return
    import traceback
    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    log.error("[unhandled]\n%s", tb)
    _count_error("unhandled")
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
    BotCommand("editmem", "Edit a memory note by number"),
    BotCommand("sourcemem", "Show source/provenance of a memory"),
    BotCommand("reviewmem", "Review pending low-confidence memories"),
    BotCommand("recall", "Search memory for a keyword"),
    BotCommand("exportmemory", "Export full memory as text"),
    BotCommand("milestones", "View relationship milestones"),
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
    BotCommand("selfimage", "View current self-image"),
    BotCommand("reflect", "Trigger nightly reflection now"),
    BotCommand("addjoke", "Add an inside joke"),
    BotCommand("jokes", "List inside jokes"),
    BotCommand("deljoke", "Remove a joke"),
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
    BotCommand("away", "Mark yourself away (suppresses proactives)"),
    BotCommand("back", "Clear away mode"),
    BotCommand("heartbeat", "Trigger a proactive message now"),
    BotCommand("voice", "Toggle voice replies on/off"),
    BotCommand("model", "Show current model"),
    BotCommand("setmodel", "Change a model setting"),
    BotCommand("settings", "Show current settings"),
    BotCommand("usage", "Token usage stats"),
    BotCommand("chatid", "Show your chat ID"),
    BotCommand("backup", "Download a memory backup"),
    BotCommand("audit", "Bot health and error report"),
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


async def _post_init(application):
    global _MAIN_LOOP
    _MAIN_LOOP = asyncio.get_running_loop()  # lets worker threads hand saves to the loop
    await _register_commands(application)
    await _start_admin_api(application)


async def _on_shutdown(application):
    # run_polling() installs its OWN SIGINT/SIGTERM/SIGABRT handlers internally,
    # silently overriding any signal.signal() registered beforehand in main() — so a
    # plain signal handler here would never fire. post_shutdown runs as part of PTB's
    # own graceful-stop sequence regardless of what triggered it (signal, or an
    # explicit app.stop() from /update or /restart), which is the reliable hook.
    # WARNING so it lands in errors.log: a startup audit with no preceding "graceful
    # shutdown" line means the process was SIGKILLed, not signaled (Android phantom
    # process killer / OOM killer — those can't be caught at all).
    log.warning("[shutdown] graceful stop — saving state.")
    _write_state()
    await _stop_admin_api(application)


def main():
    if "--claim-test" in sys.argv:
        # On-device atomicity smoke test for the group primitives — run once before
        # trusting the pilot (GROUP_CHAT_DESIGN.md §10.5). Usage:
        #   python bot.py <instance-dir> --claim-test
        raise SystemExit(0 if _run_claim_test() else 1)
    _acquire_termux_wake_lock()
    apply_overrides()
    _log_startup_diagnostic()
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_read_timeout(40)
        .post_init(_post_init)
        .post_shutdown(_on_shutdown)
        .build()
    )

    app.add_error_handler(on_error)
    # Group choke point — runs before every other handler (group -1) and stops all
    # group-chat traffic except allowlisted commands and participating plain text.
    app.add_handler(TypeHandler(Update, group_guard), group=-1)
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
    app.add_handler(CommandHandler("meme", meme_cmd))
    app.add_handler(CommandHandler("memory", memory_cmd))
    app.add_handler(CommandHandler("exportmemory", export_memory_cmd))
    app.add_handler(CommandHandler("milestones", milestones_cmd))
    app.add_handler(CommandHandler("remember", remember_cmd))
    app.add_handler(CommandHandler("forget", forget_cmd))
    app.add_handler(CommandHandler("recall", recall_cmd))
    app.add_handler(CommandHandler("addmem", addmem_cmd))
    app.add_handler(CommandHandler("mems", mems_cmd))
    app.add_handler(CommandHandler("delmem", delmem_cmd))
    app.add_handler(CommandHandler("editmem", editmem_cmd))
    app.add_handler(CommandHandler("sourcemem", sourcemem_cmd))
    app.add_handler(CommandHandler("reviewmem", reviewmem_cmd))
    app.add_handler(CommandHandler("selfimage", selfimage_cmd))
    app.add_handler(CommandHandler("reflect", reflect_now))
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
    app.add_handler(CommandHandler("quietwin", quietwin_cmd))
    app.add_handler(CommandHandler("away", away_cmd))
    app.add_handler(CommandHandler("back", back_cmd))
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
    app.add_handler(CommandHandler("addjoke", add_joke_cmd))
    app.add_handler(CommandHandler("jokes", list_jokes_cmd))
    app.add_handler(CommandHandler("deljoke", del_joke_cmd))
    app.add_handler(CommandHandler("wardrobe", wardrobe_cmd))
    app.add_handler(CommandHandler("addoutfit", add_outfit_cmd))
    app.add_handler(CommandHandler("outfit", outfit_cmd))
    app.add_handler(CommandHandler("deloutfit", del_outfit_cmd))
    app.add_handler(CommandHandler("nudges", nudges_cmd))
    app.add_handler(CommandHandler("voice", voice_cmd))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("audit", audit_cmd))
    app.add_handler(CommandHandler("errors", errors_cmd))
    app.add_handler(CommandHandler("update", update_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))
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
    if TOMTOM_ENABLED:
        app.add_handler(CommandHandler("route", route_cmd))
        app.add_handler(CommandHandler("nearby", nearby_cmd))
        app.add_handler(CommandHandler("place", place_cmd))

    if FEEDBACK_REACTIONS:
        app.add_handler(MessageReactionHandler(reaction_feedback_handler))

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
        app.job_queue.run_daily(reflection_job, time=reflection_time)
        log.info("Nightly reflection scheduled %s.", REFLECTION_TIME)
        note_time = dtime(_NF_H, _NF_M, tzinfo=TZ) if TZ else dtime(_NF_H, _NF_M)
        app.job_queue.run_daily(note_followup_job, time=note_time)
        log.info("Note follow-ups scheduled %s.", NOTE_FOLLOWUP_TIME)
        midnight = dtime(0, 1, tzinfo=TZ) if TZ else dtime(0, 1)  # 12:01 AM
        app.job_queue.run_daily(_rotate_day_context, time=midnight)
        log.info("Day context rotation scheduled at midnight.")
        for r in reminders:
            try:
                schedule_reminder(app.job_queue, r)
            except Exception as e:
                # A single corrupt/unparseable reminder must never block startup for
                # every other one (or the bot itself) — skip it and keep going.
                log.error("[reminders] failed to re-arm reminder %s: %s", r.get("id"), e)
        if reminders:
            log.info("Re-armed %d pending reminder(s).", len(reminders))
        for j in cron_jobs:
            schedule_cron_job(app.job_queue, j)
        if cron_jobs:
            log.info("Re-armed %d scheduled task(s).", len(cron_jobs))
        # first=90 (not 300): during a restart storm the process may not live 5 minutes,
        # and the storm alert has to fire from a short-lived revival to be useful.
        app.job_queue.run_repeating(_self_audit, interval=1800, first=90)
        log.info("Self-audit: every 30 minutes.")
        app.job_queue.run_repeating(_touch_alive, interval=60, first=5)
        log.info("Alive heartbeat: every 60s (for watchdog.sh, if present).")
        if TRAFFIC_ENABLED:
            interval = TRAFFIC_POLL_MINUTES * 60
            app.job_queue.run_repeating(traffic_poll_job, interval=interval, first=60)
            log.info("Traffic polling: every %d min.", TRAFFIC_POLL_MINUTES)
        if GROUP_MODE and GROUP_ALLOWED_CHATS:
            # In-process asyncio job (no new PID — phantom-process budget untouched).
            # The ledger poll is the only way this bot hears its peer bots.
            app.job_queue.run_repeating(_group_poll_job, interval=GROUP_POLL_SECONDS, first=15)
            log.info("Group mode: polling ledger every %ds for %s.",
                     GROUP_POLL_SECONDS, sorted(GROUP_ALLOWED_CHATS))
        elif GROUP_MODE:
            log.warning("GROUP_MODE=1 but GROUP_ALLOWED_CHATS is empty — group chat "
                        "stays fully disabled (fail closed).")
    else:
        log.warning('JobQueue unavailable — scheduled features disabled. '
                    'Install with: pip install "python-telegram-bot[job-queue]"')

    log.info("%s is running (home: %s)", NAME, BASE_DIR)
    if ALLOWED_USERS:
        log.info("Access restricted to user IDs: %s", ALLOWED_USERS)
    poll_kwargs = {}
    if FEEDBACK_REACTIONS:
        poll_kwargs["allowed_updates"] = [
            "message", "edited_message", "callback_query", "message_reaction",
        ]
    app.run_polling(**poll_kwargs)


if __name__ == "__main__":
    main()
