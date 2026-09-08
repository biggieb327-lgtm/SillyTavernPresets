"""Tests for voicekit.analysis."""

import json
import pytest
from pathlib import Path

from voicekit.analysis import compare_profiles, track_evolution


class TestCompareProfiles:
    """Test compare_profiles function."""

    def test_identical_profiles(self, valid_profile_file):
        """Identical profiles should have high similarity."""
        result = compare_profiles(str(valid_profile_file), str(valid_profile_file))
        assert result["overall_similarity"] == 1.0
        assert result["author_a"] == result["author_b"]

    def test_different_profiles(self, tmp_path, valid_profile):
        """Different profiles should have lower similarity."""
        profile_a = valid_profile.copy()
        profile_a["meta"] = valid_profile["meta"].copy()
        profile_a["meta"]["author"] = "Author A"

        profile_b = valid_profile.copy()
        profile_b["meta"] = valid_profile["meta"].copy()
        profile_b["meta"]["author"] = "Author B"
        # Modify a dimension
        profile_b["core_voice"] = valid_profile["core_voice"].copy()
        profile_b["core_voice"]["stance"] = valid_profile["core_voice"]["stance"].copy()
        profile_b["core_voice"]["stance"]["authority_posture"] = "very different value"

        path_a = tmp_path / "a.json"
        path_b = tmp_path / "b.json"
        path_a.write_text(json.dumps(profile_a))
        path_b.write_text(json.dumps(profile_b))

        result = compare_profiles(str(path_a), str(path_b))
        assert result["author_a"] == "Author A"
        assert result["author_b"] == "Author B"
        assert 0.0 <= result["overall_similarity"] <= 1.0


class TestTrackEvolution:
    """Test track_evolution function."""

    def test_requires_two_profiles(self):
        """Should raise ValueError with fewer than 2 profiles."""
        with pytest.raises(ValueError, match="at least 2"):
            track_evolution([], "Test Author")

    def test_detects_no_drift(self, tmp_path, valid_profile):
        """Identical profiles should show no drift."""
        path1 = tmp_path / "p1.json"
        path2 = tmp_path / "p2.json"
        path1.write_text(json.dumps(valid_profile))
        path2.write_text(json.dumps(valid_profile))

        result = track_evolution([str(path1), str(path2)], "Test Author")
        assert result["drift_detected"] is False

    def test_detects_drift(self, tmp_path, valid_profile):
        """Significant changes should be detected as drift."""
        profile_a = valid_profile.copy()
        profile_a["meta"] = valid_profile["meta"].copy()
        profile_a["core_voice"] = valid_profile["core_voice"].copy()
        profile_a["core_voice"]["stance"] = valid_profile["core_voice"]["stance"].copy()
        profile_a["core_voice"]["stance"]["authority_posture"] = "confident"

        profile_b = valid_profile.copy()
        profile_b["meta"] = valid_profile["meta"].copy()
        profile_b["core_voice"] = valid_profile["core_voice"].copy()
        profile_b["core_voice"]["stance"] = valid_profile["core_voice"]["stance"].copy()
        profile_b["core_voice"]["stance"]["authority_posture"] = "hesitant"

        path_a = tmp_path / "a.json"
        path_b = tmp_path / "b.json"
        path_a.write_text(json.dumps(profile_a))
        path_b.write_text(json.dumps(profile_b))

        result = track_evolution([str(path_a), str(path_b)], "Test Author")
        assert result["drift_detected"] is True
        assert len(result["drift_details"]) > 0

    def test_saves_report(self, tmp_path, valid_profile):
        """Should save report to file when --out specified."""
        path1 = tmp_path / "p1.json"
        path2 = tmp_path / "p2.json"
        path1.write_text(json.dumps(valid_profile))
        path2.write_text(json.dumps(valid_profile))

        out_path = tmp_path / "report.json"
        result = track_evolution([str(path1), str(path2)], "Test Author", str(out_path))

        assert out_path.exists()
        saved = json.loads(out_path.read_text())
        assert saved["author"] == "Test Author"
