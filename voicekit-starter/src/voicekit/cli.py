"""CLI entry point for voicekit."""

from __future__ import annotations

import argparse
import sys

from voicekit.core import build_profile, generate, judge


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="voicekit",
        description="Author voice profile extraction, generation, and judging",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build-profile
    bp = subparsers.add_parser("build-profile", help="Extract a voice profile from writing samples")
    bp.add_argument("--author", required=True, help="Author name")
    bp.add_argument("--samples", nargs="+", help="One or more sample file paths")
    bp.add_argument("--samples-dir", help="Directory containing sample files")
    bp.add_argument("--out", required=True, help="Output path for the profile JSON")
    bp.add_argument("--project-name", help="Optional project name for metadata")
    bp.add_argument("--source-type", help="Optional source type label")
    bp.add_argument("--use-cases", help="Optional comma-separated use cases")
    bp.add_argument("--retries", type=int, default=2, help="Max generation attempts (default: 2)")
    bp.add_argument("--model", help="Override the LLM model")

    # generate
    gen = subparsers.add_parser("generate", help="Generate a draft using a voice profile")
    gen.add_argument("--profile", required=True, help="Path to voice profile JSON")
    gen.add_argument("--task-file", required=True, help="Path to task/brief file")
    gen.add_argument("--facts-file", required=True, help="Path to facts file")
    gen.add_argument("--register", required=True, help="Target register (essay, email, dialogue, sales)")
    gen.add_argument("--out", required=True, help="Output path for the draft")
    gen.add_argument("--model", help="Override the LLM model")

    # judge
    jdg = subparsers.add_parser("judge", help="Judge a draft against a voice profile")
    jdg.add_argument("--profile", required=True, help="Path to voice profile JSON")
    jdg.add_argument("--draft-file", required=True, help="Path to draft file to evaluate")
    jdg.add_argument("--register", required=True, help="Register the draft targets")
    jdg.add_argument("--out", required=True, help="Output path for the evaluation")
    jdg.add_argument("--model", help="Override the LLM model")

    args = parser.parse_args()

    try:
        if args.command == "build-profile":
            result = build_profile(
                author=args.author,
                files=args.samples,
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
            result = generate(
                profile_path=args.profile,
                task_file=args.task_file,
                facts_file=args.facts_file,
                register=args.register,
                out=args.out,
                model=args.model,
            )
            print(f"Draft saved to {result}")

        elif args.command == "judge":
            result = judge(
                profile_path=args.profile,
                draft_file=args.draft_file,
                register=args.register,
                out=args.out,
                model=args.model,
            )
            print(f"Evaluation saved to {result}")

    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
