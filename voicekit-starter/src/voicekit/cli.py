"""CLI entry point for voicekit."""

from __future__ import annotations

import argparse
import sys

from voicekit import __version__
from voicekit.core import build_profile, generate, judge

REGISTER_EXAMPLES = "essay, email, dialogue, sales"


def _print_judge_summary(evaluation: dict) -> None:
    """Print a human-readable summary of a judge evaluation to the terminal."""
    scores = evaluation.get("scores")
    if isinstance(scores, dict) and scores:
        print("Scores:")
        for name, value in scores.items():
            print(f"  {name:<12} {value}")
    priorities = evaluation.get("revision_priorities")
    if isinstance(priorities, list) and priorities:
        print("Top revision priorities:")
        for i, item in enumerate(priorities[:3], start=1):
            print(f"  {i}. {item}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="voicekit",
        description="Author voice profile extraction, generation, and judging",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build-profile
    bp = subparsers.add_parser(
        "build-profile",
        help="Extract a voice profile from writing samples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            '  voicekit build-profile ./writing-samples/ --author "Jane Smith"\n'
            '  voicekit build-profile post1.md post2.md --author "Jane Smith" --out profiles/jane.json'
        ),
    )
    bp.add_argument(
        "paths",
        nargs="*",
        help="Sample files and/or directories (.txt, .md, .markdown)",
    )
    bp.add_argument("--author", required=True, help="Author name")
    bp.add_argument("--samples", nargs="+", help="One or more sample file paths")
    bp.add_argument("--samples-dir", help="Directory containing sample files")
    bp.add_argument(
        "--out",
        help="Output path for the profile JSON (default: <author>-profile.json)",
    )
    bp.add_argument("--project-name", help="Optional project name for metadata")
    bp.add_argument("--source-type", help="Optional source type label")
    bp.add_argument("--use-cases", help="Optional comma-separated use cases")
    bp.add_argument("--retries", type=int, default=2, help="Max generation attempts (default: 2)")
    bp.add_argument("--model", help="Override the LLM model")

    # generate
    gen = subparsers.add_parser(
        "generate",
        help="Generate a draft using a voice profile",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  voicekit generate --profile jane-profile.json --task-file brief.md --register email\n"
            "  voicekit generate --profile jane-profile.json --task-file brief.md \\\n"
            "      --facts-file facts.txt --register essay --out drafts/essay.md"
        ),
    )
    gen.add_argument("--profile", required=True, help="Path to voice profile JSON")
    gen.add_argument("--task-file", required=True, help="Path to task/brief file")
    gen.add_argument(
        "--facts-file",
        help="Optional path to a facts file (omit to use only facts from the task/brief)",
    )
    gen.add_argument(
        "--register",
        required=True,
        help=f"Target register (e.g. {REGISTER_EXAMPLES})",
    )
    gen.add_argument(
        "--out",
        help="Output path for the draft (default: print the draft to stdout)",
    )
    gen.add_argument("--model", help="Override the LLM model")

    # judge
    jdg = subparsers.add_parser(
        "judge",
        help="Judge a draft against a voice profile",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  voicekit judge --profile jane-profile.json --draft-file drafts/essay.md --register essay"
        ),
    )
    jdg.add_argument("--profile", required=True, help="Path to voice profile JSON")
    jdg.add_argument("--draft-file", required=True, help="Path to draft file to evaluate")
    jdg.add_argument(
        "--register",
        required=True,
        help=f"Register the draft targets (e.g. {REGISTER_EXAMPLES})",
    )
    jdg.add_argument(
        "--out",
        help="Output path for the evaluation (default: <draft>-eval.json next to the draft)",
    )
    jdg.add_argument("--model", help="Override the LLM model")

    args = parser.parse_args()

    try:
        if args.command == "build-profile":
            files = list(args.paths or [])
            if args.samples:
                files.extend(args.samples)
            if not files and not args.samples_dir:
                bp.error("provide sample files or directories (positional), --samples, or --samples-dir")
            result = build_profile(
                author=args.author,
                files=files or None,
                samples_dir=args.samples_dir,
                out=args.out,
                project_name=args.project_name,
                source_type=args.source_type,
                use_cases=args.use_cases,
                retries=args.retries,
                model=args.model,
            )
            print(f"Profile saved to {result}")

        elif args.command == "generate":
            draft_text, out_path = generate(
                profile_path=args.profile,
                task_file=args.task_file,
                facts_file=args.facts_file,
                register=args.register,
                out=args.out,
                model=args.model,
            )
            if out_path:
                print(f"Draft saved to {out_path}")
            else:
                print(draft_text)

        elif args.command == "judge":
            evaluation, out_path = judge(
                profile_path=args.profile,
                draft_file=args.draft_file,
                register=args.register,
                out=args.out,
                model=args.model,
            )
            if evaluation:
                _print_judge_summary(evaluation)
            print(f"Evaluation saved to {out_path}")

    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
