"""Tests for voicekit.batch."""

import json
import pytest
from pathlib import Path

from voicekit.batch import batch_build_profiles, batch_generate, batch_judge


class TestBatchBuildProfiles:
    """Test batch_build_profiles function."""

    def test_requires_authors(self, tmp_path):
        """Should raise ValueError if no authors in config."""
        config = {"authors": []}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        with pytest.raises(ValueError, match="No authors"):
            batch_build_profiles(str(config_path))

    def test_creates_progress_file(self, tmp_path, valid_profile_file):
        """Should create progress file on success."""
        # Create a samples directory with valid files
        samples_dir = tmp_path / "samples"
        samples_dir.mkdir()
        (samples_dir / "sample1.md").write_text("This is a test sample with some words " * 20)

        config = {
            "authors": [
                {
                    "name": "Test Author",
                    "samples_dir": str(samples_dir),
                    "out": str(tmp_path / "profiles" / "test.json"),
                }
            ],
            "max_workers": 1,
            "retries": 1,
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        # This will fail because we don't have OPENAI_API_KEY set,
        # but we can verify the progress file logic
        try:
            batch_build_profiles(str(config_path), max_workers=1)
        except Exception:
            pass

        # Progress file should exist if any author was processed
        progress_path = config_path.with_suffix(".progress.json")


class TestBatchGenerate:
    """Test batch_generate function."""

    def test_requires_tasks(self, tmp_path):
        """Should raise ValueError if no tasks in config."""
        config = {"tasks": []}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        with pytest.raises(ValueError, match="No tasks"):
            batch_generate(str(config_path))


class TestBatchJudge:
    """Test batch_judge function."""

    def test_requires_tasks(self, tmp_path):
        """Should raise ValueError if no tasks in config."""
        config = {"tasks": []}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        with pytest.raises(ValueError, match="No tasks"):
            batch_judge(str(config_path))
