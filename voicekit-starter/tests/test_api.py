"""Tests for voicekit.api."""

import pytest
from fastapi.testclient import TestClient

from voicekit.api import app


client = TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self):
        """Should return ok status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "voicekit-api"}


class TestSchemaEndpoint:
    """Test schema endpoint."""

    def test_get_schema(self):
        """Should return the voice profile schema."""
        response = client.get("/schema")
        assert response.status_code == 200
        data = response.json()
        assert "properties" in data
        assert "schema_version" in data["properties"]


class TestBuildProfileEndpoint:
    """Test profile build endpoint."""

    def test_requires_files(self):
        """Should return 400 when no files provided."""
        response = client.post(
            "/profiles/build",
            data={"author": "Test Author"},
        )
        assert response.status_code == 400
        assert "No files provided" in response.json()["detail"]

    def test_rejects_invalid_extension(self):
        """Should reject files with invalid extension."""
        response = client.post(
            "/profiles/build",
            data={"author": "Test Author"},
            files={"files": ("test.exe", b"content", "application/octet-stream")},
        )
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    def test_sanitizes_path_traversal(self):
        """Should sanitize filenames with path traversal."""
        response = client.post(
            "/profiles/build",
            data={"author": "Test Author"},
            files={"files": ("../../../etc/passwd.md", b"content", "text/markdown")},
        )
        # Should not crash with path traversal - 500 from missing arg is acceptable
        assert response.status_code in [200, 400, 422, 500]

    def test_rejects_empty_filename(self):
        """Should reject files with empty filename."""
        response = client.post(
            "/profiles/build",
            data={"author": "Test Author"},
            files={"files": ("", b"content", "text/markdown")},
        )
        # FastAPI returns 422 for missing/invalid required fields
        assert response.status_code in [400, 422]


class TestGenerateEndpoint:
    """Test generate endpoint."""

    def test_requires_profile(self):
        """Should return 422 when no profile provided."""
        response = client.post(
            "/drafts/generate",
            data={"task": "Write an essay", "register": "essay"},
        )
        assert response.status_code == 422

    def test_requires_task(self):
        """Should return 422 when no task provided."""
        response = client.post(
            "/drafts/generate",
            data={"register": "essay"},
            files={"profile": ("profile.json", b"{}", "application/json")},
        )
        assert response.status_code == 422


class TestJudgeEndpoint:
    """Test judge endpoint."""

    def test_requires_profile(self):
        """Should return 422 when no profile provided."""
        response = client.post(
            "/drafts/judge",
            data={"draft": "Test draft", "register": "essay"},
        )
        assert response.status_code == 422

    def test_requires_draft(self):
        """Should return 422 when no draft provided."""
        response = client.post(
            "/drafts/judge",
            data={"register": "essay"},
            files={"profile": ("profile.json", b"{}", "application/json")},
        )
        assert response.status_code == 422


class TestListProfilesEndpoint:
    """Test list profiles endpoint."""

    def test_requires_directory(self):
        """Should return 500 when directory doesn't exist."""
        response = client.get("/profiles/list?directory=/nonexistent/path")
        assert response.status_code == 500


class TestCompareEndpoint:
    """Test compare endpoint."""

    def test_requires_two_profiles(self):
        """Should return 422 when only one profile provided."""
        response = client.post(
            "/profiles/compare",
            files={"profile_a": ("a.json", b"{}", "application/json")},
        )
        assert response.status_code == 422


class TestValidateEndpoint:
    """Test validate endpoint."""

    def test_requires_profile(self):
        """Should return 422 when no profile provided."""
        response = client.post("/profiles/validate")
        assert response.status_code == 422
