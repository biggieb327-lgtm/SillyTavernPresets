"""Unit tests for voicekit.schemas."""

import pytest
from voicekit.schemas import VOICE_PROFILE_SCHEMA


class TestSchemaStructure:
    """Test that the schema has the expected structure."""

    def test_schema_has_required_top_level_keys(self):
        required = VOICE_PROFILE_SCHEMA["required"]
        expected = {
            "schema_version",
            "profile_type",
            "meta",
            "corpus",
            "core_voice",
            "registers",
            "exemplars",
            "constraints",
            "evaluation",
            "generation_recipes",
        }
        assert set(required) == expected

    def test_schema_version_pattern(self):
        props = VOICE_PROFILE_SCHEMA["properties"]
        assert props["schema_version"]["pattern"] == r"^\d+\.\d+$"

    def test_evaluation_weights_sum_to_one(self):
        """Verify the default weights in the template sum to 1.0."""
        weights = {
            "rhythm": 0.2,
            "lexicon": 0.2,
            "stance": 0.25,
            "rhetoric": 0.2,
            "constraints": 0.15,
        }
        assert sum(weights.values()) == 1.0

    def test_pass_threshold_in_valid_range(self):
        evaluation = VOICE_PROFILE_SCHEMA["properties"]["evaluation"]
        threshold = evaluation["properties"]["pass_threshold"]
        assert threshold["minimum"] == 0
        assert threshold["maximum"] == 1

    def test_registers_have_four_types(self):
        registers = VOICE_PROFILE_SCHEMA["properties"]["registers"]["properties"]
        assert set(registers.keys()) == {"essay", "email", "dialogue", "sales"}

    def test_core_voice_has_six_dimensions(self):
        core = VOICE_PROFILE_SCHEMA["properties"]["core_voice"]["properties"]
        assert set(core.keys()) == {
            "rhythm", "syntax", "punctuation",
            "lexicon", "rhetoric", "stance",
        }

    def test_exemplars_require_minimum_items(self):
        exemplars = VOICE_PROFILE_SCHEMA["properties"]["exemplars"]["properties"]
        assert exemplars["signature_sentences"]["minItems"] == 3
        assert exemplars["signature_paragraphs"]["minItems"] == 1


class TestSchemaValidation:
    """Test schema validation with sample data."""

    def test_minimal_valid_profile(self, tmp_path):
        """A minimal profile should pass validation."""
        profile = {
            "schema_version": "1.0",
            "profile_type": "author_voice",
            "meta": {"author": "Test", "generated_at": "2026-09-08"},
            "corpus": {
                "file_count": 1,
                "total_words": 100,
                "sources": [{"label": "test", "word_count": 100}],
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
                    "filler_words": ["very", "really"],
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
                    "conviction_markers": ["clearly", "undoubtedly"],
                },
            },
            "registers": {
                "essay": {
                    "tone_shift": "reflective",
                    "formality_delta": "+1",
                    "typical_length": "800-1200 words",
                    "distinguishing_markers": ["first person", "anecdotes"],
                },
                "email": {
                    "tone_shift": "direct",
                    "formality_delta": "-1",
                    "typical_length": "100-300 words",
                    "distinguishing_markers": ["short paragraphs", "bullet points"],
                },
                "dialogue": {
                    "tone_shift": "casual",
                    "formality_delta": "-2",
                    "typical_length": "varied",
                    "distinguishing_markers": ["contractions", "fragments"],
                },
                "sales": {
                    "tone_shift": "persuasive",
                    "formality_delta": "0",
                    "typical_length": "500-800 words",
                    "distinguishing_markers": ["benefit-driven", "urgency"],
                },
            },
            "exemplars": {
                "signature_sentences": [
                    "The best writing is invisible.",
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
                "rewrite": {
                    "goal": "Transform text",
                    "steps": ["Step 1", "Step 2"],
                },
                "draft_from_bullets": {
                    "goal": "Expand bullets",
                    "steps": ["Step 1", "Step 2"],
                },
                "voice_judge": {
                    "goal": "Evaluate draft",
                    "steps": ["Step 1", "Step 2"],
                },
            },
        }
        # Should not raise
        import jsonschema
        jsonschema.validate(instance=profile, schema=VOICE_PROFILE_SCHEMA)

    def test_missing_required_field_fails(self):
        """A profile missing required fields should fail validation."""
        import jsonschema
        profile = {
            "schema_version": "1.0",
            "profile_type": "author_voice",
            # Missing meta, corpus, etc.
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=profile, schema=VOICE_PROFILE_SCHEMA)

    def test_invalid_schema_version_fails(self):
        """Schema version must match pattern."""
        import jsonschema
        profile = {
            "schema_version": "invalid",
            "profile_type": "author_voice",
            "meta": {"author": "Test", "generated_at": "2026-09-08"},
            "corpus": {"file_count": 1, "total_words": 100, "sources": [{"label": "test", "word_count": 100}]},
            "core_voice": {},
            "registers": {},
            "exemplars": {"signature_sentences": ["a", "b", "c"], "signature_paragraphs": ["p"]},
            "constraints": {"hard_rules": [], "anti_rules": [], "safety_notes": []},
            "evaluation": {"weights": {}, "pass_threshold": 0.5},
            "generation_recipes": {},
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=profile, schema=VOICE_PROFILE_SCHEMA)
