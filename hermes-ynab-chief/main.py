#!/usr/bin/env python3
"""Hermes YNAB Financial Chief — interactive CLI."""

import os
import sys
from dotenv import load_dotenv


def main():
    load_dotenv()

    ynab_key = os.getenv("YNAB_API_KEY")
    nanogpt_key = os.getenv("NANOGPT_API_KEY")
    model = os.getenv("HERMES_MODEL", "nousresearch/hermes-3-llama-3.1-70b")
    default_budget = os.getenv("YNAB_DEFAULT_BUDGET", "")
    max_history = int(os.getenv("MAX_HISTORY", "20"))

    if not ynab_key:
        print("Error: YNAB_API_KEY is not set. Add it to .env or export it.")
        sys.exit(1)
    if not nanogpt_key:
        print("Error: NANOGPT_API_KEY is not set. Add it to .env or export it.")
        sys.exit(1)

    try:
        from rich.console import Console
        from rich.markdown import Markdown
        console = Console()
        use_rich = True
    except ImportError:
        console = None
        use_rich = False

    from agent import HermesAgent

    agent = HermesAgent(
        nanogpt_api_key=nanogpt_key,
        ynab_api_key=ynab_key,
        model=model,
        max_history=max_history,
    )

    if default_budget:
        budget_name = agent.set_default_budget(default_budget)
        if budget_name:
            _print(f"Budget: {budget_name}", console, use_rich)
        else:
            _print("Could not resolve default budget, will ask the model to pick one.", console, use_rich)

    _print(f"Hermes Financial Chief ready (model: {model})", console, use_rich)
    _print("Type your question, or 'quit' to exit.\n", console, use_rich)

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break

        try:
            response = agent.chat(user_input)
            print()
            if use_rich:
                console.print(Markdown(response))
            else:
                print(response)
            print()
        except KeyboardInterrupt:
            print("\n[Interrupted]")
        except Exception as e:
            print(f"\nError: {e}\n")


def _print(text: str, console, use_rich: bool):
    if use_rich:
        console.print(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
