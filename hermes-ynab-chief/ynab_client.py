"""YNAB API client. Wraps the v1 REST API with typed helpers."""

import requests
from datetime import date, datetime
from typing import Optional


BASE_URL = "https://api.ynab.com/v1"


class YNABError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"YNAB API {status_code}: {detail}")


def _millis_to_dollars(milliunits: int) -> float:
    return milliunits / 1000.0


def _dollars_to_millis(dollars: float) -> int:
    return int(round(dollars * 1000))


class YNABClient:
    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        resp = self.session.get(f"{BASE_URL}{path}", params=params)
        if resp.status_code != 200:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            detail = body.get("error", {}).get("detail", resp.text[:200])
            raise YNABError(resp.status_code, detail)
        return resp.json()["data"]

    def _post(self, path: str, payload: dict) -> dict:
        resp = self.session.post(f"{BASE_URL}{path}", json=payload)
        if resp.status_code not in (200, 201):
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            detail = body.get("error", {}).get("detail", resp.text[:200])
            raise YNABError(resp.status_code, detail)
        return resp.json()["data"]

    def _patch(self, path: str, payload: dict) -> dict:
        resp = self.session.patch(f"{BASE_URL}{path}", json=payload)
        if resp.status_code != 200:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            detail = body.get("error", {}).get("detail", resp.text[:200])
            raise YNABError(resp.status_code, detail)
        return resp.json()["data"]

    # ── Budgets ──

    def list_budgets(self) -> list[dict]:
        data = self._get("/budgets")
        budgets = []
        for b in data["budgets"]:
            budgets.append({
                "id": b["id"],
                "name": b["name"],
                "last_modified": b.get("last_modified_on", ""),
                "currency": b.get("currency_format", {}).get("iso_code", "USD"),
            })
        return budgets

    def get_budget(self, budget_id: str) -> dict:
        data = self._get(f"/budgets/{budget_id}")
        b = data["budget"]
        return {
            "id": b["id"],
            "name": b["name"],
            "last_modified": b.get("last_modified_on", ""),
            "currency": b.get("currency_format", {}).get("iso_code", "USD"),
            "accounts_count": len(b.get("accounts", [])),
            "categories_count": sum(
                len(g.get("categories", []))
                for g in b.get("category_groups", [])
            ),
        }

    # ── Accounts ──

    def list_accounts(self, budget_id: str) -> list[dict]:
        data = self._get(f"/budgets/{budget_id}/accounts")
        accounts = []
        for a in data["accounts"]:
            if a.get("deleted") or a.get("closed"):
                continue
            accounts.append({
                "id": a["id"],
                "name": a["name"],
                "type": a["type"],
                "on_budget": a.get("on_budget", True),
                "balance": _millis_to_dollars(a.get("balance", 0)),
                "cleared_balance": _millis_to_dollars(a.get("cleared_balance", 0)),
                "uncleared_balance": _millis_to_dollars(a.get("uncleared_balance", 0)),
            })
        return accounts

    # ── Categories ──

    def list_categories(self, budget_id: str) -> list[dict]:
        data = self._get(f"/budgets/{budget_id}/categories")
        groups = []
        for g in data["category_groups"]:
            if g.get("deleted") or g.get("hidden"):
                continue
            cats = []
            for c in g.get("categories", []):
                if c.get("deleted") or c.get("hidden"):
                    continue
                cats.append({
                    "id": c["id"],
                    "name": c["name"],
                    "budgeted": _millis_to_dollars(c.get("budgeted", 0)),
                    "activity": _millis_to_dollars(c.get("activity", 0)),
                    "balance": _millis_to_dollars(c.get("balance", 0)),
                    "goal_type": c.get("goal_type"),
                    "goal_target": _millis_to_dollars(c["goal_target"]) if c.get("goal_target") else None,
                    "goal_percentage_complete": c.get("goal_percentage_complete"),
                })
            if cats:
                groups.append({
                    "group_name": g["name"],
                    "group_id": g["id"],
                    "categories": cats,
                })
        return groups

    def get_category(self, budget_id: str, category_id: str) -> dict:
        data = self._get(f"/budgets/{budget_id}/categories/{category_id}")
        c = data["category"]
        return {
            "id": c["id"],
            "name": c["name"],
            "budgeted": _millis_to_dollars(c.get("budgeted", 0)),
            "activity": _millis_to_dollars(c.get("activity", 0)),
            "balance": _millis_to_dollars(c.get("balance", 0)),
            "goal_type": c.get("goal_type"),
            "goal_target": _millis_to_dollars(c["goal_target"]) if c.get("goal_target") else None,
            "goal_percentage_complete": c.get("goal_percentage_complete"),
        }

    def update_category(self, budget_id: str, category_id: str, month: str,
                        budgeted_dollars: float) -> dict:
        """Move money to/from a category by setting its budgeted amount for a month.
        month format: 'YYYY-MM-01' or 'current'"""
        if month == "current":
            month = date.today().strftime("%Y-%m-01")
        data = self._patch(
            f"/budgets/{budget_id}/months/{month}/categories/{category_id}",
            {"category": {"budgeted": _dollars_to_millis(budgeted_dollars)}}
        )
        c = data["category"]
        return {
            "id": c["id"],
            "name": c["name"],
            "budgeted": _millis_to_dollars(c.get("budgeted", 0)),
            "balance": _millis_to_dollars(c.get("balance", 0)),
        }

    # ── Transactions ──

    def list_transactions(self, budget_id: str, since_date: Optional[str] = None,
                          category_id: Optional[str] = None,
                          account_id: Optional[str] = None,
                          limit: int = 50) -> list[dict]:
        params = {}
        if since_date:
            params["since_date"] = since_date

        if account_id:
            path = f"/budgets/{budget_id}/accounts/{account_id}/transactions"
        elif category_id:
            path = f"/budgets/{budget_id}/categories/{category_id}/transactions"
        else:
            path = f"/budgets/{budget_id}/transactions"

        data = self._get(path, params)
        txns = []
        for t in data["transactions"][-limit:]:
            txns.append({
                "id": t["id"],
                "date": t["date"],
                "amount": _millis_to_dollars(t.get("amount", 0)),
                "payee_name": t.get("payee_name", ""),
                "category_name": t.get("category_name", ""),
                "memo": t.get("memo", ""),
                "cleared": t.get("cleared", ""),
                "approved": t.get("approved", False),
                "flag_color": t.get("flag_color"),
                "account_name": t.get("account_name", ""),
            })
        return txns

    def create_transaction(self, budget_id: str, account_id: str,
                           amount_dollars: float, payee_name: str,
                           category_id: Optional[str] = None,
                           memo: Optional[str] = None,
                           transaction_date: Optional[str] = None,
                           cleared: str = "uncleared",
                           approved: bool = False) -> dict:
        txn = {
            "account_id": account_id,
            "date": transaction_date or date.today().isoformat(),
            "amount": _dollars_to_millis(amount_dollars),
            "payee_name": payee_name,
            "cleared": cleared,
            "approved": approved,
        }
        if category_id:
            txn["category_id"] = category_id
        if memo:
            txn["memo"] = memo

        data = self._post(
            f"/budgets/{budget_id}/transactions",
            {"transaction": txn}
        )
        t = data["transaction"]
        return {
            "id": t["id"],
            "date": t["date"],
            "amount": _millis_to_dollars(t.get("amount", 0)),
            "payee_name": t.get("payee_name", ""),
            "category_name": t.get("category_name", ""),
            "memo": t.get("memo", ""),
            "approved": t.get("approved", False),
        }

    # ── Payees ──

    def list_payees(self, budget_id: str) -> list[dict]:
        data = self._get(f"/budgets/{budget_id}/payees")
        payees = []
        for p in data["payees"]:
            if p.get("deleted"):
                continue
            payees.append({
                "id": p["id"],
                "name": p["name"],
                "transfer_account_id": p.get("transfer_account_id"),
            })
        return payees

    # ── Month summaries ──

    def list_months(self, budget_id: str) -> list[dict]:
        data = self._get(f"/budgets/{budget_id}/months")
        months = []
        for m in data["months"][:12]:
            months.append({
                "month": m["month"],
                "income": _millis_to_dollars(m.get("income", 0)),
                "budgeted": _millis_to_dollars(m.get("budgeted", 0)),
                "activity": _millis_to_dollars(m.get("activity", 0)),
                "to_be_budgeted": _millis_to_dollars(m.get("to_be_budgeted", 0)),
            })
        return months

    def get_month(self, budget_id: str, month: str) -> dict:
        """month format: 'YYYY-MM-01' or 'current'"""
        if month == "current":
            month = date.today().strftime("%Y-%m-01")
        data = self._get(f"/budgets/{budget_id}/months/{month}")
        m = data["month"]
        result = {
            "month": m["month"],
            "income": _millis_to_dollars(m.get("income", 0)),
            "budgeted": _millis_to_dollars(m.get("budgeted", 0)),
            "activity": _millis_to_dollars(m.get("activity", 0)),
            "to_be_budgeted": _millis_to_dollars(m.get("to_be_budgeted", 0)),
            "categories": [],
        }
        for c in m.get("categories", []):
            if c.get("deleted") or c.get("hidden"):
                continue
            result["categories"].append({
                "name": c["name"],
                "budgeted": _millis_to_dollars(c.get("budgeted", 0)),
                "activity": _millis_to_dollars(c.get("activity", 0)),
                "balance": _millis_to_dollars(c.get("balance", 0)),
            })
        return result

    # ── Scheduled transactions ──

    def list_scheduled_transactions(self, budget_id: str) -> list[dict]:
        data = self._get(f"/budgets/{budget_id}/scheduled_transactions")
        txns = []
        for t in data["scheduled_transactions"]:
            if t.get("deleted"):
                continue
            txns.append({
                "id": t["id"],
                "date_first": t.get("date_first", ""),
                "date_next": t.get("date_next", ""),
                "frequency": t.get("frequency", ""),
                "amount": _millis_to_dollars(t.get("amount", 0)),
                "payee_name": t.get("payee_name", ""),
                "category_name": t.get("category_name", ""),
                "memo": t.get("memo", ""),
                "account_name": t.get("account_name", ""),
            })
        return txns
