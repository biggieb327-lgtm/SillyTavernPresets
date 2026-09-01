"""skillforge CLI: `demo`, `bench`, and `evolve`."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import benchmark as bm
from .demo import demo_brain
from .llm import MockLLM, OpenAICompatLLM
from .orchestrator import evolve
from .workspace import Workspace

_DEFAULT_TASKS = Path(__file__).resolve().parents[2] / "tasks" / "demo_tasks.jsonl"


def _print_result(result, workspace: Workspace) -> None:
    print(f"\nbaseline val accuracy : {result.baseline:.3f}")
    print(f"final R_best          : {result.r_best:.3f}")
    print(f"accepted proposals    : {len(result.accepted)} / {len(result.history)}")
    for o in result.history:
        print(f"  iter {o.iteration}: {o.label:24s} score={o.score:.3f} skill={o.skill}")
    print(f"\nworkspace: {workspace.root}")
    print(f"  skills : {workspace.list_skill_names()}")
    print(f"  wiki   : {[p for p in workspace.list_files('wiki')]}")


def cmd_demo(args: argparse.Namespace) -> int:
    tasks = bm.load_tasks(args.tasks)
    root = Path(args.workspace) if args.workspace else Path(tempfile.mkdtemp(prefix="skillforge-demo-"))
    ws = Workspace(root)
    llm = MockLLM(demo_brain)
    result = evolve(llm, ws, bm.split(tasks, "train"), bm.split(tasks, "val"), iterations=args.iterations)
    _print_result(result, ws)
    # Held-out test evaluation with the final skills (paper §4).
    from .agents import InferenceAgent

    test = bm.split(tasks, "test")
    test_acc = bm.evaluate(InferenceAgent(llm, ws).solve, test).accuracy
    print(f"\nheld-out test accuracy: {test_acc:.3f}  (n={len(test)})")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    tasks = bm.load_tasks(args.tasks)
    for name in ("train", "val", "test"):
        sp = bm.split(tasks, name)
        fams = sorted({t.meta.get("family", "?") for t in sp})
        print(f"{name:5s}: {len(sp):2d} tasks  families={fams}")
    print(f"total: {len(tasks)} tasks in {args.tasks}")
    return 0


def cmd_evolve(args: argparse.Namespace) -> int:
    tasks = bm.load_tasks(args.tasks)
    ws = Workspace(args.workspace)
    llm = OpenAICompatLLM(model=args.model, base_url=args.base_url, api_key=args.api_key)
    result = evolve(
        llm, ws, bm.split(tasks, "train"), bm.split(tasks, "val"), iterations=args.iterations
    )
    _print_result(result, ws)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="skillforge", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="run the offline deterministic loop (no network)")
    d.add_argument("--tasks", default=str(_DEFAULT_TASKS))
    d.add_argument("--workspace", default=None)
    d.add_argument("--iterations", type=int, default=5)
    d.set_defaults(func=cmd_demo)

    b = sub.add_parser("bench", help="describe the skill-quality benchmark")
    b.add_argument("--tasks", default=str(_DEFAULT_TASKS))
    b.set_defaults(func=cmd_bench)

    e = sub.add_parser("evolve", help="run the loop against a real OpenAI-compatible model")
    e.add_argument("--tasks", default=str(_DEFAULT_TASKS))
    e.add_argument("--workspace", required=True)
    e.add_argument("--model", required=True)
    e.add_argument("--base-url", default="https://nano-gpt.com/api/v1")
    e.add_argument("--api-key", default=None)
    e.add_argument("--iterations", type=int, default=5)
    e.set_defaults(func=cmd_evolve)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
