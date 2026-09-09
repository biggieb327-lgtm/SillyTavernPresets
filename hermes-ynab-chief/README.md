# YNAB Financial Chief — Hermes Agent Tools

YNAB budget management tools for the Hermes agent. Registers 8 tools via
`tools.registry` that let the agent read and write your YNAB budget through
natural conversation in Matrix.

## Tools registered

| Tool | Type | What it does |
|------|------|--------------|
| `ynab_budget_overview` | read | Account balances, month income/spending/to-be-budgeted |
| `ynab_categories` | read | All categories with budgeted/activity/balance and goal progress |
| `ynab_transactions` | read | Recent transactions, filterable by date/category/account |
| `ynab_month_summary` | read | Per-category breakdown for any month |
| `ynab_spending_trends` | read | Compare income and spending across recent months |
| `ynab_scheduled_transactions` | read | Upcoming bills, subscriptions, and recurring transfers |
| `ynab_create_transaction` | write | Log a new transaction |
| `ynab_move_money` | write | Adjust a category's budget (move money between envelopes) |

All tools auto-resolve the default budget (most recently modified, or set via
`YNAB_DEFAULT_BUDGET`), so the model never needs to ask "which budget?"

## Install

1. Copy both files into the Hermes tools directory:
   ```bash
   cp ynab_client.py ~/.hermes/hermes-agent/tools/
   cp ynab_tools.py ~/.hermes/hermes-agent/tools/
   ```

2. Add your YNAB API key to `~/.hermes/.env`:
   ```
   YNAB_API_KEY=your-key-here
   ```
   Generate one at https://app.ynab.com/settings/developer

3. Optionally set a default budget:
   ```
   YNAB_DEFAULT_BUDGET=last-used
   ```
   Use `last-used` (auto-selects most recently modified) or a specific budget ID.

4. Restart the Hermes gateway:
   ```bash
   systemctl --user restart hermes-gateway
   ```

## Usage

Talk to Hermes in Matrix:

```
"How's my budget looking?"
"What categories are overspent?"
"How much have I spent on dining out this month?"
"Log a $35.50 purchase at Target under Household"
"Move $100 from Entertainment to Groceries"
"What bills are coming up this week?"
"Compare my spending to last month"
```

## Files

- `ynab_client.py` — YNAB v1 API wrapper (handles milliunit conversion, auth, error handling)
- `ynab_tools.py` — 8 tool registrations via `tools.registry.register()`, all in the `ynab` toolset

## Notes

- YNAB uses milliunits internally (1000 = $1.00); the client handles conversion both ways.
- Negative transaction amounts are outflows (spending); positive are inflows (income).
- The `check_requirements()` function gates all tools on `YNAB_API_KEY` being set — if the
  key is missing, the tools won't appear in the model's tool list.
- The YNAB client and resolved budget ID are cached at module level for the process lifetime.
