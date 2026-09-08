"""Shared fixtures for voicekit tests."""

import json
import os
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def sample_corpus(tmp_path):
    """Create a sample corpus for testing."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "essay1.md").write_text(
        "# On Writing\n\nWriting is thinking made visible. "
        "When we write clearly, we think clearly."
    )
    (corpus_dir / "essay2.md").write_text(
        "# On Revision\n\nThe first draft is just you telling yourself the story. "
        "The real work begins when you shape that story for someone else."
    )
    return corpus_dir


@pytest.fixture
def valid_profile():
    """Return a valid voice profile dict."""
    return {
        "schema_version": "1.0",
        "profile_type": "author_voice",
        "meta": {"author": "Test Author", "generated_at": "2026-09-08"},
        "corpus": {
            "file_count": 2,
            "total_words": 500,
            "sources": [
                {"label": "essay1", "word_count": 250},
                {"label": "essay2", "word_count": 250},
            ],
        },
        "core_voice": {
            "rhythm": {
                "avg_sentence_length": "medium",
                "variation_pattern": "varied",
                "paragraph_cadence": "moderate",
            },
            "syntax": {
                "sentence_openers": ["First", "Then"],
                "clause_complexity": "moderate",
                "signature_structures": ["parallelism"],
            },
            "punctuation": {
                "em_dash_usage": "frequent",
                "semicolon_frequency": "rare",
                "parenthetical_style": "em-dash",
                "list_style": "bullets",
            },
            "lexicon": {
                "formality_band": "semi-formal",
                "jargon_density": "low",
                "metaphor_family": ["architecture"],
                "filler_words": ["very"],
            },
            "rhetoric": {
                "persuasion_mode": "logical",
                "evidence_style": "anecdotal",
                "humor_type": "dry",
                "concession_pattern": "acknowledge-counter",
            },
            "stance": {
                "authority_posture": "confident",
                "reader_relationship": "peer",
                "hedging_level": "low",
                "conviction_markers": ["clearly"],
            },
        },
        "registers": {
            "essay": {
                "tone_shift": "reflective",
                "formality_delta": "+1",
                "typical_length": "800-1200 words",
                "distinguishing_markers": ["first person"],
            },
            "email": {
                "tone_shift": "direct",
                "formality_delta": "-1",
                "typical_length": "100-300 words",
                "distinguishing_markers": ["short paragraphs"],
            },
            "dialogue": {
                "tone_shift": "casual",
                "formality_delta": "-2",
                "typical_length": "varied",
                "distinguishing_markers": ["contractions"],
            },
            "sales": {
                "tone_shift": "persuasive",
                "formality_delta": "0",
                "typical_length": "500-800 words",
                "distinguishing_markers": ["benefit-driven"],
            },
        },
        "exemplars": {
            "signature_sentences": [
                "Writing is thinking made visible.",
                "Clarity is kindness.",
                "Every word must earn its place.",
            ],
            "signature_paragraphs": [
                "I've spent years editing, and the pattern is always the same.",
            ],
        },
        "constraints": {
            "hard_rules": ["No exclamation marks"],
            "anti_rules": ["Avoid corporate jargon"],
            "safety_notes": ["Check facts before publishing"],
        },
        "evaluation": {
            "weights": {
                "rhythm": 0.2,
                "lexicon": 0.2,
                "stance": 0.25,
                "rhetoric": 0.2,
                "constraints": 0.15,
            },
            "pass_threshold": 0.7,
        },
        "generation_recipes": {
            "rewrite": {"goal": "Transform text", "steps": ["Step 1"]},
            "draft_from_bullets": {"goal": "Expand bullets", "steps": ["Step 1"]},
            "voice_judge": {"goal": "Evaluate draft", "steps": ["Step 1"]},
        },
    }
