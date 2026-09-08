"""Hermes agent loop: takes user input, calls the model via NanoGPT, executes
YNAB tool calls, feeds results back, repeats until the model gives a final answer."""

import json
from openai import OpenAI
from tools import TOOL_DEFINITIONS, dispatch
from ynab_client import YNABClient


SYSTEM_PROMPT = """\
You are the Chief of Financial Operations, a sharp and efficient personal finance agent \
with direct access to the user's YNAB (You Need A Budget) data. You help them understand \
their budget, track spending, manage categories, create transactions, and make informed \
financial decisions.

Your personality:
- Direct and clear. No fluff, no hedging. Say what the numbers say.
- Proactive: if you spot an overspent category or a goal falling behind, mention it.
- When presenting financial data, use clean formatting with dollar amounts.
- For spending analysis, always contextualize: compare to budget, to last month, to goals.
- When the user asks to move money or create transactions, confirm the details before executing.

How you work:
- You have tools to read and write the user's YNAB budget data.
- Start by identifying which budget to work with if not already established.
- Use the tools to fetch real data before answering questions. Do not guess or hallucinate numbers.
- For multi-step operations (like moving money between categories), fetch current state first, \
then make the changes.
- Negative transaction amounts are outflows (spending); positive are inflows (income).

Financial context:
- YNAB uses an envelope budgeting method: every dollar gets a job.
- "Activity" means actual spending/income in a category for the month.
- "Balance" is what remains available in a category (budgeted + activity).
- "To Be Budgeted" is unassigned money waiting for a job.
- Categories can be overspent (negative balance) which means borrowing from future months.\
"""


class HermesAgent:
    def __init__(self, nanogpt_api_key: str, ynab_api_key: str,
                 model: str = "nousresearch/hermes-3-llama-3.1-70b",
                 max_history: int = 20):
        self.openai = OpenAI(
            api_key=nanogpt_api_key,
            base_url="https://nano-gpt.com/api/v1",
        )
        self.ynab = YNABClient(ynab_api_key)
        self.model = model
        self.max_history = max_history
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.budget_id: str | None = None

    def set_default_budget(self, budget_ref: str):
        """Pre-select a budget by ID or 'last-used'."""
        if budget_ref == "last-used":
            budgets = self.ynab.list_budgets()
            if budgets:
                budgets.sort(key=lambda b: b.get("last_modified", ""), reverse=True)
                self.budget_id = budgets[0]["id"]
                return budgets[0]["name"]
        elif budget_ref:
            self.budget_id = budget_ref
            try:
                info = self.ynab.get_budget(budget_ref)
                return info["name"]
            except Exception:
                pass
        return None

    def chat(self, user_message: str) -> str:
        """Send a user message through the agent loop and return the final text response."""
        self.messages.append({"role": "user", "content": user_message})
        self._trim_history()

        tool_rounds = 0
        max_tool_rounds = 10

        while tool_rounds < max_tool_rounds:
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )

            choice = response.choices[0]
            message = choice.message

            if not message.tool_calls:
                text = message.content or ""
                self.messages.append({"role": "assistant", "content": text})
                return text

            self.messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            for tc in message.tool_calls:
                args = json.loads(tc.function.arguments)

                if "budget_id" in args and args["budget_id"] == "default" and self.budget_id:
                    args["budget_id"] = self.budget_id

                result = dispatch(tc.function.name, args, self.ynab)

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            tool_rounds += 1

        return "[Agent hit the tool-call limit. Try a simpler question or break it into steps.]"

    def _trim_history(self):
        """Keep the system prompt + last N user/assistant turns."""
        if len(self.messages) <= 1 + self.max_history * 2:
            return
        system = self.messages[0]
        tail = self.messages[-(self.max_history * 2):]
        self.messages = [system] + tail
