import os
import re
import sys
import json
import random
import asyncio
import time
import base64
import calendar
import html as _html_module
from io import BytesIO
from datetime import datetime, date, timedelta, time as dtime
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    ApplicationBuilder,
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
NANOGPT_API_KEY = os.getenv("NANOGPT_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if not TELEGRAM_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN not found in .env at " + str(env_path))
if not NANOGPT_API_KEY:
    raise SystemExit("NANOGPT_API_KEY not found in .env at " + str(env_path))

NANOGPT_BASE_URL = "https://nano-gpt.com/api/v1"
NANOGPT_MODEL = os.getenv("NANOGPT_MODEL", "zai-org/glm-5:thinking")
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", NANOGPT_MODEL)  # can point at a faster model
VISION_MODEL = os.getenv("VISION_MODEL", NANOGPT_MODEL)    # must accept image input
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")          # used if the chat model 5xx/times out
VISION_FALLBACK_MODEL = os.getenv("VISION_FALLBACK_MODEL", "")  # vision-specific fallback
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "1.0"))
CONTEXT_LIMIT = int(os.getenv("CONTEXT_LIMIT", "40"))   # messages kept in rolling window
SUMMARY_EVERY = int(os.getenv("SUMMARY_EVERY", "20"))   # summarize every N new turns
TZ_NAME = os.getenv("BOT_TIMEZONE", "America/New_York")
WHITELIST_RAW = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS: set[int] = set()
if WHITELIST_RAW.strip():
    for _u in WHITELIST_RAW.split(","):
        _u = _u.strip()
        if _u:
            try:
                ALLOWED_USERS.add(int(_u))
            except ValueError:
                pass

try:
    import zoneinfo
    TZ = zoneinfo.ZoneInfo(TZ_NAME)
except Exception:
    TZ = None

# --- Card / persona ---
card_path = BASE_DIR / "priya.json"
CHAR_NAME = "Priya"
SYSTEM_PROMPT = ""
GREETING = ""

def load_card():
    global CHAR_NAME, SYSTEM_PROMPT, GREETING
    if not card_path.exists():
        return
    try:
        raw = json.loads(card_path.read_text(encoding="utf-8"))
        # Support both v1 (flat) and v2 (nested under data) cards
        card = raw.get("data", raw)
        CHAR_NAME = card.get("name", CHAR_NAME)
        desc    = card.get("description", "")
        persona = card.get("personality", "")
        scenario = card.get("scenario", "")
        mes_example = card.get("mes_example", "")
        system_prompt_field = card.get("system_prompt", "")
        # First message as greeting
        first_messages = card.get("first_mes", "")
        if isinstance(first_messages, list):
            GREETING = first_messages[0] if first_messages else ""
        else:
            GREETING = first_messages
        parts = []
        if system_prompt_field:
            parts.append(system_prompt_field)
        if desc:
            parts.append(f"Character: {CHAR_NAME}\n{desc}")
        if persona:
            parts.append(f"Personality: {persona}")
        if scenario:
            parts.append(f"Scenario: {scenario}")
        if mes_example:
            parts.append(f"Example exchanges:\n{mes_example}")
        # Inject preset instructions from preset.txt if present
        preset_path = BASE_DIR / "preset.txt"
        if preset_path.exists():
            preset_text = preset_path.read_text(encoding="utf-8").strip()
            if preset_text:
                parts.append(preset_text)
        SYSTEM_PROMPT = "\n\n".join(parts)
    except Exception as e:
        print(f"[card] Failed to load card: {e}")

load_card()

# --- Memory / history persistence ---
memory_path = BASE_DIR / "memory.json"

