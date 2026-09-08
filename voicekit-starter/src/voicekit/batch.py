#!/usr/bin/env python3
"""Sprint 2: Batch Processing for voicekit-starter.

Multi-author, parallel, and resume-capable batch operations."""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from voicekit.core import (
    build_profile,
    generate,
    judge,
    slugify,
    validate_profile,
)


def batch_build_profiles(
    config_path: str,
    max_workers: int = 3,
    resume: bool = True,
) -> list[dict]:
    """Build profiles for multiple authors from a config file.

    Config format (JSON):
    {
      "authors": [
        {
          "name": "Author Name",
          "samples_dir": "./samples/author1/",
          "out": "profiles/author1.json",
          "project_name": "Optional",
          "source_type": "Optional",
          "use_cases": "Optional"
        }
      ],
      "max_workers": 3,
      "retries": 2
    }
    """
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    authors = config.get("authors", [])
    retries = config.get("retries", 2)

    if not authors:
        raise ValueError("No authors in config")

    # Progress tracking
    progress_path = Path(config_path).with_suffix(".progress.json")
    completed = {}
    if resume and progress_path.exists():
        completed = json.loads(progress_path.read_text(encoding="utf-8"))
        print(f"Resuming: {len(completed)}/{len(authors)} already completed", file=sys.stderr)

    results = []

    def process_author(author_config: dict) -> dict:
        name = author_config["name"]
        if name in completed:
            return {"name": name, "status": "skipped", "path": completed[name]}

        try:
            out_path = build_profile(
                author=name,
                files=author_config.get("files"),
                samples_dir=author_config.get("samples_dir"),
                out=author_config.get("out"),
                project_name=author_config.get("project_name"),
                source_type=author_config.get("source_type"),
                use_cases=author_config.get("use_cases"),
                retries=retries,
            )
            return {"name": name, "status": "success", "path": str(out_path)}
        except Exception as e:
            return {"name": name, "status": "failed", "error": str(e)}

    # Process in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_author, a): a for a in authors}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            if result["status"] == "success":
                completed[result["name"]] = result["path"]
                progress_path.write_text(json.dumps(completed, indent=2), encoding="utf-8")

            status_icon = "✓" if result["status"] == "success" else "✗" if result["status"] == "failed" else "→"
            print(f"  {status_icon} {result['name']}: {result['status']}", file=sys.stderr)

    return results


def batch_generate(
    config_path: str,
    max_workers: int = 3,
) -> list[dict]:
    """Generate multiple drafts from a config file.

    Config format (JSON):
    {
      "tasks": [
        {
          "profile": "profiles/author1.json",
          "task_file": "briefs/essay1.md",
          "register": "essay",
          "out": "drafts/author1-essay1.md",
          "facts_file": "Optional"
        }
      ],
      "max_workers": 3
    }
    """
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    tasks = config.get("tasks", [])

    if not tasks:
        raise ValueError("No tasks in config")

    results = []

    def process_task(task_config: dict) -> dict:
        try:
            draft_text, out_path = generate(
                profile_path=task_config["profile"],
                task_file=task_config["task_file"],
                facts_file=task_config.get("facts_file"),
                register=task_config["register"],
                out=task_config.get("out"),
            )
            return {
                "task": task_config.get("task_file", "unknown"),
                "status": "success",
                "path": str(out_path) if out_path else None,
            }
        except Exception as e:
            return {
                "task": task_config.get("task_file", "unknown"),
                "status": "failed",
                "error": str(e),
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_task, t): t for t in tasks}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            status_icon = "✓" if result["status"] == "success" else "✗"
            print(f"  {status_icon} {result['task']}: {result['status']}", file=sys.stderr)

    return results


def batch_judge(
    config_path: str,
    max_workers: int = 3,
) -> list[dict]:
    """Judge multiple drafts from a config file.

    Config format (JSON):
    {
      "tasks": [
        {
          "profile": "profiles/author1.json",
          "draft_file": "drafts/essay1.md",
          "register": "essay",
          "out": "evals/essay1-eval.json"
        }
      ],
      "max_workers": 3
    }
    """
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    tasks = config.get("tasks", [])

    if not tasks:
        raise ValueError("No tasks in config")

    results = []

    def process_task(task_config: dict) -> dict:
        try:
            evaluation, out_path = judge(
                profile_path=task_config["profile"],
                draft_file=task_config["draft_file"],
                register=task_config["register"],
                out=task_config.get("out"),
            )
            return {
                "task": task_config.get("draft_file", "unknown"),
                "status": "success",
                "path": str(out_path),
            }
        except Exception as e:
            return {
                "task": task_config.get("draft_file", "unknown"),
                "status": "failed",
                "error": str(e),
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_task, t): t for t in tasks}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            status_icon = "✓" if result["status"] == "success" else "✗"
            print(f"  {status_icon} {result['task']}: {result['status']}", file=sys.stderr)

    return results


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: batch.py <build|generate|judge> <config.json> [--workers N] [--no-resume]")
        sys.exit(1)

    command = sys.argv[1]
    config_path = sys.argv[2]
    max_workers = 3
    resume = True

    for i, arg in enumerate(sys.argv[3:], 3):
        if arg == "--workers" and i + 1 < len(sys.argv):
            max_workers = int(sys.argv[i + 1])
        elif arg == "--no-resume":
            resume = False

    if command == "build":
        results = batch_build_profiles(config_path, max_workers, resume)
    elif command == "generate":
        results = batch_generate(config_path, max_workers)
    elif command == "judge":
        results = batch_judge(config_path, max_workers)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

    # Print summary
    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    print(f"\nSummary: {success} succeeded, {failed} failed, {skipped} skipped")
