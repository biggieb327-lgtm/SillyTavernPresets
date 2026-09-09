"""YNAB tools for the Hermes agent. Registers via tools.registry.

Drop this file into ~/.hermes/hermes-agent/tools/ alongside ynab_client.py.
Add YNAB_API_KEY to ~/.hermes/.env.
Optionally set YNAB_DEFAULT_BUDGET to a budget ID or 'last-used'.
"""

import json
import os
from tools.registry import registry
from tools.ynab_client import YNABClient, YNABError

_client = None
_budget_id = None


def check_requirements() -> bool:
    return bool(os.environ.get("YNAB_API_KEY"))


def _get_client() -> YNABClient:
    global _client
    if _client is None:
        key = os.environ.get("YNAB_API_KEY", "")
        _client = YNABClient(key)
    return _client


def _resolve_budget_id(explicit_id: str = "") -> str:
    global _budget_id
    if explicit_id:
        return explicit_id
    if _budget_id:
        return _budget_id

    client = _get_client()
    default = os.environ.get("YNAB_DEFAULT_BUDGET", "last-used")

    if default and default != "last-used":
        _budget_id = default
        return _budget_id

    budgets = client.list_budgets()
    if not budgets:
        return ""
    budgets.sort(key=lambda b: b.get("last_modified", ""), reverse=True)
    _budget_id = budgets[0]["id"]
    return _budget_id


