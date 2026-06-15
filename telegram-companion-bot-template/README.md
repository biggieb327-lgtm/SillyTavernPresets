# Telegram Companion Bot

A self-hosted AI companion that lives in Telegram — built on a SillyTavern v2
character card, with persistent memory, moods, proactive messages, selfies, web
search, and link reading. Designed to run on an Android phone via Termux (or any
Linux machine), entirely under your own control.

## Features

- **Character-driven**: powered by a standard SillyTavern v2 character card
  (`priya.json` is included as a working example)
- **Two-tier memory**: a verbatim recent-conversation window, a rolling "recent
  memory" summary, and durable long-term facts that persist indefinitely
- **Proactive texting**: occasional unprompted messages within configurable
  quiet hours, plus nightly reflection that sets a "next conversation goal"
- **Mood**: drifts based on how often you talk, coloring tone and selfies
- **Selfies**: img2img portraits via Gemini or NanoGPT, mood- and weather-aware
- **Web search & link reading**: including Reddit posts (via Reddit's OAuth API)
- **Live config**: change AI models and feature toggles from Telegram itself with
  `/setmodel` and `/settings` — no restart needed
- **Reminders & recurring tasks**: `/remindme`, `/cron`, and an optional weekly
  payments-reminder digest
- **Editable texting style**: `preset.txt` controls phrasing/punctuation rules
  without touching the code

## Getting started

New to this? Follow [`SETUP_GUIDE.md`](./SETUP_GUIDE.md) — a beginner-friendly,
step-by-step walkthrough (no programming experience needed, ~30-45 minutes).

Already set up? See [`OPS_MANUAL.md`](./OPS_MANUAL.md) for the full command
reference, configuration knobs, and troubleshooting.

## What's included

| File | Purpose |
|---|---|
| `bot.py` | The bot itself — shared code, configured entirely via `.env` and per-character files |
| `priya.json` | Example SillyTavern v2 character card — copy and adapt, or write your own |
| `preset.txt` | Editable texting-style instructions |
| `.env.example` | All configuration options, with comments |
| `requirements.txt` | Python dependencies |
| `run.sh` / `run-bot.sh` | Auto-restarting launcher scripts for tmux |
| `SETUP_GUIDE.md` | Step-by-step setup for beginners |
| `OPS_MANUAL.md` | Command reference, configuration, and troubleshooting |

## Bring your own character

`priya.json` demonstrates the character card structure this bot expects: OCEAN
personality trait blocks, a voice pack with concrete speech rules, system-prompt
dialogue rules, and a lorebook (`character_book`) of background entries. You can
build your own card from scratch in SillyTavern's character creator and export it
as v2 JSON, or start from `priya.json` and adapt it.

## Requirements

- A Telegram bot token (free, via @BotFather)
- A [NanoGPT](https://nano-gpt.com) API key (subscription recommended)
- Optional: a Google Gemini API key for higher-quality selfies
- Optional: Reddit API credentials for reading Reddit links
