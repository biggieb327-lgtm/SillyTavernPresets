"""Tests for voicekit.profile_mgmt."""

import json
import pytest
from pathlib import Path

from voicekit.profile_mgmt import list_profiles, merge_profiles, validate_profile_cmd


class TestListProfiles:
    """Test list_profiles function."""

    def test_lists_valid_profiles(self, tmp_path, valid_profile):
        """Should list valid profiles in a directory."""
        (tmp_path / "test-profile.json").write_text(json.dumps(valid_profile))

        profiles = list_profiles(str(tmp_path))
        assert len(profiles) == 1
        assert profiles[0]["valid"] is True
        assert profiles[0]["author"] == "Test Author"

    def test_detects_invalid_profiles(self, tmp_path):
        """Should detect invalid profiles."""
        (tmp_path / "invalid.json").write_text('{"invalid": "data"}')

        profiles = list_profiles(str(tmp_path))
        assert len(profiles) == 1
        assert profiles[0]["valid"] is False

    def test_empty_directory(self, tmp_path):
        """Should return empty list for empty directory."""
        profiles = list_profiles(str(tmp_path))
        assert len(profiles) == 0


class TestValidateProfileCmd:
    """Test validate_profile_cmd function."""

    def test_valid_profile(self, valid_profile_file):
        """Should return valid report for valid profile."""
        report = validate_profile_cmd(str(valid_profile_file))
        assert report["valid"] is True
        assert report["stats"]["author"] == "Test Author"
        assert report["stats"]["traits"] == 2

    def test_invalid_profile(self, tmp_path):
        """Should return invalid report for invalid profile."""
        path = tmp_path / "invalid.json"
        path.write_text('{"invalid": "data"}')

        report = validate_profile_cmd(str(path))
        assert report["valid"] is False
        assert len(report["errors"]) > 0

    def test_nonexistent_file(self, tmp_path):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            validate_profile_cmd(str(tmp_path / "nonexistent.json"))
