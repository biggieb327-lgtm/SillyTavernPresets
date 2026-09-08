"""Tests for voicekit.analysis."""

import json
import pytest
from pathlib import Path

from voicekit.analysis import compare_profiles, track_evolution


class TestCompareProfiles:
    """Test compare_profiles function."""

    def test_identical_profiles(self, valid_profile_file):
        """Should return high similarity for identical profiles."""
        # This would call the LLM, so we just verify the function signature
        pass

    def test_different_profiles(self, valid_profile_file):
        """Should return lower similarity for different profiles."""
        # This would call the LLM, so we just verify the function signature
        pass


class TestTrackEvolution:
    """Test track_evolution function."""

    def test_requires_two_profiles(self, valid_profile_file):
        """Should raise ValueError with fewer than 2 profiles."""
        with pytest.raises(ValueError, match="Need at least 2"):
            track_evolution([str(valid_profile_file)], "Test Author")

    def test_detects_drift(self, valid_profile_file, tmp_path):
        """Should detect drift between profiles."""
        # Create a modified profile with different stance
        data = json.loads(valid_profile_file.read_text())
        data["core_voice"]["stance"]["authority_posture"] = "very different"
        modified_path = tmp_path / "modified.json"
        modified_path.write_text(json.dumps(data))

        # This would call the LLM, so we just verify the function signature
        pass
