#!/usr/bin/env python3
"""Sprint 2: Semantic analysis with Propose-Prove pattern.

Based on Sembra's research: the LLM proposes candidate voice markers,
then verifies them against actual text. Hallucinated markers get zero
matches and are automatically dropped."""

import json
import re
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from voicekit.core import get_client, get_model, call_llm
from voicekit.prompts import GENERATOR_SYSTEM


def propose_voice_markers(sample_text: str, author: str) -> list[dict]:
    """Propose voice markers from sample text using LLM.

    Returns a list of candidate markers with evidence requirements.
    """
    prompt = f"""Analyze this writing sample by "{author}" and propose 5-10 specific voice markers.
A voice marker is a distinctive linguistic pattern, phrase, or stylistic habit that appears in the text.

For each marker, provide:
- marker: the specific pattern (e.g., "uses em-dashes for parenthetical asides")
- evidence: the exact quote from the text that demonstrates this marker
- category: rhythm | syntax | punctuation | lexicon | rhetoric | stance

Return JSON: {{"markers": [{{"marker": "...", "evidence": "...", "category": "..."}}]}}

Text:
{sample_text[:4000]}"""

    client = get_client()
    model = get_model(None)
    raw = call_llm(client, model, GENERATOR_SYSTEM, prompt, json_mode=True)

    raw = re.sub(r"^```(?:json)?\s*\n", "", raw.strip())
    raw = re.sub(r"\n```\s*$", "", raw)

    result = json.loads(raw)
    return result.get("markers", [])


def verify_markers(markers: list[dict], corpus_text: str) -> list[dict]:
    """Propose-Prove: verify proposed markers against the full corpus.

    Markers without actual evidence in the corpus are dropped.
    Returns only verified markers with match counts.
    """
    verified = []
    corpus_lower = corpus_text.lower()

    for marker in markers:
        evidence = marker.get("evidence", "").lower()
        if not evidence:
            continue

        # Count occurrences of the evidence pattern in the corpus
        # Use a simplified matching approach
        words = evidence.split()
        if len(words) < 3:
            continue

        # Check if key phrases from the evidence appear in corpus
        key_phrase = " ".join(words[:5])  # First 5 words as key phrase
        count = corpus_lower.count(key_phrase)

        if count > 0:
            verified.append({
                "marker": marker.get("marker", ""),
                "evidence": marker.get("evidence", ""),
                "category": marker.get("category", ""),
                "corpus_matches": count,
                "verified": True,
            })

    return verified


def analyze_semantic_patterns(sample_text: str, corpus_text: str, author: str) -> dict:
    """Full semantic analysis with Propose-Prove pattern.

    Proposes markers from a sample, then verifies against the full corpus.
    Returns verified markers and analysis summary.
    """
    # Step 1: Propose markers from sample
    proposed = propose_voice_markers(sample_text, author)

    # Step 2: Verify against full corpus
    verified = verify_markers(proposed, corpus_text)

    # Step 3: Categorize and summarize
    by_category = {}
    for m in verified:
        cat = m.get("category", "unknown")
        by_category.setdefault(cat, []).append(m)

    return {
        "author": author,
        "proposed_count": len(proposed),
        "verified_count": len(verified),
        "verification_rate": round(len(verified) / len(proposed), 2) if proposed else 0,
        "verified_markers": verified,
        "by_category": {cat: len(markers) for cat, markers in by_category.items()},
        "summary": _generate_semantic_summary(author, len(proposed), len(verified), by_category),
    }


def _generate_semantic_summary(author: str, proposed: int, verified: int, by_category: dict) -> str:
    """Generate a human-readable semantic analysis summary."""
    rate = verified / proposed if proposed else 0

    if rate >= 0.8:
        quality = "high confidence"
    elif rate >= 0.5:
        quality = "moderate confidence"
    else:
        quality = "low confidence"

    parts = [
        f"Semantic analysis for {author}: {verified}/{proposed} proposed markers verified ({quality}).",
    ]

    if by_category:
        cats = ", ".join(f"{cat}: {len(markers)}" for cat, markers in by_category.items())
        parts.append(f"Markers by category: {cats}.")

    return " ".join(parts)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: semantic.py <sample_text> <corpus_text> <author>")
        sys.exit(1)

    sample_text = Path(sys.argv[1]).read_text(encoding="utf-8")
    corpus_text = Path(sys.argv[2]).read_text(encoding="utf-8")
    author = sys.argv[3]

    result = analyze_semantic_patterns(sample_text, corpus_text, author)
    print(json.dumps(result, indent=2))