def load_memory() -> dict:
    if memory_path.exists():
        try:
            return json.loads(memory_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_memory(mem: dict):
    memory_path.write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")

MEMORY = load_memory()
# MEMORY structure:
# {
#   str(user_id): {
#     "history": [{"role":"user"|"assistant", "content":"..."},...],
#     "summary": "...rolling summary...",
#     "turn_count": int,          # total turns since last summary
#     "facts": ["fact1", ...],    # extracted long-term facts
#     "note": "user's personal note",
#     "last_active": "ISO datetime",
#   }
# }

def get_user_mem(user_id: int) -> dict:
    key = str(user_id)
    if key not in MEMORY:
        MEMORY[key] = {"history": [], "summary": "", "turn_count": 0, "facts": [], "note": "", "last_active": ""}
    return MEMORY[key]

# --- NanoGPT helpers ---

def build_messages(user_id: int, new_user_msg: str | None = None) -> list[dict]:
    """Construct the messages list to send to the model."""
    mem = get_user_mem(user_id)
    system = SYSTEM_PROMPT
    if mem.get("summary"):
        system += f"\n\n[Rolling summary of earlier conversation:\n{mem['summary']}]"
    if mem.get("facts"):
        system += "\n\n[Known facts about the user:\n" + "\n".join(f"- {f}" for f in mem["facts"]) + "]"
    if mem.get("note"):
        system += f"\n\n[User's personal note: {mem['note']}]"
    msgs: list[dict] = [{"role": "system", "content": system}]
    msgs.extend(mem["history"])
    if new_user_msg is not None:
        msgs.append({"role": "user", "content": new_user_msg})
    return msgs

def call_nanogpt(messages: list[dict], model: str | None = None, max_tokens: int | None = None) -> str:
    model = model or NANOGPT_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens or MAX_TOKENS,
        "temperature": TEMPERATURE,
    }
    headers = {"Authorization": f"Bearer {NANOGPT_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post(f"{NANOGPT_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]

def call_with_fallback(messages: list[dict], max_tokens: int | None = None) -> str:
    """Try primary model, fall back to FALLBACK_MODEL on 5xx / timeout."""
    try:
        return call_nanogpt(messages, model=NANOGPT_MODEL, max_tokens=max_tokens)
    except Exception as primary_err:
        if FALLBACK_MODEL:
            print(f"[nanogpt] Primary model error ({primary_err}), trying fallback {FALLBACK_MODEL}")
            return call_nanogpt(messages, model=FALLBACK_MODEL, max_tokens=max_tokens)
        raise

def call_vision(image_bytes: bytes, mime: str, caption: str, user_id: int) -> str:
    """Send an image + text to the vision model."""
    b64 = base64.b64encode(image_bytes).decode()
    image_content = {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64}"},
    }
    text_content = {"type": "text", "text": caption or "What do you see in this image?"}
    mem = get_user_mem(user_id)
    system = SYSTEM_PROMPT
    if mem.get("summary"):
        system += f"\n\n[Rolling summary of earlier conversation:\n{mem['summary']}]"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": [image_content, text_content]},
    ]
    try:
        return call_nanogpt(messages, model=VISION_MODEL)
    except Exception as e:
        if VISION_FALLBACK_MODEL:
            print(f"[vision] Primary vision error ({e}), trying fallback {VISION_FALLBACK_MODEL}")
            return call_nanogpt(messages, model=VISION_FALLBACK_MODEL)
        raise

# --- Summarization ---

async def maybe_summarize(user_id: int):
    mem = get_user_mem(user_id)
    mem["turn_count"] = mem.get("turn_count", 0) + 1
    if mem["turn_count"] < SUMMARY_EVERY:
        return
    # Run summarization in executor so we don't block the event loop
    await asyncio.get_event_loop().run_in_executor(None, _do_summarize, user_id)

def _do_summarize(user_id: int):
    mem = get_user_mem(user_id)
    history = mem.get("history", [])
    if len(history) < 4:
        return
    convo_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)
    prev_summary = mem.get("summary", "")
    prompt = "Summarize the following conversation in 3-5 sentences, focusing on important facts, emotional tone, and anything the user revealed about themselves. If there's a prior summary, merge it in."
    if prev_summary:
        prompt += f"\n\nPrior summary: {prev_summary}"
    prompt += f"\n\nConversation:\n{convo_text}"
    try:
        new_summary = call_nanogpt(
            [{"role": "user", "content": prompt}],
            model=SUMMARY_MODEL,
            max_tokens=512,
        )
        mem["summary"] = new_summary.strip()
        mem["turn_count"] = 0
        # Keep only the last CONTEXT_LIMIT messages after summarizing
        mem["history"] = mem["history"][-CONTEXT_LIMIT:]
        save_memory(MEMORY)
        print(f"[summary] Summarized for user {user_id}")
    except Exception as e:
        print(f"[summary] Error: {e}")

# --- Fact extraction (runs in background) ---

async def maybe_extract_facts(user_id: int, user_message: str):
    """Occasionally extract long-term facts from recent messages."""
    mem = get_user_mem(user_id)
    # Only run every 10 turns to keep costs low
    if mem.get("turn_count", 0) % 10 != 0:
        return
    await asyncio.get_event_loop().run_in_executor(None, _do_extract_facts, user_id, user_message)

