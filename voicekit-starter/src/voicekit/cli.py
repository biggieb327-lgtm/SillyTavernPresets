"""CLI entry point for voicekit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from voicekit import __version__
from voicekit.core import build_profile, generate, judge
from voicekit.profile_mgmt import list_profiles, merge_profiles, validate_profile_cmd
from voicekit.batch import batch_build_profiles, batch_generate, batch_judge
from voicekit.analysis import compare_profiles, track_evolution
from voicekit.multi_author import detect_authors, attribute_text, build_collaborative_profile

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

    # list-profiles
    lp = subparsers.add_parser(
        "list-profiles",
        help="List and validate all profiles in a directory",
    )
    lp.add_argument("directory", help="Directory containing profile JSON files")

    # merge-profiles
    mp = subparsers.add_parser(
        "merge-profiles",
        help="Merge multiple profiles into one",
    )
    mp.add_argument("profiles", nargs="+", help="Paths to profiles to merge")
    mp.add_argument("--author", required=True, help="Author name for merged profile")
    mp.add_argument("--out", help="Output path for merged profile")

    # validate-profile
    vp = subparsers.add_parser(
        "validate-profile",
        help="Validate a voice profile against the schema",
    )
    vp.add_argument("profile", help="Path to profile JSON file")

    # batch-build
    bb = subparsers.add_parser(
        "batch-build",
        help="Build profiles for multiple authors in parallel",
    )
    bb.add_argument("config", help="Path to batch config JSON file")
    bb.add_argument("--workers", type=int, default=3, help="Max parallel workers (default: 3)")
    bb.add_argument("--no-resume", action="store_true", help="Don't resume from progress file")

    # batch-generate
    bg = subparsers.add_parser(
        "batch-generate",
        help="Generate multiple drafts in parallel",
    )
    bg.add_argument("config", help="Path to batch config JSON file")
    bg.add_argument("--workers", type=int, default=3, help="Max parallel workers (default: 3)")

    # batch-judge
    bj = subparsers.add_parser(
        "batch-judge",
        help="Judge multiple drafts in parallel",
    )
    bj.add_argument("config", help="Path to batch config JSON file")
    bj.add_argument("--workers", type=int, default=3, help="Max parallel workers (default: 3)")

    # compare-profiles
    cp = subparsers.add_parser(
        "compare-profiles",
        help="Compare two voice profiles and show similarity",
    )
    cp.add_argument("profile_a", help="Path to first profile JSON")
    cp.add_argument("profile_b", help="Path to second profile JSON")

    # track-evolution
    te = subparsers.add_parser(
        "track-evolution",
        help="Track voice evolution across multiple profiles",
    )
    te.add_argument("profiles", nargs="+", help="Paths to profile JSON files (chronological order)")
    te.add_argument("--author", required=True, help="Author name")
    te.add_argument("--out", help="Output path for evolution report")

    # detect-authors
    da = subparsers.add_parser(
        "detect-authors",
        help="Detect distinct authors in a corpus directory",
    )
    da.add_argument("corpus_dir", help="Directory containing writing samples")

    # attribute-text
    at = subparsers.add_parser(
        "attribute-text",
        help="Attribute text to a known author",
    )
    at.add_argument("text_file", help="Path to text file to attribute")
    at.add_argument("profiles", nargs="+", help="Paths to author profile JSON files")

    # collaborative-profile
    cp = subparsers.add_parser(
        "collaborative-profile",
        help="Build a collaborative voice profile from multiple authors",
    )
    cp.add_argument("profiles", nargs="+", help="Paths to author profile JSON files")
    cp.add_argument("--name", required=True, help="Name for the collaborative profile")
    cp.add_argument("--out", help="Output path for the collaborative profile")

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

        elif args.command == "list-profiles":
            profiles = list_profiles(args.directory)
            if not profiles:
                print("No profiles found.")
            else:
                for p in profiles:
                    status = "✓" if p["valid"] else "✗"
                    print(f"  {status} {p['author']} ({p['version']}) - {p['path']}")

        elif args.command == "merge-profiles":
            out_path = merge_profiles(args.profiles, args.author, args.out)
            print(f"Merged profile saved to {out_path}")

        elif args.command == "validate-profile":
            report = validate_profile_cmd(args.profile)
            if report["valid"]:
                print(f"✓ Valid profile: {report['stats'].get('author', 'unknown')}")
                print(f"  Traits: {report['stats'].get('traits', 0)}")
                print(f"  Exemplars: {report['stats'].get('exemplars', 0)}")
                print(f"  Registers: {report['stats'].get('registers', 0)}")
            else:
                print(f"✗ Invalid profile:")
                for err in report["errors"]:
                    print(f"  - {err}")

        elif args.command == "batch-build":
            results = batch_build_profiles(args.config, args.workers, not args.no_resume)
            success = sum(1 for r in results if r["status"] == "success")
            failed = sum(1 for r in results if r["status"] == "failed")
            print(f"\nSummary: {success} succeeded, {failed} failed")

        elif args.command == "batch-generate":
            results = batch_generate(args.config, args.workers)
            success = sum(1 for r in results if r["status"] == "success")
            failed = sum(1 for r in results if r["status"] == "failed")
            print(f"\nSummary: {success} succeeded, {failed} failed")

        elif args.command == "batch-judge":
            results = batch_judge(args.config, args.workers)
            success = sum(1 for r in results if r["status"] == "success")
            failed = sum(1 for r in results if r["status"] == "failed")
            print(f"\nSummary: {success} succeeded, {failed} failed")

        elif args.command == "compare-profiles":
            result = compare_profiles(args.profile_a, args.profile_b)
            print(f"Overall similarity: {result['overall_similarity']:.0%}")
            print(f"\nDimension scores:")
            for dim, score in result["dimension_scores"].items():
                print(f"  {dim:<12} {score:.0%}")
            print(f"\n{result['summary']}")

        elif args.command == "track-evolution":
            result = track_evolution(args.profiles, args.author, args.out)
            print(result["summary"])
            if result["drift_detected"]:
                print("\nDrift details:")
                for detail in result["drift_details"]:
                    print(f"  - {detail}")
            if args.out:
                print(f"\nReport saved to {args.out}")

        elif args.command == "detect-authors":
            authors = detect_authors(args.corpus_dir)
            print(f"Detected {len(authors)} author(s):")
            for author in authors:
                print(f"  - {author.get('name', 'Unknown')} ({len(author.get('sample_paths', []))} samples)")

        elif args.command == "attribute-text":
            text = Path(args.text_file).read_text(encoding="utf-8")
            profiles = [json.loads(Path(p).read_text()) for p in args.profiles]
            result = attribute_text(text, profiles)
            print(f"Attributed to: {result.get('author', 'Unknown')} (confidence: {result.get('confidence', 0):.0%})")
            if result.get("reasoning"):
                print(f"Reasoning: {result['reasoning']}")

        elif args.command == "collaborative-profile":
            profiles = [json.loads(Path(p).read_text()) for p in args.profiles]
            result = build_collaborative_profile(profiles, args.name, args.out)
            print(f"Collaborative profile created: {args.name}")
            if args.out:
                print(f"Saved to: {args.out}")

    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
