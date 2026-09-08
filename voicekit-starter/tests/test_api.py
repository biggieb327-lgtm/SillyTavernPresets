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


class TestProfilesEndpoint:
    """Test profiles endpoints."""

    def test_build_requires_files(self):
        """Should return 400 if no files provided."""
        response = client.post(
            "/profiles/build",
            data={"author": "Test Author"},
        )
        assert response.status_code == 400


class TestDraftsEndpoint:
    """Test drafts endpoints."""

    def test_generate_requires_profile(self):
        """Should return 422 if profile missing."""
        response = client.post(
            "/drafts/generate",
            data={"task": "Write an essay", "register": "essay"},
        )
        assert response.status_code == 422

    def test_judge_requires_profile(self):
        """Should return 422 if profile missing."""
        response = client.post(
            "/drafts/judge",
            data={"draft": "Test draft", "register": "essay"},
        )
        assert response.status_code == 422