def _do_extract_facts(user_id: int, recent_text: str):
    mem = get_user_mem(user_id)
    existing = mem.get("facts", [])
    prompt = (
        "Extract 0-3 important long-term facts about the user from the text below. "
        "Only include facts that would still be relevant weeks from now (name, job, relationships, important preferences, health info, etc.). "
        "Return them as a JSON array of short strings, e.g. [\"User's name is Alex\", \"Has a dog named Max\"]. "
        "If there are no new facts, return [].\n\n" + recent_text
    )
    try:
        result = call_nanogpt([{"role": "user", "content": prompt}], model=SUMMARY_MODEL, max_tokens=256)
        # Extract JSON array from result
        match = re.search(r'\[.*?\]', result, re.DOTALL)
        if match:
            new_facts = json.loads(match.group())
            if isinstance(new_facts, list):
                combined = list(dict.fromkeys(existing + new_facts))  # dedupe, preserve order
                mem["facts"] = combined[-20:]  # cap at 20 facts
                save_memory(MEMORY)
    except Exception as e:
        print(f"[facts] Error: {e}")

# --- Proactive message scheduler ---

def _get_user_tz():
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(TZ_NAME)
    except Exception:
        return None

def _now_local():
    tz = _get_user_tz()
    if tz:
        return datetime.now(tz)
    return datetime.utcnow()

PROACTIVE_USER_ID: int | None = None
try:
    _raw = os.getenv("PROACTIVE_USER_ID", "")
    if _raw.strip():
        PROACTIVE_USER_ID = int(_raw.strip())
except ValueError:
    pass

PROACTIVE_HOUR_START = int(os.getenv("PROACTIVE_HOUR_START", "9"))
PROACTIVE_HOUR_END   = int(os.getenv("PROACTIVE_HOUR_END",   "21"))

# Track the last day we sent a proactive message so we send at most once per day
_last_proactive_date: date | None = None

async def proactive_check(context):
    global _last_proactive_date
    if PROACTIVE_USER_ID is None:
        return
    now = _now_local()
    today = now.date()
    if _last_proactive_date == today:
        return
    if not (PROACTIVE_HOUR_START <= now.hour < PROACTIVE_HOUR_END):
        return
    # Random chance to fire (30% per check interval, checked every 30 min → ~1/day on avg)
    if random.random() > 0.30:
        return
    _last_proactive_date = today
    try:
        mem = get_user_mem(PROACTIVE_USER_ID)
        last_active = mem.get("last_active", "")
        ctx_note = f" (last active: {last_active})" if last_active else ""
        prompt = (
            f"It's {now.strftime('%A, %B %d')} at {now.strftime('%I:%M %p')}{ctx_note}. "
            "Send a short, natural check-in message to your user — maybe ask what they're up to, "
            "share a random thought, or reference something from your recent conversations. "
            "Keep it casual, 1-2 sentences max."
        )
        msgs = build_messages(PROACTIVE_USER_ID)
        msgs.append({"role": "user", "content": prompt})
        reply = await asyncio.get_event_loop().run_in_executor(
            None, lambda: call_with_fallback(msgs, max_tokens=120)
        )
        await context.bot.send_message(chat_id=PROACTIVE_USER_ID, text=reply.strip())
        print(f"[proactive] Sent check-in to {PROACTIVE_USER_ID}: {reply[:60]}")
    except Exception as e:
        print(f"[proactive] Error: {e}")

# --- Typing action helper ---

async def send_typing(update: Update):
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

# --- /start ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("Sorry, this bot is private.")
        return
    await update.message.reply_text(GREETING or f"Hi! I'm {CHAR_NAME}. How can I help you today?")

# --- /reset ---

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    key = str(user_id)
    MEMORY[key] = {"history": [], "summary": "", "turn_count": 0, "facts": [], "note": "", "last_active": ""}
    save_memory(MEMORY)
    await update.message.reply_text("Memory cleared. Fresh start!")

# --- /summary ---

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    mem = get_user_mem(user_id)
    summary = mem.get("summary", "")
    facts = mem.get("facts", [])
    parts = []
    if summary:
        parts.append(f"**Summary:**\n{summary}")
    if facts:
        parts.append("**Known facts:**\n" + "\n".join(f"- {f}" for f in facts))
    if parts:
        await update.message.reply_text("\n\n".join(parts), parse_mode="Markdown")
    else:
        await update.message.reply_text("No summary yet — keep chatting!")

# --- /note ---

