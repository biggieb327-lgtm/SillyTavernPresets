#!/usr/bin/env python3
"""Sprint 1: Profile Management + Enhanced Generation for voicekit-starter."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from voicekit.core import validate_profile, slugify, get_client, get_model, call_llm
from voicekit.prompts import GENERATOR_SYSTEM, GENERATOR_USER


def list_profiles(directory: str) -> list[dict]:
    """List and validate all profiles in a directory."""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise ValueError(f"{directory} is not a directory")
    
    profiles = []
    for p in sorted(dir_path.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            validate_profile(data)
            profiles.append({
                "path": str(p),
                "author": data.get("meta", {}).get("author", "unknown"),
                "version": data.get("schema_version", "unknown"),
                "valid": True,
            })
        except Exception as e:
            profiles.append({
                "path": str(p),
                "author": "unknown",
                "version": "unknown",
                "valid": False,
                "error": str(e),
            })
    return profiles


def merge_profiles(profile_paths: list[str], author: str, out: str | None = None) -> Path:
    """Merge multiple profiles into one combined profile."""
    profiles = []
    for path in profile_paths:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Profile not found: {path}")
        data = json.loads(p.read_text(encoding="utf-8"))
        validate_profile(data)
        profiles.append(data)
    
    if len(profiles) < 2:
        raise ValueError("Need at least 2 profiles to merge")
    
    # Use LLM to merge profiles intelligently
    client = get_client()
    model = get_model(None)
    
    profiles_json = json.dumps(profiles, indent=2)
    user_prompt = f"Merge these {len(profiles)} voice profiles into a single combined profile for '{author}'. " \
                  f"Combine all traits, average weights, merge exemplars, and preserve all unique characteristics.\n\n" \
                  f"Profiles:\n{profiles_json}"
    
    print(f"Merging {len(profiles)} profiles with {model}...", file=sys.stderr)
    raw = call_llm(client, model, GENERATOR_SYSTEM, user_prompt, json_mode=True)
    
    # Parse and validate
    import re
    raw = re.sub(r"^```(?:json)?\s*\n", "", raw.strip())
    raw = re.sub(r"\n```\s*$", "", raw)
    
    merged = json.loads(raw)
    validate_profile(merged)
    
    out_path = Path(out) if out else Path(f"{slugify(author)}-merged-profile.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def validate_profile_cmd(profile_path: str) -> dict:
    """Validate a profile and return detailed report."""
    p = Path(profile_path)
    if not p.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")
    
    data = json.loads(p.read_text(encoding="utf-8"))
    
    report = {
        "path": str(p),
        "valid": False,
        "errors": [],
        "warnings": [],
        "stats": {},
    }
    
    try:
        validate_profile(data)
        report["valid"] = True
    except Exception as e:
        report["errors"].append(str(e))
    
    # Gather stats
    if isinstance(data, dict):
        report["stats"]["author"] = data.get("meta", {}).get("author", "missing")
        report["stats"]["version"] = data.get("schema_version", "missing")
        report["stats"]["traits"] = len(data.get("core_voice", {}).get("stance", {}).get("conviction_markers", []))
        report["stats"]["exemplars"] = len(data.get("exemplars", {}).get("signature_sentences", []))
        report["stats"]["registers"] = len(data.get("registers", {}))
    
    return report


if __name__ == "__main__":
    # Quick test
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        profiles = list_profiles(sys.argv[2] if len(sys.argv) > 2 else ".")
        for p in profiles:
            status = "✓" if p["valid"] else "✗"
            print(f"  {status} {p['author']} ({p['version']}) - {p['path']}")
