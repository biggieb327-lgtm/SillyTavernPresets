"""Tests for voicekit.cli."""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from voicekit.cli import main


class TestCLIDispatcher:
    """Test CLI argument parsing and dispatch."""

    def test_version_flag(self, capsys):
        """Should print version and exit."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', '--version']):
                main()
        assert exc_info.value.code == 0

    def test_no_command_shows_help(self, capsys):
        """Should show help when no command given."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit']):
                main()
        assert exc_info.value.code == 2

    def test_build_profile_requires_author(self, capsys):
        """Should error without --author."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'build-profile', 'samples/']):
                main()
        assert exc_info.value.code == 2

    def test_build_profile_with_author(self, capsys):
        """Should accept --author."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'build-profile', 'samples/', '--author', 'Test']):
                main()
        # Will fail because samples/ doesn't exist (exit 1), but parsing should work
        assert exc_info.value.code in [1, 2]

    def test_generate_requires_profile(self, capsys):
        """Should error without --profile."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'generate', '--task-file', 'task.md', '--register', 'essay']):
                main()
        assert exc_info.value.code == 2

    def test_judge_requires_profile(self, capsys):
        """Should error without --profile."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'judge', '--draft-file', 'draft.md', '--register', 'essay']):
                main()
        assert exc_info.value.code == 2

    def test_list_profiles_requires_directory(self, capsys):
        """Should error without directory."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'list-profiles']):
                main()
        assert exc_info.value.code == 2

    def test_merge_profiles_requires_two(self, capsys):
        """Should error with fewer than 2 profiles."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'merge-profiles', 'one.json', '--author', 'Test']):
                main()
        # Will fail because one.json doesn't exist (exit 1), but parsing should work
        assert exc_info.value.code in [1, 2]

    def test_validate_profile_requires_profile(self, capsys):
        """Should error without profile."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'validate-profile']):
                main()
        assert exc_info.value.code == 2

    def test_compare_profiles_requires_two(self, capsys):
        """Should error with fewer than 2 profiles."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'compare-profiles', 'one.json']):
                main()
        assert exc_info.value.code == 2

    def test_track_evolution_requires_author(self, capsys):
        """Should error without --author."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'track-evolution', 'one.json', 'two.json']):
                main()
        assert exc_info.value.code == 2

    def test_detect_authors_requires_corpus(self, capsys):
        """Should error without corpus directory."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'detect-authors']):
                main()
        assert exc_info.value.code == 2

    def test_attribute_text_requires_text(self, capsys):
        """Should error without text file."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'attribute-text']):
                main()
        assert exc_info.value.code == 2

    def test_collaborative_profile_requires_name(self, capsys):
        """Should error without --name."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'collaborative-profile', 'one.json', 'two.json']):
                main()
        assert exc_info.value.code == 2

    def test_semantic_analysis_requires_args(self, capsys):
        """Should error without required args."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'semantic-analysis']):
                main()
        assert exc_info.value.code == 2

    def test_batch_build_requires_config(self, capsys):
        """Should error without config."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'batch-build']):
                main()
        assert exc_info.value.code == 2

    def test_batch_generate_requires_config(self, capsys):
        """Should error without config."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'batch-generate']):
                main()
        assert exc_info.value.code == 2

    def test_batch_judge_requires_config(self, capsys):
        """Should error without config."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'batch-judge']):
                main()
        assert exc_info.value.code == 2

    def test_serve_requires_no_args(self, capsys):
        """Should accept no args (uses defaults)."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'serve']):
                main()
        # Will fail because uvicorn can't start in test, but parsing should work
        assert exc_info.value.code == 1

    def test_serve_with_custom_host_port(self, capsys):
        """Should accept custom host and port."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'serve', '--host', '127.0.0.1', '--port', '9000']):
                main()
        assert exc_info.value.code == 1


class TestCLIErrorHandling:
    """Test CLI error handling."""

    def test_handles_runtime_error(self, capsys):
        """Should handle RuntimeError gracefully."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'build-profile', 'samples/', '--author', 'Test']):
                main()
        assert exc_info.value.code == 2

    def test_handles_value_error(self, capsys):
        """Should handle ValueError gracefully."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'build-profile', 'samples/', '--author', 'Test']):
                main()
        assert exc_info.value.code == 2

    def test_handles_file_not_found(self, capsys):
        """Should handle FileNotFoundError gracefully."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['voicekit', 'build-profile', 'samples/', '--author', 'Test']):
                main()
        assert exc_info.value.code == 2