def _wrap(fn):
    """Standard error wrapper for tool handlers."""
    def wrapped(*a, **kw):
        try:
            return json.dumps(fn(*a, **kw), indent=2, default=str)
        except YNABError as e:
            return json.dumps({"error": f"YNAB API {e.status_code}: {e.detail}"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    return wrapped


# ── Tool handlers ──

@_wrap
def _budget_overview(args, **kw):
    client = _get_client()
    bid = _resolve_budget_id(args.get("budget_id", ""))
    if not bid:
        return {"error": "No budget found. Set YNAB_DEFAULT_BUDGET or pass budget_id."}

    accounts = client.list_accounts(bid)
    month = client.get_month(bid, "current")

    on_budget = [a for a in accounts if a["on_budget"]]
    tracking = [a for a in accounts if not a["on_budget"]]

    return {
        "budget_id": bid,
        "month": month["month"],
        "to_be_budgeted": month["to_be_budgeted"],
        "income": month["income"],
        "budgeted": month["budgeted"],
        "activity": month["activity"],
        "on_budget_accounts": [
            {"name": a["name"], "type": a["type"], "balance": a["balance"]}
            for a in on_budget
        ],
        "tracking_accounts": [
            {"name": a["name"], "type": a["type"], "balance": a["balance"]}
            for a in tracking
        ],
        "total_on_budget": sum(a["balance"] for a in on_budget),
        "total_tracking": sum(a["balance"] for a in tracking),
    }


@_wrap
def _categories(args, **kw):
    client = _get_client()
    bid = _resolve_budget_id(args.get("budget_id", ""))
    if not bid:
        return {"error": "No budget found."}
    return client.list_categories(bid)


@_wrap
def _transactions(args, **kw):
    client = _get_client()
    bid = _resolve_budget_id(args.get("budget_id", ""))
    if not bid:
        return {"error": "No budget found."}
    return client.list_transactions(
        budget_id=bid,
        since_date=args.get("since_date"),
        category_id=args.get("category_id"),
        account_id=args.get("account_id"),
        limit=args.get("limit", 30),
    )


@_wrap
def _create_transaction(args, **kw):
    client = _get_client()
    bid = _resolve_budget_id(args.get("budget_id", ""))
    if not bid:
        return {"error": "No budget found."}
    return client.create_transaction(
        budget_id=bid,
        account_id=args["account_id"],
        amount_dollars=args["amount"],
        payee_name=args["payee_name"],
        category_id=args.get("category_id"),
        memo=args.get("memo"),
        transaction_date=args.get("date"),
    )


@_wrap
def _move_money(args, **kw):
    client = _get_client()
    bid = _resolve_budget_id(args.get("budget_id", ""))
    if not bid:
        return {"error": "No budget found."}
    return client.update_category(
        budget_id=bid,
        category_id=args["category_id"],
        month=args.get("month", "current"),
        budgeted_dollars=args["new_budgeted_amount"],
    )


@_wrap
def _month_summary(args, **kw):
    client = _get_client()
    bid = _resolve_budget_id(args.get("budget_id", ""))
    if not bid:
        return {"error": "No budget found."}
    return client.get_month(bid, args.get("month", "current"))


@_wrap
def _spending_trends(args, **kw):
    client = _get_client()
    bid = _resolve_budget_id(args.get("budget_id", ""))
    if not bid:
        return {"error": "No budget found."}
    months = client.list_months(bid)
    count = args.get("months", 3)
    return months[:count]


@_wrap
def _scheduled_transactions(args, **kw):
    client = _get_client()
    bid = _resolve_budget_id(args.get("budget_id", ""))
    if not bid:
        return {"error": "No budget found."}
    return client.list_scheduled_transactions(bid)


# ── Registrations ──

TOOLSET = "ynab"

registry.register(
    name="ynab_budget_overview",
    toolset=TOOLSET,
    schema={
        "name": "ynab_budget_overview",
        "description": "Get a full budget overview: account balances, this month's income/spending/to-be-budgeted. Call this first to orient before answering budget questions.",
        "parameters": {
            "type": "object",
            "properties": {
                "budget_id": {"type": "string", "description": "Budget ID. Omit to use the default budget."},
            },
        },
    },
    handler=_budget_overview,
    check_fn=check_requirements,
)

registry.register(
    name="ynab_categories",
    toolset=TOOLSET,
    schema={
        "name": "ynab_categories",
        "description": "List all budget categories grouped by category group. Shows budgeted amount, spending activity, remaining balance, and goal progress for each category this month.",
        "parameters": {
            "type": "object",
            "properties": {
                "budget_id": {"type": "string", "description": "Budget ID. Omit to use the default budget."},
            },
        },
    },
    handler=_categories,
    check_fn=check_requirements,
)

registry.register(
    name="ynab_transactions",
    toolset=TOOLSET,
    schema={
        "name": "ynab_transactions",
        "description": "List recent transactions. Filter by date, category, or account. Returns date, amount, payee, category, memo, and cleared status.",
        "parameters": {
            "type": "object",
            "properties": {
                "budget_id": {"type": "string", "description": "Budget ID. Omit to use the default budget."},
                "since_date": {"type": "string", "description": "Only transactions on or after this date (YYYY-MM-DD)."},
                "category_id": {"type": "string", "description": "Filter to a specific category."},
                "account_id": {"type": "string", "description": "Filter to a specific account."},
                "limit": {"type": "integer", "description": "Max transactions to return (default 30)."},
            },
        },
    },
    handler=_transactions,
    check_fn=check_requirements,
)

registry.register(
    name="ynab_create_transaction",
    toolset=TOOLSET,
    schema={
        "name": "ynab_create_transaction",
        "description": "Create a new transaction in YNAB. Use negative amounts for outflows (spending) and positive for inflows (income). Example: -45.99 for a $45.99 purchase.",
        "parameters": {
            "type": "object",
            "properties": {
                "budget_id": {"type": "string", "description": "Budget ID. Omit to use the default budget."},
                "account_id": {"type": "string", "description": "Account to record the transaction in. Use ynab_budget_overview to find account IDs."},
                "amount": {"type": "number", "description": "Dollar amount. Negative = outflow (spending), positive = inflow (income)."},
                "payee_name": {"type": "string", "description": "Who the transaction is with."},
                "category_id": {"type": "string", "description": "Budget category to assign. Use ynab_categories to find IDs."},
                "memo": {"type": "string", "description": "Optional note."},
                "date": {"type": "string", "description": "Transaction date (YYYY-MM-DD). Defaults to today."},
            },
            "required": ["account_id", "amount", "payee_name"],
        },
    },
    handler=_create_transaction,
    check_fn=check_requirements,
)

registry.register(
    name="ynab_move_money",
    toolset=TOOLSET,
    schema={
        "name": "ynab_move_money",
        "description": "Move money between budget categories by setting the new budgeted amount for a category. To move $50 from A to B: first call ynab_categories to get current amounts, then decrease A and increase B by the transfer amount.",
        "parameters": {
            "type": "object",
            "properties": {
                "budget_id": {"type": "string", "description": "Budget ID. Omit to use the default budget."},
                "category_id": {"type": "string", "description": "The category to adjust. Use ynab_categories to find IDs."},
                "new_budgeted_amount": {"type": "number", "description": "The new total budgeted amount in dollars for this category this month."},
                "month": {"type": "string", "description": "Month to adjust (YYYY-MM-01). Defaults to current month."},
            },
            "required": ["category_id", "new_budgeted_amount"],
        },
    },
    handler=_move_money,
    check_fn=check_requirements,
)

registry.register(
    name="ynab_month_summary",
    toolset=TOOLSET,
    schema={
        "name": "ynab_month_summary",
        "description": "Get the detailed budget summary for a specific month: income, total budgeted, total activity, to-be-budgeted, and per-category breakdown.",
        "parameters": {
            "type": "object",
            "properties": {
                "budget_id": {"type": "string", "description": "Budget ID. Omit to use the default budget."},
                "month": {"type": "string", "description": "Month to query (YYYY-MM-01). Defaults to current month."},
            },
        },
    },
    handler=_month_summary,
    check_fn=check_requirements,
)

registry.register(
    name="ynab_spending_trends",
    toolset=TOOLSET,
    schema={
        "name": "ynab_spending_trends",
        "description": "Compare income, spending, and budgeted amounts across recent months. Good for spotting trends and answering 'how does this month compare' questions.",
        "parameters": {
            "type": "object",
            "properties": {
                "budget_id": {"type": "string", "description": "Budget ID. Omit to use the default budget."},
                "months": {"type": "integer", "description": "Number of months to show (default 3, max 12)."},
            },
        },
    },
    handler=_spending_trends,
    check_fn=check_requirements,
)

registry.register(
    name="ynab_scheduled_transactions",
    toolset=TOOLSET,
    schema={
        "name": "ynab_scheduled_transactions",
        "description": "List all scheduled and recurring transactions: upcoming bills, subscriptions, and planned transfers with their next occurrence dates, frequencies, and amounts.",
        "parameters": {
            "type": "object",
            "properties": {
                "budget_id": {"type": "string", "description": "Budget ID. Omit to use the default budget."},
            },
        },
    },
    handler=_scheduled_transactions,
    check_fn=check_requirements,
)
