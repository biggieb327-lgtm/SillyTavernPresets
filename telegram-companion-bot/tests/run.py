#!/usr/bin/env python3
"""Pure-function test runner for bot.py.  Run with:  python3 tests/run.py

bot.py cannot be imported (module-level side effects: dotenv, file loads, a network session, a
running event loop). So instead of importing it, we extract individual functions from its source
via the AST and exec them into a controlled namespace with hand-built dependencies. This is the
house pattern documented in the companion-bot-validation-and-qa skill; these tests are the
throwaway verification dry-runs from the audits, made permanent so the fixed bugs can't silently
regress. Exits non-zero on any failure (so the pre-commit hook can gate on it)."""
import ast
import os
import sys

BOT_PY = os.path.join(os.path.dirname(__file__), "..", "bot.py")
_SRC = open(BOT_PY, encoding="utf-8").read()
_TREE = ast.parse(_SRC)


def extract(names, seed=None):
    """Return a namespace with the named top-level functions (and simple module-level constants,
    e.g. _REFUSAL_MARKERS) from bot.py exec'd into it, over an optional `seed` dict of
    dependencies (stdlib modules, stub globals). Interdependent functions can be requested
    together so they resolve each other's names at call time via the shared namespace."""
    ns = dict(seed or {})
    wanted = set(names)
    for node in _TREE.body:
        got = None
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            got = node.name
        elif isinstance(node, ast.Assign):
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and tgt.id in wanted:
                got = tgt.id
        if got:
            exec(compile(ast.Module(body=[node], type_ignores=[]), BOT_PY, "exec"), ns)
    missing = wanted - set(ns)
    if missing:
        raise RuntimeError(f"not found in bot.py: {sorted(missing)}")
    return ns


def main():
    import test_pure
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    test_pure.run(extract, check)

    failed = [n for n, ok in results if not ok]
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{len(results) - len(failed)}/{len(results)} passed.")
    if failed:
        print("FAILURES:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    main()
