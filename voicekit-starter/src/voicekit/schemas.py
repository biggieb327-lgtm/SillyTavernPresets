"""JSON schema for voice profile validation."""

VOICE_PROFILE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Voice Profile",
    "type": "object",
    "required": [
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
    ],
    "properties": {
        "schema_version": {"type": "string", "pattern": "^\\d+\\.\\d+$"},
        "profile_type": {"type": "string"},
        "meta": {
            "type": "object",
            "required": ["author", "generated_at"],
            "properties": {
                "author": {"type": "string"},
                "generated_at": {"type": "string"},
                "project_name": {"type": "string"},
                "source_type": {"type": "string"},
                "use_cases": {"type": "array", "items": {"type": "string"}},
            },
        },
        "corpus": {
            "type": "object",
            "required": ["file_count", "total_words", "sources"],
            "properties": {
                "file_count": {"type": "integer", "minimum": 1},
                "total_words": {"type": "integer", "minimum": 1},
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["label", "word_count"],
                        "properties": {
                            "label": {"type": "string"},
                            "word_count": {"type": "integer"},
                        },
                    },
                },
            },
        },
        "core_voice": {
            "type": "object",
            "required": ["rhythm", "syntax", "punctuation", "lexicon", "rhetoric", "stance"],
            "properties": {
                "rhythm": {
                    "type": "object",
                    "required": ["avg_sentence_length", "variation_pattern", "paragraph_cadence"],
                    "properties": {
                        "avg_sentence_length": {"type": "string"},
                        "variation_pattern": {"type": "string"},
                        "paragraph_cadence": {"type": "string"},
                    },
                },
                "syntax": {
                    "type": "object",
                    "required": ["sentence_openers", "clause_complexity", "signature_structures"],
                    "properties": {
                        "sentence_openers": {"type": "array", "items": {"type": "string"}},
                        "clause_complexity": {"type": "string"},
                        "signature_structures": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "punctuation": {
                    "type": "object",
                    "required": ["em_dash_usage", "semicolon_frequency", "parenthetical_style", "list_style"],
                    "properties": {
                        "em_dash_usage": {"type": "string"},
                        "semicolon_frequency": {"type": "string"},
                        "parenthetical_style": {"type": "string"},
                        "list_style": {"type": "string"},
                    },
                },
                "lexicon": {
                    "type": "object",
                    "required": ["formality_band", "jargon_density", "metaphor_family", "filler_words"],
                    "properties": {
                        "formality_band": {"type": "string"},
                        "jargon_density": {"type": "string"},
                        "metaphor_family": {"type": "array", "items": {"type": "string"}},
                        "filler_words": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "rhetoric": {
                    "type": "object",
                    "required": ["persuasion_mode", "evidence_style", "humor_type", "concession_pattern"],
                    "properties": {
                        "persuasion_mode": {"type": "string"},
                        "evidence_style": {"type": "string"},
                        "humor_type": {"type": "string"},
                        "concession_pattern": {"type": "string"},
                    },
                },
                "stance": {
                    "type": "object",
                    "required": ["authority_posture", "reader_relationship", "hedging_level", "conviction_markers"],
                    "properties": {
                        "authority_posture": {"type": "string"},
                        "reader_relationship": {"type": "string"},
                        "hedging_level": {"type": "string"},
                        "conviction_markers": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
        "registers": {
            "type": "object",
            "required": ["essay", "email", "dialogue", "sales"],
            "properties": {
                "essay": {"$ref": "#/$defs/register_block"},
                "email": {"$ref": "#/$defs/register_block"},
                "dialogue": {"$ref": "#/$defs/register_block"},
                "sales": {"$ref": "#/$defs/register_block"},
            },
        },
        "exemplars": {
            "type": "object",
            "required": ["signature_sentences", "signature_paragraphs"],
            "properties": {
                "signature_sentences": {
                    "type": "array",
                    "minItems": 3,
                    "items": {"type": "string"},
                },
                "signature_paragraphs": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string"},
                },
            },
        },
        "constraints": {
            "type": "object",
            "required": ["hard_rules", "anti_rules", "safety_notes"],
            "properties": {
                "hard_rules": {"type": "array", "items": {"type": "string"}},
                "anti_rules": {"type": "array", "items": {"type": "string"}},
                "safety_notes": {"type": "array", "items": {"type": "string"}},
            },
        },
        "evaluation": {
            "type": "object",
            "required": ["weights", "pass_threshold"],
            "properties": {
                "weights": {
                    "type": "object",
                    "required": ["rhythm", "lexicon", "stance", "rhetoric", "constraints"],
                    "properties": {
                        "rhythm": {"type": "number"},
                        "lexicon": {"type": "number"},
                        "stance": {"type": "number"},
                        "rhetoric": {"type": "number"},
                        "constraints": {"type": "number"},
                    },
                },
                "pass_threshold": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "generation_recipes": {
            "type": "object",
            "required": ["rewrite", "draft_from_bullets", "voice_judge"],
            "properties": {
                "rewrite": {"$ref": "#/$defs/recipe_block"},
                "draft_from_bullets": {"$ref": "#/$defs/recipe_block"},
                "voice_judge": {"$ref": "#/$defs/recipe_block"},
            },
        },
    },
    "$defs": {
        "register_block": {
            "type": "object",
            "required": ["tone_shift", "formality_delta", "typical_length", "distinguishing_markers"],
            "properties": {
                "tone_shift": {"type": "string"},
                "formality_delta": {"type": "string"},
                "typical_length": {"type": "string"},
                "distinguishing_markers": {"type": "array", "items": {"type": "string"}},
            },
        },
        "recipe_block": {
            "type": "object",
            "required": ["goal", "steps"],
            "properties": {
                "goal": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}
