#!/usr/bin/env python3
"""Telegram <-> NanoGPT (GLM 5.1 Thinking) bot.

Single file, long-polling, SQLite-backed persistence. Built for Termux on
Android. Secrets come from the environment (BOT_TOKEN, NANOGPT_API_KEY);
model calls go through NanoGPT's OpenAI-compatible endpoint via httpx.
"""

import os
import re
import sys
import logging
import sqlite3
import threading

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

NANOGPT_URL = "https://nano-gpt.com/api/v1/chat/completions"

# IMPORTANT: confirm the exact slug for GLM 5.1 Thinking on your account.
# List what your key can see:
#   curl https://nano-gpt.com/api/v1/models \
#     -H "Authorization: Bearer $NANOGPT_API_KEY" | grep -i glm
# Then set MODEL to the id that comes back (it may or may not need ":thinking").
MODEL = "zai-org/glm-5:thinking"

MAX_TOKENS = 8000             # thinking eats budget; raise if replies get cut off
HTTP_TIMEOUT = 120.0          # seconds; thinking models are slow
MAX_TURNS = 20                # turns kept per user (a turn = user + assistant)
DB_PATH = os.path.join(os.path.expanduser("~"), "glm_bot.db")

SYSTEM_PROMPT = (
    "You are a helpful, friendly assistant chatting with the user over "
    "Telegram. Keep replies clear and reasonably concise for a phone screen."
)

# Background proactive check. Off by default so the bot stays silent unless you
# flip this on; even when on it asks the model first and defaults to silence.
PROACTIVE_ENABLED = False
PROACTIVE_INTERVAL = 6 * 60 * 60  # seconds between checks when enabled

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("glm_bot")


def require_env(name: str) -> str:
    """Read a required secret from the environment, stripped. Exit if missing."""
    value = os.environ.get(name)
    if not value or not value.strip():
        sys.exit(f"FATAL: environment variable {name} is not set. "
                 f"Set it in ~/.bashrc and restart your shell.")
    return value.strip()


# --------------------------------------------------------------------------- #
# Persistence (SQLite at ~/glm_bot.db)
# --------------------------------------------------------------------------- #

_db_lock = threading.Lock()
_db = sqlite3.connect(DB_PATH, check_same_thread=False)
_db.execute("PRAGMA journal_mode=WAL;")
_db.executescript(
    """
    CREATE TABLE IF NOT EXISTS chats (
        chat_id    INTEGER PRIMARY KEY,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS messages (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        role    TEXT NOT NULL,
        content TEXT NOT NULL,
        ts      TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
    """
)
_db.commit()


def register_chat(chat_id: int) -> None:
    with _db_lock:
        _db.execute("INSERT OR IGNORE INTO chats(chat_id) VALUES (?)", (chat_id,))
        _db.commit()


def known_chats() -> list[int]:
    with _db_lock:
        rows = _db.execute("SELECT chat_id FROM chats").fetchall()
    return [r[0] for r in rows]


def add_message(chat_id: int, role: str, content: str) -> None:
    """Append a message and trim the user's history to the last MAX_TURNS turns."""
    with _db_lock:
        _db.execute(
            "INSERT INTO messages(chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        _db.execute(
            """
            DELETE FROM messages
            WHERE chat_id = ?
              AND id NOT IN (
                  SELECT id FROM messages
                  WHERE chat_id = ?
                  ORDER BY id DESC
                  LIMIT ?
              )
            """,
            (chat_id, chat_id, MAX_TURNS * 2),
        )
        _db.commit()


def get_history(chat_id: int) -> list[dict]:
    with _db_lock:
        rows = _db.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        ).fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows]


def forget_chat(chat_id: int) -> None:
    with _db_lock:
        _db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        _db.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        _db.commit()


# --------------------------------------------------------------------------- #
# NanoGPT call
# --------------------------------------------------------------------------- #

_THINK_RE = re.compile(r"(?s)^.*?</think>")


def strip_thinking(text: str) -> str:
    """Drop everything up to and including a closing </think> tag."""
    if "</think>" in text:
        text = _THINK_RE.sub("", text, count=1)
    text = text.replace("<think>", "")
    return text.strip()


async def call_nanogpt(api_key: str, messages: list[dict]) -> str:
    """POST to NanoGPT and return the cleaned assistant text."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TIMEOUT)) as client:
        resp = await client.post(NANOGPT_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    choice = data["choices"][0]["message"]
    content = choice.get("content") or ""
    # Some thinking models split reasoning into reasoning_content and leave the
    # final answer in content; if content is empty fall back to reasoning_content.
    if not content.strip():
        content = choice.get("reasoning_content") or ""
    return strip_thinking(content)


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    register_chat(chat_id)
    await update.message.reply_text(
        "Hi! I'm wired up to GLM 5.1. Just send me a message and I'll reply.\n"
        "Use /stop to make me forget our conversation."
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    forget_chat(chat_id)
    await update.message.reply_text("Done — I've deleted your stored data.")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_text = update.message.text
    register_chat(chat_id)
    add_message(chat_id, "user", user_text)

    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + get_history(chat_id)
    try:
        reply = await call_nanogpt(context.bot_data["api_key"], messages)
    except httpx.HTTPStatusError as exc:
        log.error("NanoGPT HTTP %s: %s", exc.response.status_code, exc.response.text[:500])
        await update.message.reply_text(
            f"Backend error (HTTP {exc.response.status_code}). Try again in a moment."
        )
        return
    except Exception as exc:  # noqa: BLE001 - surface anything else to the user
        log.exception("NanoGPT call failed")
        await update.message.reply_text(f"Something went wrong: {exc}")
        return

    if not reply:
        reply = "(the model returned an empty answer)"

    add_message(chat_id, "assistant", reply)

    # Telegram caps messages at 4096 chars; chunk long replies.
    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i:i + 4000])


async def proactive_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask the model whether to reach out; default to staying silent."""
    api_key = context.bot_data["api_key"]
    for chat_id in known_chats():
        history = get_history(chat_id)
        if not history:
            continue
        probe = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {
                "role": "user",
                "content": (
                    "[system] Based on our conversation, is there a genuinely "
                    "useful, welcome follow-up you should send right now "
                    "unprompted? If not, reply with exactly SILENT. Default to "
                    "SILENT unless there is a clear reason. If you do reach out, "
                    "reply only with the message to send."
                ),
            },
        ]
        try:
            reply = await call_nanogpt(api_key, probe)
        except Exception:  # noqa: BLE001
            log.exception("proactive check failed for %s", chat_id)
            continue
        if reply and reply.strip().upper() != "SILENT":
            await context.bot.send_message(chat_id, reply)
            add_message(chat_id, "assistant", reply)


async def post_init(application) -> None:
    log.info("Bot started. Model=%s  Known chats=%d", MODEL, len(known_chats()))


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    bot_token = require_env("BOT_TOKEN")
    api_key = require_env("NANOGPT_API_KEY")

    application = (
        ApplicationBuilder()
        .token(bot_token)
        # Mobile handshakes to Telegram are slow; be generous so startup and
        # long-polling don't raise telegram.error.TimedOut.
        .connect_timeout(30)
        .read_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
        .post_init(post_init)
        .build()
    )
    application.bot_data["api_key"] = api_key

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_message)
    )

    if PROACTIVE_ENABLED and application.job_queue is not None:
        application.job_queue.run_repeating(
            proactive_check, interval=PROACTIVE_INTERVAL, first=PROACTIVE_INTERVAL
        )
        log.info("Proactive check enabled (every %ds).", PROACTIVE_INTERVAL)

    log.info("Starting long polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