async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    mem = get_user_mem(user_id)
    text = " ".join(context.args).strip() if context.args else ""
    if text:
        mem["note"] = text
        save_memory(MEMORY)
        await update.message.reply_text(f"Note saved: {text}")
    else:
        current = mem.get("note", "")
        await update.message.reply_text(f"Current note: {current}" if current else "No note set. Use /note <text> to set one.")

# --- /model ---

async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    await update.message.reply_text(
        f"Chat model: `{NANOGPT_MODEL}`\nSummary model: `{SUMMARY_MODEL}`\nVision model: `{VISION_MODEL}`",
        parse_mode="Markdown"
    )

# --- /retry ---

async def cmd_retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    mem = get_user_mem(user_id)
    history = mem.get("history", [])
    # Find the last user message
    last_user_idx = None
    for i in range(len(history) - 1, -1, -1):
        if history[i]["role"] == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        await update.message.reply_text("Nothing to retry.")
        return
    # Remove everything after the last user message
    last_user_msg = history[last_user_idx]["content"]
    mem["history"] = history[:last_user_idx]
    save_memory(MEMORY)
    await send_typing(update)
    try:
        msgs = build_messages(user_id, last_user_msg)
        reply = await asyncio.get_event_loop().run_in_executor(
            None, lambda: call_with_fallback(msgs)
        )
        reply = reply.strip()
        mem["history"].append({"role": "user", "content": last_user_msg})
        mem["history"].append({"role": "assistant", "content": reply})
        if len(mem["history"]) > CONTEXT_LIMIT * 2:
            mem["history"] = mem["history"][-CONTEXT_LIMIT * 2:]
        save_memory(MEMORY)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# --- /edit ---

async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit the last assistant message: /edit <new text>"""
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    mem = get_user_mem(user_id)
    history = mem.get("history", [])
    new_text = " ".join(context.args).strip() if context.args else ""
    if not new_text:
        await update.message.reply_text("Usage: /edit <replacement text for last bot reply>")
        return
    # Find and replace last assistant message
    for i in range(len(history) - 1, -1, -1):
        if history[i]["role"] == "assistant":
            history[i]["content"] = new_text
            save_memory(MEMORY)
            await update.message.reply_text("Last reply updated.")
            return
    await update.message.reply_text("No assistant message found to edit.")

# --- /undo ---

async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove the last exchange (user + assistant turn)."""
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    mem = get_user_mem(user_id)
    history = mem.get("history", [])
    removed = 0
    while history and removed < 2:
        history.pop()
        removed += 1
    mem["history"] = history
    save_memory(MEMORY)
    await update.message.reply_text(f"Removed {removed} message(s) from history.")

# --- /imagine ---
# Simple image generation stub via NanoGPT (if they support it)

