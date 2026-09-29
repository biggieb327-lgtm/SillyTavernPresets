"""Unit tests for voicekit.core."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from voicekit.core import (
    slugify,
    collect_samples,
    build_corpus_text,
    load_template,
    validate_profile,
    strip_markdown_fences,
    get_model,
    get_client,
    build_profile,
)


class TestSlugify:
    """Test author name slugification."""

    def test_simple_name(self):
        assert slugify("Jane Smith") == "jane-smith"

    def test_multiple_words(self):
        assert slugify("John Jacob Schmidt") == "john-jacob-schmidt"

    def test_special_characters(self):
        assert slugify("O'Brien") == "o-brien"

    def test_mixed_case(self):
        assert slugify("McDonald") == "mcdonald"

    def test_empty_string_returns_author(self):
        assert slugify("") == "author"


class TestCollectSamples:
    """Test sample file collection."""

    def test_collects_single_file(self, tmp_path):
        f = tmp_path / "sample.md"
        f.write_text("Test content")
        result = collect_samples([str(f)], None)
        assert len(result) == 1
        assert result[0] == f.resolve()

    def test_collects_from_directory(self, tmp_path):
        (tmp_path / "a.md").write_text("A")
        (tmp_path / "b.txt").write_text("B")
        result = collect_samples(None, str(tmp_path))
        assert len(result) == 2

    def test_skips_unsupported_extensions(self, tmp_path, capsys):
        (tmp_path / "sample.pdf").write_text("PDF")
        (tmp_path / "sample.md").write_text("MD")
        result = collect_samples([str(tmp_path / "sample.pdf"), str(tmp_path / "sample.md")], None)
        assert len(result) == 1
        assert result[0].suffix == ".md"

    def test_raises_on_no_valid_files(self, tmp_path):
        with pytest.raises(ValueError, match="No valid sample files"):
            collect_samples(None, str(tmp_path))

    def test_deduplicates_files(self, tmp_path):
        f = tmp_path / "sample.md"
        f.write_text("Test")
        result = collect_samples([str(f), str(f)], None)
        assert len(result) == 1

    def test_raises_on_nonexistent_files(self, tmp_path):
        """Nonexistent files should raise ValueError when no valid files found."""
        with pytest.raises(ValueError, match="No valid sample files"):
            collect_samples(["/nonexistent/file.md"], None)


class TestBuildCorpusText:
    """Test corpus text building."""

    def test_builds_corpus_from_files(self, tmp_path):
        f1 = tmp_path / "a.md"
        f1.write_text("Hello world")
        f2 = tmp_path / "b.md"
        f2.write_text("Second file here")
        corpus, total_words, sources = build_corpus_text([f1, f2])
        assert "Hello world" in corpus
        assert "Second file here" in corpus
        assert total_words > 0
        assert len(sources) == 2

    def test_warns_on_large_corpus(self, tmp_path):
        f = tmp_path / "big.md"
        f.write_text("word " * 50000)  # 50k words = large corpus
        with pytest.warns(UserWarning, match="tokens"):
            build_corpus_text([f])


class TestStripMarkdownFences:
    """Test markdown fence removal."""

    def test_removes_json_fence(self):
        text = '```json\n{"key": "value"}\n```'
        assert strip_markdown_fences(text) == '{"key": "value"}'

    def test_removes_plain_fence(self):
        text = '```\nplain text\n```'
        assert strip_markdown_fences(text) == 'plain text'

    def test_no_fences_unchanged(self):
        text = '{"key": "value"}'
        assert strip_markdown_fences(text) == '{"key": "value"}'

    def test_strips_whitespace(self):
        text = '  \n```json\n{}\n```\n  '
        assert strip_markdown_fences(text) == '{}'


class TestGetModel:
    """Test model resolution."""

    def test_override_takes_precedence(self):
        assert get_model("gpt-4") == "gpt-4"

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
        assert get_model(None) == "gpt-4.1"

    def test_default_when_no_env(self, monkeypatch):
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        assert get_model(None) == "gpt-4.1-mini"


class TestGetClient:
    """Test OpenAI client creation."""

    def test_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                get_client()

    def test_creates_client_with_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        client = get_client()
        assert client is not None

    def test_respects_base_url(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
        client = get_client()
        assert "localhost" in str(client.base_url)


class TestLoadTemplate:
    """Test template loading."""

    def test_loads_valid_json(self):
        template = load_template()
        assert isinstance(template, dict)
        assert "schema_version" in template
        assert "core_voice" in template

    def test_has_expected_structure(self):
        template = load_template()
        assert "registers" in template
        assert set(template["registers"].keys()) == {"essay", "email", "dialogue", "sales"}


class TestValidateProfile:
    """Test profile validation."""

    def test_valid_profile_passes(self):
        profile = {
            "schema_version": "1.0",
            "profile_type": "author_voice",
            "meta": {"author": "Test", "generated_at": "2026-09-08"},
            "corpus": {"file_count": 1, "total_words": 100, "sources": [{"label": "test", "word_count": 100}]},
            "core_voice": {
                "rhythm": {"avg_sentence_length": "medium", "variation_pattern": "varied", "paragraph_cadence": "moderate"},
                "syntax": {"sentence_openers": ["First"], "clause_complexity": "moderate", "signature_structures": []},
                "punctuation": {"em_dash_usage": "frequent", "semicolon_frequency": "rare", "parenthetical_style": "em-dash", "list_style": "bullets"},
                "lexicon": {"formality_band": "semi-formal", "jargon_density": "low", "metaphor_family": [], "filler_words": []},
                "rhetoric": {"persuasion_mode": "logical", "evidence_style": "anecdotal", "humor_type": "dry", "concession_pattern": "acknowledge-counter"},
                "stance": {"authority_posture": "confident", "reader_relationship": "peer", "hedging_level": "low", "conviction_markers": []},
            },
            "registers": {
                "essay": {"tone_shift": "reflective", "formality_delta": "+1", "typical_length": "800 words", "distinguishing_markers": []},
                "email": {"tone_shift": "direct", "formality_delta": "-1", "typical_length": "200 words", "distinguishing_markers": []},
                "dialogue": {"tone_shift": "casual", "formality_delta": "-2", "typical_length": "varied", "distinguishing_markers": []},
                "sales": {"tone_shift": "persuasive", "formality_delta": "0", "typical_length": "600 words", "distinguishing_markers": []},
            },
            "exemplars": {
                "signature_sentences": ["a", "b", "c"],
                "signature_paragraphs": ["paragraph"],
            },
            "constraints": {"hard_rules": [], "anti_rules": [], "safety_notes": []},
            "evaluation": {"weights": {"rhythm": 0.2, "lexicon": 0.2, "stance": 0.25, "rhetoric": 0.2, "constraints": 0.15}, "pass_threshold": 0.7},
            "generation_recipes": {
                "rewrite": {"goal": "rewrite", "steps": []},
                "draft_from_bullets": {"goal": "draft", "steps": []},
                "voice_judge": {"goal": "judge", "steps": []},
            },
        }
        # Should not raise
        validate_profile(profile)

    def test_invalid_profile_raises(self):
        with pytest.raises(Exception):
            validate_profile({"invalid": "data"})


class TestBuildProfileKnownFields:
    """build_profile writes meta and corpus itself instead of trusting the model."""

    def _run(self, tmp_path, reply):
        sample = tmp_path / "sample.txt"
        sample.write_text("The river was high. We ran the boat hard all night.")
        calls = []

        def fake_call_llm(client, model, system, prompt, json_mode=False):
            calls.append(prompt)
            return json.dumps(reply)

        with patch("voicekit.core.get_client", return_value=MagicMock()), \
             patch("voicekit.core.call_llm", side_effect=fake_call_llm):
            out = build_profile("Test Author", [str(sample)], None, out=str(tmp_path / "p.json"))
        return json.loads(out.read_text()), calls

    def test_model_output_missing_source_label_still_passes(self, tmp_path, valid_profile):
        # The failure seen live in Author-Profile-Tool on 2026-09-29
        reply = json.loads(json.dumps(valid_profile))
        reply["meta"]["author"] = "Wrong Name"
        reply["corpus"] = {"file_count": 99, "total_words": 5, "sources": [{"word_count": 5}]}

        profile, calls = self._run(tmp_path, reply)

        assert len(calls) == 1
        assert profile["meta"]["author"] == "Test Author"
        assert profile["corpus"]["file_count"] == 1
        assert profile["corpus"]["sources"][0]["label"] == "sample"
        assert profile["corpus"]["total_words"] == profile["corpus"]["sources"][0]["word_count"]

    def test_template_sent_to_model_carries_known_fields(self, tmp_path, valid_profile):
        _, calls = self._run(tmp_path, valid_profile)
        assert '"author": "Test Author"' in calls[0]
        assert '"label":' in calls[0]


class TestCanonicalFiles:
    """The files Author-Profile-Tool vendors must stay readable by a non-Python tool."""

    def test_schema_json_matches_loaded_schema(self):
        import importlib.resources
        from voicekit.schemas import VOICE_PROFILE_SCHEMA
        raw = importlib.resources.files("voicekit").joinpath("templates/voice_profile_schema.json")
        assert json.loads(raw.read_text()) == VOICE_PROFILE_SCHEMA

    def test_unformatted_prompts_have_no_doubled_braces(self):
        # JUDGE_SYSTEM and GENERATOR_SYSTEM are sent as-is, never through str.format
        from voicekit.prompts import JUDGE_SYSTEM, GENERATOR_SYSTEM
        for prompt in (JUDGE_SYSTEM, GENERATOR_SYSTEM):
            assert "{{" not in prompt and "}}" not in prompt
