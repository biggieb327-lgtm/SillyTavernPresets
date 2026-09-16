"""Shared test fixtures for voicekit tests."""

import json
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def valid_profile():
    """A minimal valid voice profile matching the schema."""
    return {
        "schema_version": "1.0",
        "profile_type": "author_voice",
        "meta": {
            "author": "Test Author",
            "generated_at": "2026-09-08T00:00:00Z",
            "project_name": "Test Project",
            "source_type": "essays",
            "use_cases": ["blog", "email"],
        },
        "corpus": {
            "file_count": 2,
            "total_words": 1500,
            "sources": [
                {"label": "sample1", "word_count": 750},
                {"label": "sample2", "word_count": 750},
            ],
        },
        "core_voice": {
            "rhythm": {
                "avg_sentence_length": "15-20 words",
                "variation_pattern": "mixed long and short",
                "paragraph_cadence": "3-5 sentences",
            },
            "syntax": {
                "sentence_openers": ["However", "Moreover", "In contrast"],
                "clause_complexity": "moderate",
                "signature_structures": ["parallelism", "rhetorical questions"],
            },
            "punctuation": {
                "em_dash_usage": "frequent for emphasis",
                "semicolon_frequency": "rare",
                "parenthetical_style": "em-dashes",
                "list_style": "bullet points",
            },
            "lexicon": {
                "formality_band": "semi-formal",
                "jargon_density": "moderate",
                "metaphor_family": ["construction", "nature"],
                "filler_words": ["very", "really"],
            },
            "rhetoric": {
                "persuasion_mode": "inductive",
                "evidence_style": "anecdotal and statistical",
                "humor_type": "dry wit",
                "concession_pattern": "acknowledge then refute",
            },
            "stance": {
                "authority_posture": "authoritative yet approachable",
                "reader_relationship": "moderate",
                "hedging_level": "low",
                "conviction_markers": ["indeed", "fundamentally"],
            },
        },
        "registers": {
            "essay": {
                "tone_shift": "formal",
                "formality_delta": "+2",
                "typical_length": "1000-2000 words",
                "distinguishing_markers": ["citations", "structured arguments"],
            },
            "email": {
                "tone_shift": "casual",
                "formality_delta": "-1",
                "typical_length": "200-500 words",
                "distinguishing_markers": ["greeting", "sign-off"],
            },
            "dialogue": {
                "tone_shift": "conversational",
                "formality_delta": "-2",
                "typical_length": "varies",
                "distinguishing_markers": ["questions", "interruptions"],
            },
            "sales": {
                "tone_shift": "persuasive",
                "formality_delta": "0",
                "typical_length": "500-1000 words",
                "distinguishing_markers": ["call to action", "benefits"],
            },
        },
        "exemplars": {
            "signature_sentences": [
                "Indeed, the fundamental challenge lies not in the complexity of the problem, but in our approach to solving it.",
                "Moreover, the evidence suggests a different conclusion entirely.",
                "In contrast, the alternative offers little improvement.",
            ],
            "signature_paragraphs": [
                "The opening paragraph establishes the thesis with clarity and purpose, setting up the argument that follows.",
            ],
        },
        "constraints": {
            "hard_rules": ["use active voice", "vary sentence length"],
            "anti_rules": ["passive voice", "jargon without explanation"],
            "safety_notes": ["maintain consistent tone", "cite sources"],
        },
        "evaluation": {
            "weights": {
                "rhythm": 0.2,
                "lexicon": 0.2,
                "stance": 0.2,
                "rhetoric": 0.2,
                "constraints": 0.2,
            },
            "pass_threshold": 0.7,
        },
        "generation_recipes": {
            "rewrite": {
                "goal": "Rewrite text to match voice profile",
                "steps": ["Analyze source text", "Extract key points", "Regenerate in target voice"],
            },
            "draft_from_bullets": {
                "goal": "Create draft from bullet points",
                "steps": ["Expand bullets into sentences", "Apply voice traits", "Polish and refine"],
            },
            "voice_judge": {
                "goal": "Evaluate draft against profile",
                "steps": ["Score each dimension", "Identify gaps", "Suggest revisions"],
            },
        },
    }


@pytest.fixture
def valid_profile_file(valid_profile, tmp_path):
    """Write a valid profile to a temp file."""
    path = tmp_path / "test-profile.json"
    path.write_text(json.dumps(valid_profile, indent=2))
    return path