async def cmd_imagine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    prompt_text = " ".join(context.args).strip() if context.args else ""
    if not prompt_text:
        await update.message.reply_text("Usage: /imagine <description>")
        return
    await send_typing(update)
    # NanoGPT image generation endpoint (may vary)
    try:
        headers = {"Authorization": f"Bearer {NANOGPT_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "dall-e-3", "prompt": prompt_text, "n": 1, "size": "1024x1024"}
        resp = requests.post(f"{NANOGPT_BASE_URL}/images/generations", json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        img_url = data["data"][0].get("url", "")
        if img_url:
            await update.message.reply_photo(img_url, caption=prompt_text[:200])
        else:
            await update.message.reply_text("No image URL in response.")
    except Exception as e:
        await update.message.reply_text(f"Image generation failed: {e}")

# --- /tts ---

async def cmd_tts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /tts <text to speak>")
        return
    await send_typing(update)
    try:
        headers = {"Authorization": f"Bearer {NANOGPT_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "tts-1", "input": text, "voice": "nova"}
        resp = requests.post(f"{NANOGPT_BASE_URL}/audio/speech", json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        audio_bytes = resp.content
        await update.message.reply_voice(voice=BytesIO(audio_bytes))
    except Exception as e:
        await update.message.reply_text(f"TTS failed: {e}")

# --- /status ---

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    mem = get_user_mem(user_id)
    history_len = len(mem.get("history", []))
    facts_len = len(mem.get("facts", []))
    turn_count = mem.get("turn_count", 0)
    last_active = mem.get("last_active", "never")
    await update.message.reply_text(
        f"Model: `{NANOGPT_MODEL}`\n"
        f"History messages: {history_len}\n"
        f"Known facts: {facts_len}\n"
        f"Turns since last summary: {turn_count}/{SUMMARY_EVERY}\n"
        f"Last active: {last_active}",
        parse_mode="Markdown"
    )

# --- /time ---

async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    now = _now_local()
    await update.message.reply_text(f"Current time ({TZ_NAME}): {now.strftime('%A, %B %d %Y  %I:%M %p')}")

# --- /remindme ---

async def cmd_remindme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /remindme <minutes> <message>
    Sets a one-off reminder that fires after <minutes> minutes.
    """
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Usage: /remindme <minutes> <reminder text>")
        return
    try:
        minutes = float(args[0])
    except ValueError:
        await update.message.reply_text("First argument must be a number of minutes.")
        return
    reminder_text = " ".join(args[1:])
    chat_id = update.effective_chat.id

    async def fire_reminder(ctx):
        await ctx.bot.send_message(chat_id=chat_id, text=f"Reminder: {reminder_text}")

    context.application.job_queue.run_once(fire_reminder, when=minutes * 60)
    await update.message.reply_text(f"Got it! I'll remind you in {minutes:.0f} minute(s): {reminder_text}")

# --- /setreminder ---

async def cmd_setreminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setreminder <HH:MM> <message>  — daily reminder at a specific local time.
    """
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Usage: /setreminder <HH:MM> <reminder text>")
        return
    time_str = args[0]
    reminder_text = " ".join(args[1:])
    try:
        hour, minute = map(int, time_str.split(":"))
        remind_time = dtime(hour=hour, minute=minute)
    except (ValueError, TypeError):
        await update.message.reply_text("Time must be in HH:MM format (24-hour).")
        return
    chat_id = update.effective_chat.id

    async def fire_daily(ctx):
        await ctx.bot.send_message(chat_id=chat_id, text=f"Daily reminder: {reminder_text}")

    tz = _get_user_tz()
    context.application.job_queue.run_daily(fire_daily, time=remind_time, timezone=tz)
    await update.message.reply_text(
        f"Daily reminder set for {time_str} ({TZ_NAME}): {reminder_text}"
    )

# --- URL / content fetching helpers ---

def _is_url(text: str) -> bool:
    return bool(re.match(r'https?://', text.strip()))

def _fetch_url_text(url: str, max_chars: int = 8000) -> str:
    """Fetch a URL and return its text content (plain or HTML-stripped)."""
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            return resp.text[:max_chars]
        # Strip HTML tags naively
        text = re.sub(r'<[^>]+>', ' ', resp.text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]
    except Exception as e:
        return f"[Could not fetch URL: {e}]"

# --- Voice message transcription ---

async def _transcribe_voice(file_bytes: bytes, mime: str = "audio/ogg") -> str:
    """Transcribe voice via NanoGPT Whisper endpoint."""
    try:
        import io
        headers = {"Authorization": f"Bearer {NANOGPT_API_KEY}"}
        files = {"file": ("voice.ogg", io.BytesIO(file_bytes), mime)}
        data = {"model": "whisper-1"}
        resp = requests.post(
            f"{NANOGPT_BASE_URL}/audio/transcriptions",
            headers=headers, files=files, data=data, timeout=60
        )
        resp.raise_for_status()
        return resp.json().get("text", "")
    except Exception as e:
        return f"[Transcription failed: {e}]"

# --- Main message handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("Sorry, this bot is private.")
        return

    await send_typing(update)

    msg = update.message
    user_text = ""

    # --- Voice messages ---
    if msg.voice:
        voice_file = await msg.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
        user_text = await _transcribe_voice(bytes(voice_bytes))
        if not user_text.strip():
            await msg.reply_text("Sorry, I couldn't transcribe that. Try again?")
            return
        # Echo the transcription so user knows what was heard
        await msg.reply_text(f"[Heard]: {user_text}")

    # --- Photo messages ---
    elif msg.photo:
        caption = msg.caption or ""
        photo = msg.photo[-1]  # largest size
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        await send_typing(update)
        try:
            reply = await asyncio.get_event_loop().run_in_executor(
                None, lambda: call_vision(bytes(photo_bytes), "image/jpeg", caption, user_id)
            )
        except Exception as e:
            await msg.reply_text(f"Vision error: {e}")
            return
        reply = reply.strip()
        mem = get_user_mem(user_id)
        mem["history"].append({"role": "user", "content": f"[Image]{': ' + caption if caption else ''}"})
        mem["history"].append({"role": "assistant", "content": reply})
        if len(mem["history"]) > CONTEXT_LIMIT * 2:
            mem["history"] = mem["history"][-CONTEXT_LIMIT * 2:]
        mem["last_active"] = datetime.utcnow().isoformat()
        save_memory(MEMORY)
        await msg.reply_text(reply)
        return

    # --- Document / file messages ---
    elif msg.document:
        doc = msg.document
        caption = msg.caption or ""
        # Only try to read text-like files under 100 KB
        if doc.file_size and doc.file_size < 100_000 and (
            doc.mime_type and ("text" in doc.mime_type or doc.mime_type in (
                "application/json", "application/xml", "application/javascript",
                "application/x-python", "application/x-sh",
            ))
        ):
            doc_file = await doc.get_file()
            doc_bytes = await doc_file.download_as_bytearray()
            try:
                doc_text = bytes(doc_bytes).decode("utf-8", errors="replace")
            except Exception:
                doc_text = "[binary file]"
            user_text = f"[File: {doc.file_name}]\n{doc_text[:6000]}"
            if caption:
                user_text = caption + "\n" + user_text
        else:
            user_text = f"[File attached: {doc.file_name} ({doc.mime_type}, {doc.file_size} bytes)]" + (f" {caption}" if caption else "")

    # --- Sticker messages ---
    elif msg.sticker:
        emoji = msg.sticker.emoji or "🙂"
        user_text = f"[Sent a sticker: {emoji}]"

    # --- Location messages ---
    elif msg.location:
        lat, lon = msg.location.latitude, msg.location.longitude
        user_text = f"[Shared location: {lat:.4f}, {lon:.4f}]"

    # --- Regular text messages ---
    else:
        user_text = msg.text or ""

    if not user_text.strip():
        return

    # Inline URL fetching: if the message is just a URL, fetch and summarize
    words = user_text.strip().split()
    if len(words) == 1 and _is_url(words[0]):
        fetched = _fetch_url_text(words[0])
        user_text = f"I shared this URL. Please read and respond to the content:\n{words[0]}\n\nContent:\n{fetched}"
    elif len(words) >= 2 and _is_url(words[-1]):
        # Command + URL (e.g. "summarize https://...")
        url = words[-1]
        fetched = _fetch_url_text(url)
        user_text = " ".join(words[:-1]) + f"\n\n[URL content from {url}:]\n{fetched}"

    mem = get_user_mem(user_id)

    try:
        msgs = build_messages(user_id, user_text)
        reply = await asyncio.get_event_loop().run_in_executor(
            None, lambda: call_with_fallback(msgs)
        )
        reply = reply.strip()
    except Exception as e:
        await msg.reply_text(f"Sorry, something went wrong: {e}")
        return

    mem["history"].append({"role": "user", "content": user_text})
    mem["history"].append({"role": "assistant", "content": reply})
    if len(mem["history"]) > CONTEXT_LIMIT * 2:
        mem["history"] = mem["history"][-CONTEXT_LIMIT * 2:]
    mem["last_active"] = datetime.utcnow().isoformat()
    save_memory(MEMORY)

    # Background tasks (don't await — fire and forget)
    asyncio.create_task(maybe_summarize(user_id))
    asyncio.create_task(maybe_extract_facts(user_id, user_text))

    # Split long replies (Telegram max 4096 chars per message)
    MAX_MSG_LEN = 4000
    if len(reply) <= MAX_MSG_LEN:
        await msg.reply_text(reply)
    else:
        chunks = [reply[i:i+MAX_MSG_LEN] for i in range(0, len(reply), MAX_MSG_LEN)]
        for chunk in chunks:
            await msg.reply_text(chunk)

# --- Error handler ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        print(f"[error] Network/timeout: {err}")
        return
    print(f"[error] Unhandled: {err}")

# --- Main ---

def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set")

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("retry", cmd_retry))
    app.add_handler(CommandHandler("edit", cmd_edit))
    app.add_handler(CommandHandler("undo", cmd_undo))
    app.add_handler(CommandHandler("imagine", cmd_imagine))
    app.add_handler(CommandHandler("tts", cmd_tts))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("time", cmd_time))
    app.add_handler(CommandHandler("remindme", cmd_remindme))
    app.add_handler(CommandHandler("setreminder", cmd_setreminder))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    # Proactive message scheduler (every 30 minutes)
    if PROACTIVE_USER_ID:
        app.job_queue.run_repeating(proactive_check, interval=1800, first=60)
        print(f"[proactive] Scheduler enabled for user {PROACTIVE_USER_ID}")

    print(f"[bot] Starting {CHAR_NAME} bot (base: {BASE_DIR})...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
