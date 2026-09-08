#!/usr/bin/env python3
"""Sprint 3: Analysis Features for voicekit-starter.

Profile comparison and voice evolution tracking."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from voicekit.core import validate_profile, slugify, get_client, get_model, call_llm
from voicekit.prompts import GENERATOR_SYSTEM


def compare_profiles(profile_path_a: str, profile_path_b: str) -> dict:
    """Compare two voice profiles and return similarity analysis."""
    profile_a = json.loads(Path(profile_path_a).read_text(encoding="utf-8"))
    profile_b = json.loads(Path(profile_path_b).read_text(encoding="utf-8"))

    validate_profile(profile_a)
    validate_profile(profile_b)

    author_a = profile_a.get("meta", {}).get("author", "Unknown")
    author_b = profile_b.get("meta", {}).get("author", "Unknown")

    # Calculate similarity scores for each dimension
    scores = {}
    details = {}

    # Compare core voice dimensions
    core_a = profile_a.get("core_voice", {})
    core_b = profile_b.get("core_voice", {})

    for dimension in ["rhythm", "syntax", "punctuation", "lexicon", "rhetoric", "stance"]:
        dim_a = core_a.get(dimension, {})
        dim_b = core_b.get(dimension, {})

        if not dim_a or not dim_b:
            scores[dimension] = 0.0
            details[dimension] = "Missing data"
            continue

        # Simple similarity: count matching keys
        all_keys = set(dim_a.keys()) | set(dim_b.keys())
        matching = sum(1 for k in all_keys if dim_a.get(k) == dim_b.get(k))
        similarity = matching / len(all_keys) if all_keys else 0.0
        scores[dimension] = round(similarity, 2)

    # Compare registers
    reg_a = set(profile_a.get("registers", {}).keys())
    reg_b = set(profile_b.get("registers", {}).keys())
    if reg_a or reg_b:
        intersection = reg_a & reg_b
        union = reg_a | reg_b
        scores["registers"] = round(len(intersection) / len(union), 2) if union else 0.0
    else:
        scores["registers"] = 0.0

    # Overall similarity
    overall = round(sum(scores.values()) / len(scores), 2) if scores else 0.0

    return {
        "author_a": author_a,
        "author_b": author_b,
        "overall_similarity": overall,
        "dimension_scores": scores,
        "summary": _generate_comparison_summary(author_a, author_b, overall, scores),
    }


def _generate_comparison_summary(author_a: str, author_b: str, overall: float, scores: dict) -> str:
    """Generate a human-readable comparison summary."""
    if overall >= 0.8:
        similarity = "very similar"
    elif overall >= 0.6:
        similarity = "moderately similar"
    elif overall >= 0.4:
        similarity = "somewhat different"
    else:
        similarity = "very different"

    # Find most and least similar dimensions
    sorted_dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    most_similar = sorted_dims[0] if sorted_dims else (None, 0)
    least_similar = sorted_dims[-1] if sorted_dims else (None, 0)

    parts = [
        f"{author_a} and {author_b} have {similarity} writing styles (overall: {overall:.0%}).",
    ]

    if most_similar[0]:
        parts.append(f"Most similar dimension: {most_similar[0]} ({most_similar[1]:.0%}).")
    if least_similar[0] and least_similar != most_similar:
        parts.append(f"Least similar dimension: {least_similar[0]} ({least_similar[1]:.0%}).")

    return " ".join(parts)


def track_evolution(
    profile_history: list[str],
    author: str,
    out: str | None = None,
) -> dict:
    """Track voice evolution across multiple profiles over time."""
    if len(profile_history) < 2:
        raise ValueError("Need at least 2 profiles to track evolution")

    profiles = []
    for path in profile_history:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        validate_profile(data)
        profiles.append(data)

    # Analyze trends across profiles
    trends = _analyze_trends(profiles)

    # Detect drift
    drift = _detect_drift(profiles)

    result = {
        "author": author,
        "profile_count": len(profiles),
        "date_range": {
            "first": profiles[0].get("meta", {}).get("generated_at", "unknown"),
            "last": profiles[-1].get("meta", {}).get("generated_at", "unknown"),
        },
        "trends": trends,
        "drift_detected": drift["detected"],
        "drift_details": drift["details"],
        "summary": _generate_evolution_summary(author, trends, drift),
    }

    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


def _analyze_trends(profiles: list[dict]) -> dict:
    """Analyze trends across profile history."""
    trends = {}

    # Track stance changes
    stances = []
    for p in profiles:
        stance = p.get("core_voice", {}).get("stance", {})
        if stance:
            stances.append(stance.get("authority_posture", "unknown"))

    if len(set(stances)) > 1:
        trends["stance"] = {"change": f"{stances[0]} → {stances[-1]}", "values": stances}

    # Track register count changes
    reg_counts = [len(p.get("registers", {})) for p in profiles]
    if len(set(reg_counts)) > 1:
        trends["register_count"] = {"change": f"{reg_counts[0]} → {reg_counts[-1]}", "values": reg_counts}

    # Track lexicon changes
    lexicon_a = set(profiles[0].get("core_voice", {}).get("lexicon", {}).get("filler_words", []))
    lexicon_b = set(profiles[-1].get("core_voice", {}).get("lexicon", {}).get("filler_words", []))
    if lexicon_a != lexicon_b:
        added = lexicon_b - lexicon_a
        removed = lexicon_a - lexicon_b
        trends["lexicon"] = {
            "filler_words_added": list(added),
            "filler_words_removed": list(removed),
        }

    return trends


def _detect_drift(profiles: list[dict]) -> dict:
    """Detect significant voice drift between first and last profile."""
    if len(profiles) < 2:
        return {"detected": False, "details": []}

    first = profiles[0]
    last = profiles[-1]
    drift_details = []

    # Check for significant stance changes
    stance_first = first.get("core_voice", {}).get("stance", {}).get("authority_posture", "")
    stance_last = last.get("core_voice", {}).get("stance", {}).get("authority_posture", "")
    if stance_first != stance_last:
        drift_details.append(f"Stance shifted from '{stance_first}' to '{stance_last}'")

    # Check for register count changes
    reg_first = len(first.get("registers", {}))
    reg_last = len(last.get("registers", {}))
    if abs(reg_last - reg_first) >= 2:
        drift_details.append(f"Register count changed from {reg_first} to {reg_last}")

    # Check for evaluation threshold changes
    eval_first = first.get("evaluation", {}).get("pass_threshold", 0)
    eval_last = last.get("evaluation", {}).get("pass_threshold", 0)
    if abs(eval_last - eval_first) >= 0.1:
        drift_details.append(f"Pass threshold changed from {eval_first} to {eval_last}")

    return {
        "detected": len(drift_details) > 0,
        "details": drift_details,
    }


def _generate_evolution_summary(author: str, trends: dict, drift: dict) -> str:
    """Generate a human-readable evolution summary."""
    parts = [f"Voice evolution analysis for {author}:"]

    if not trends:
        parts.append("No significant changes detected across profiles.")
    else:
        parts.append(f"Detected {len(trends)} trend(s): {', '.join(trends.keys())}.")

    if drift["detected"]:
        parts.append(f"Voice drift detected: {'; '.join(drift['details'])}.")
    else:
        parts.append("No significant voice drift detected.")

    return " ".join(parts)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: analysis.py <compare|evolve> <args...>")
        print("  compare <profile_a.json> <profile_b.json>")
        print("  evolve <profile1.json> <profile2.json> ... --author <name> [--out <path>]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "compare":
        result = compare_profiles(sys.argv[2], sys.argv[3])
        print(json.dumps(result, indent=2))
    elif command == "evolve":
        profiles = []
        author = None
        out = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--author" and i + 1 < len(sys.argv):
                author = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--out" and i + 1 < len(sys.argv):
                out = sys.argv[i + 1]
                i += 2
            else:
                profiles.append(sys.argv[i])
                i += 1

        if not author:
            print("Error: --author required", file=sys.stderr)
            sys.exit(1)

        result = track_evolution(profiles, author, out)
        print(json.dumps(result, indent=2))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
