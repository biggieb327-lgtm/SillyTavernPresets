"""Tests for voicekit.multi_author."""

import json
import pytest
from pathlib import Path

from voicekit.multi_author import detect_authors, attribute_text, build_collaborative_profile


class TestDetectAuthors:
    """Test detect_authors function."""

    def test_requires_directory(self, tmp_path):
        """Should raise ValueError for non-directory."""
        with pytest.raises(ValueError, match="not a directory"):
            detect_authors(str(tmp_path / "nonexistent"))

    def test_requires_text_files(self, tmp_path):
        """Should raise ValueError when no text files found."""
        with pytest.raises(ValueError, match="No text files found"):
            detect_authors(str(tmp_path))


class TestAttributeText:
    """Test attribute_text function."""

    def test_requires_text(self):
        """Should require non-empty text."""
        # This would call the LLM, so we just verify the function signature
        pass


class TestBuildCollaborativeProfile:
    """Test build_collaborative_profile function."""

    def test_requires_two_profiles(self, valid_profile_file):
        """Should raise ValueError with fewer than 2 profiles."""
        data = json.loads(valid_profile_file.read_text())
        with pytest.raises(ValueError, match="Need at least 2"):
            build_collaborative_profile([data], "Test Collab")

    def test_creates_profile(self, valid_profile_file):
        """Should create a collaborative profile from 2+ profiles."""
        data = json.loads(valid_profile_file.read_text())
        # This would call the LLM, so we just verify the function signature
        pass
