# Hermes YNAB Financial Chief

A conversational finance agent that uses a Nous Hermes model (via NanoGPT) with
tool-calling to manage your YNAB budget.

## What it does

Ask natural-language questions about your budget and the agent fetches real data
from YNAB to answer. It can also write: create transactions, move money between
categories, and help with budget planning.

**Read operations:** budget summaries, account balances, category breakdowns,
transaction history, month-over-month trends, scheduled transactions, payee lists.

**Write operations:** create transactions, adjust category budgets (move money).

## Setup

```bash
cd hermes-ynab-chief
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with:
- `YNAB_API_KEY` — generate at https://app.ynab.com/settings/developer
- `NANOGPT_API_KEY` — your NanoGPT key
- `HERMES_MODEL` — the model ID on NanoGPT (default: `nousresearch/hermes-3-llama-3.1-70b`)

## Usage

```bash
python3 main.py
```

Then ask questions:

```
You: How much have I spent on groceries this month?
You: What categories are overspent?
You: Move $50 from Dining Out to Groceries
You: Log a $12.50 purchase at Walgreens under Health
You: Show me my spending trends for the last 3 months
```

## Files

- `main.py` — CLI entry point with interactive REPL
- `agent.py` — Hermes agent loop (NanoGPT + tool calling)
- `tools.py` — YNAB tool definitions (OpenAI function-calling format) and dispatch
- `ynab_client.py` — YNAB v1 API wrapper

## Notes

- This is a standalone project, unrelated to the Telegram bot fleet.
- YNAB amounts use milliunits internally (1000 = $1.00); the client handles conversion.
- The agent confirms before executing write operations (transactions, money moves).
- Conversation history is trimmed to `MAX_HISTORY` turns to stay within context limits.
