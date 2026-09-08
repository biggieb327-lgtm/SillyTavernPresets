"""Tool definitions (OpenAI function-calling format) and dispatch for the YNAB chief."""

import json
from ynab_client import YNABClient, YNABError


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_budgets",
            "description": "List all budgets the user has in YNAB.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_summary",
            "description": "Get a high-level summary of a specific budget including account and category counts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                },
                "required": ["budget_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_accounts",
            "description": "List all open accounts in the budget with their current balances.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                },
                "required": ["budget_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "List all category groups and their categories with budgeted amounts, activity, and balances for the current month.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                },
                "required": ["budget_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_detail",
            "description": "Get detailed information about a single budget category including goal progress.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                    "category_id": {"type": "string", "description": "The category ID."},
                },
                "required": ["budget_id", "category_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_transactions",
            "description": "List recent transactions, optionally filtered by date, category, or account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                    "since_date": {"type": "string", "description": "Only return transactions on or after this date (YYYY-MM-DD)."},
                    "category_id": {"type": "string", "description": "Filter to this category."},
                    "account_id": {"type": "string", "description": "Filter to this account."},
                    "limit": {"type": "integer", "description": "Max transactions to return (default 50)."},
                },
                "required": ["budget_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_transaction",
            "description": "Create a new transaction in YNAB. Use negative amounts for outflows (spending) and positive for inflows (income).",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                    "account_id": {"type": "string", "description": "The account to record the transaction in."},
                    "amount": {"type": "number", "description": "Dollar amount. Negative for spending, positive for income. Example: -45.99 for a $45.99 purchase."},
                    "payee_name": {"type": "string", "description": "Who the transaction is with."},
                    "category_id": {"type": "string", "description": "Budget category to assign to."},
                    "memo": {"type": "string", "description": "Optional memo/note."},
                    "date": {"type": "string", "description": "Transaction date (YYYY-MM-DD). Defaults to today."},
                },
                "required": ["budget_id", "account_id", "amount", "payee_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_money",
            "description": "Move money between budget categories by adjusting the budgeted amount for the current month. To move $50 from category A to B: decrease A's budgeted by 50, increase B's budgeted by 50.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                    "category_id": {"type": "string", "description": "The category to adjust."},
                    "new_budgeted_amount": {"type": "number", "description": "The new total budgeted amount in dollars for this category this month."},
                    "month": {"type": "string", "description": "Month to adjust (YYYY-MM-01). Defaults to current month."},
                },
                "required": ["budget_id", "category_id", "new_budgeted_amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_month_summary",
            "description": "Get the budget summary for a specific month: income, total budgeted, activity, and amount to be budgeted. Also lists per-category breakdowns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                    "month": {"type": "string", "description": "Month to query (YYYY-MM-01 or 'current')."},
                },
                "required": ["budget_id", "month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_months",
            "description": "List the last 12 months of budget summaries showing income, budgeted, activity, and to-be-budgeted for each.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                },
                "required": ["budget_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_payees",
            "description": "List all payees (merchants, people, transfer targets) in the budget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                },
                "required": ["budget_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_scheduled_transactions",
            "description": "List all scheduled/recurring transactions showing their next occurrence, frequency, and amounts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_id": {"type": "string", "description": "The budget ID."},
                },
                "required": ["budget_id"],
            },
        },
    },
]


def dispatch(tool_name: str, arguments: dict, client: YNABClient) -> str:
    """Execute a tool call and return the JSON result string."""
    try:
        result = _execute(tool_name, arguments, client)
        return json.dumps(result, indent=2, default=str)
    except YNABError as e:
        return json.dumps({"error": f"YNAB API error ({e.status_code}): {e.detail}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _execute(tool_name: str, args: dict, client: YNABClient):
    match tool_name:
        case "list_budgets":
            return client.list_budgets()
        case "get_budget_summary":
            return client.get_budget(args["budget_id"])
        case "list_accounts":
            return client.list_accounts(args["budget_id"])
        case "list_categories":
            return client.list_categories(args["budget_id"])
        case "get_category_detail":
            return client.get_category(args["budget_id"], args["category_id"])
        case "list_transactions":
            return client.list_transactions(
                budget_id=args["budget_id"],
                since_date=args.get("since_date"),
                category_id=args.get("category_id"),
                account_id=args.get("account_id"),
                limit=args.get("limit", 50),
            )
        case "create_transaction":
            return client.create_transaction(
                budget_id=args["budget_id"],
                account_id=args["account_id"],
                amount_dollars=args["amount"],
                payee_name=args["payee_name"],
                category_id=args.get("category_id"),
                memo=args.get("memo"),
                transaction_date=args.get("date"),
            )
        case "move_money":
            return client.update_category(
                budget_id=args["budget_id"],
                category_id=args["category_id"],
                month=args.get("month", "current"),
                budgeted_dollars=args["new_budgeted_amount"],
            )
        case "get_month_summary":
            return client.get_month(args["budget_id"], args["month"])
        case "list_months":
            return client.list_months(args["budget_id"])
        case "list_payees":
            return client.list_payees(args["budget_id"])
        case "list_scheduled_transactions":
            return client.list_scheduled_transactions(args["budget_id"])
        case _:
            return {"error": f"Unknown tool: {tool_name}"}
