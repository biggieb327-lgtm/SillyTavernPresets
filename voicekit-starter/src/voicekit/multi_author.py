#!/usr/bin/env python3
"""Sprint 1: Multi-author support for voicekit-starter.

Detect authors in a corpus, attribute text to authors, and create
collaborative voice profiles."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from voicekit.core import slugify, get_client, get_model, call_llm, strip_markdown_fences
from voicekit.prompts import GENERATOR_SYSTEM


def detect_authors(corpus_dir: str) -> list[dict]:
    """Detect distinct authors in a corpus directory.

    Analyzes writing samples and groups them by detected author.
    Returns a list of detected authors with their sample files.
    """
    corpus_path = Path(corpus_dir)
    if not corpus_path.is_dir():
        raise ValueError(f"{corpus_dir} is not a directory")

    # Collect all text files
    text_files = []
    for ext in ["*.txt", "*.md", "*.markdown"]:
        text_files.extend(corpus_path.rglob(ext))

    if not text_files:
        raise ValueError(f"No text files found in {corpus_dir}")

    # Read samples (full content, no truncation)
    samples = []
    for f in sorted(text_files):
        try:
            content = f.read_text(encoding="utf-8")
            if len(content) > 100:  # Skip very short files
                samples.append({"path": str(f), "content": content})
        except Exception:
            continue

    if not samples:
        raise ValueError("No valid text samples found")

    # Use LLM to detect authors
    samples_json = json.dumps(samples, indent=2)
    prompt = f"""Analyze these writing samples and group them by detected author.
For each detected author, list the sample file paths that belong to them.
Return JSON in this format:
{{"authors": [{{"name": "Author Name", "sample_paths": ["path1", "path2"], "confidence": 0.9}}]}}

Writing samples:
{samples_json}"""

    client = get_client()
    model = get_model(None)
    raw = call_llm(client, model, GENERATOR_SYSTEM, prompt, json_mode=True)

    raw = strip_markdown_fences(raw)

    result = json.loads(raw)
    return result.get("authors", [])


def attribute_text(text: str, author_profiles: list[dict]) -> dict:
    """Attribute a piece of text to one of the known authors.

    Returns the matched author and confidence score.
    """
    profiles_json = json.dumps(author_profiles, indent=2)
    prompt = f"""Given these author voice profiles and a piece of text, determine which author most likely wrote the text.

Return JSON in this format:
{{"author": "Author Name", "confidence": 0.85, "reasoning": "brief explanation"}}

Author profiles:
{profiles_json}

Text to attribute:
{text[:3000]}"""

    client = get_client()
    model = get_model(None)
    raw = call_llm(client, model, GENERATOR_SYSTEM, prompt, json_mode=True)

    raw = strip_markdown_fences(raw)

    return json.loads(raw)


def build_collaborative_profile(author_profiles: list[dict], name: str, out: str | None = None) -> dict:
    """Build a collaborative voice profile from multiple author profiles.

    Combines voice elements from multiple authors into a single profile
    that represents a collaborative voice.
    """
    if len(author_profiles) < 2:
        raise ValueError("Need at least 2 author profiles for collaborative voice")

    profiles_json = json.dumps(author_profiles, indent=2)
    prompt = f"""Create a collaborative voice profile that combines elements from these {len(author_profiles)} author profiles.
The collaborative profile should represent a voice that could work for any of these authors.
Combine traits, merge exemplars, and create a unified voice.

Return a complete voice profile JSON matching the voice_profile schema.

Author profiles:
{profiles_json}"""

    client = get_client()
    model = get_model(None)
    raw = call_llm(client, model, GENERATOR_SYSTEM, prompt, json_mode=True)

    raw = strip_markdown_fences(raw)

    profile = json.loads(raw)

    # Add collaborative metadata
    author_names = [p.get("meta", {}).get("author", "Unknown") for p in author_profiles]
    if "meta" not in profile:
        profile["meta"] = {}
    profile["meta"]["collaborative"] = True
    profile["meta"]["source_authors"] = author_names

    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")

    return profile


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: multi_author.py <detect|attribute|collaborate> <args...>")
        print("  detect <corpus_dir>")
        print("  attribute <text_file> <profile1.json> <profile2.json> ...")
        print("  collaborate <profile1.json> <profile2.json> ... --name <name> [--out <path>]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "detect":
        authors = detect_authors(sys.argv[2])
        print(json.dumps(authors, indent=2))
    elif command == "attribute":
        text = Path(sys.argv[2]).read_text(encoding="utf-8")
        profiles = [json.loads(Path(p).read_text()) for p in sys.argv[3:]]
        result = attribute_text(text, profiles)
        print(json.dumps(result, indent=2))
    elif command == "collaborate":
        profiles = []
        name = None
        out = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--name" and i + 1 < len(sys.argv):
                name = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--out" and i + 1 < len(sys.argv):
                out = sys.argv[i + 1]
                i += 2
            else:
                profiles.append(json.loads(Path(sys.argv[i]).read_text()))
                i += 1

        if not name:
            print("Error: --name required", file=sys.stderr)
            sys.exit(1)

        result = build_collaborative_profile(profiles, name, out)
        print(json.dumps(result, indent=2))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
