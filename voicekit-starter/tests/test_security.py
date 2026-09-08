"""Tests for voicekit.security."""

import os
import pytest
from fastapi.testclient import TestClient

from voicekit.api import app
from voicekit.security import (
    RateLimiter,
    validate_author_name,
    validate_register,
    sanitize_text_input,
    generate_api_key,
    rotate_api_key,
)
from fastapi import HTTPException


client = TestClient(app)


class TestRateLimiter:
    """Test RateLimiter class."""

    def test_allows_under_limit(self):
        """Should allow requests under the limit."""
        limiter = RateLimiter(requests_per_minute=60, burst=10)
        for _ in range(10):
            assert limiter.is_allowed("client1") is True

    def test_blocks_over_burst(self):
        """Should block requests over the burst limit."""
        limiter = RateLimiter(requests_per_minute=60, burst=5)
        for _ in range(5):
            limiter.is_allowed("client1")
        assert limiter.is_allowed("client1") is False

    def test_separate_clients(self):
        """Should track clients separately."""
        limiter = RateLimiter(requests_per_minute=60, burst=5)
        for _ in range(5):
            limiter.is_allowed("client1")
        # client2 should still be allowed
        assert limiter.is_allowed("client2") is True

    def test_retry_after(self):
        """Should return retry-after time."""
        limiter = RateLimiter(requests_per_minute=60, burst=1)
        limiter.is_allowed("client1")
        retry = limiter.get_retry_after("client1")
        assert 0 <= retry <= 60


class TestValidateAuthorName:
    """Test validate_author_name function."""

    def test_valid_name(self):
        """Should accept valid author name."""
        assert validate_author_name("Jane Smith") == "Jane Smith"

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        assert validate_author_name("  Jane Smith  ") == "Jane Smith"

    def test_rejects_empty(self):
        """Should reject empty name."""
        with pytest.raises(HTTPException, match="required"):
            validate_author_name("")

    def test_rejects_too_long(self):
        """Should reject names over 200 chars."""
        with pytest.raises(HTTPException, match="too long"):
            validate_author_name("A" * 201)

    def test_removes_control_chars(self):
        """Should remove control characters."""
        result = validate_author_name("Jane\x00Smith")
        assert "\x00" not in result


class TestValidateRegister:
    """Test validate_register function."""

    def test_valid_registers(self):
        """Should accept valid registers."""
        for reg in ["essay", "email", "dialogue", "sales", "formal", "casual"]:
            assert validate_register(reg) == reg

    def test_rejects_invalid(self):
        """Should reject invalid registers."""
        with pytest.raises(HTTPException, match="Invalid register"):
            validate_register("invalid_register")

    def test_case_insensitive(self):
        """Should accept mixed case."""
        assert validate_register("ESSAY") == "essay"


class TestSanitizeTextInput:
    """Test sanitize_text_input function."""

    def test_valid_text(self):
        """Should accept valid text."""
        assert sanitize_text_input("Hello world") == "Hello world"

    def test_rejects_too_long(self):
        """Should reject text over max length."""
        with pytest.raises(HTTPException, match="too long"):
            sanitize_text_input("A" * 50_001)

    def test_removes_null_bytes(self):
        """Should remove null bytes."""
        result = sanitize_text_input("Hello\x00World")
        assert "\x00" not in result


class TestApiKeyGeneration:
    """Test API key generation."""

    def test_generates_key(self):
        """Should generate a valid API key."""
        key = generate_api_key()
        assert key.startswith("vk_")
        assert len(key) > 20

    def test_validates_min_length(self):
        """Should reject short keys."""
        with pytest.raises(ValueError, match="at least 16"):
            rotate_api_key("short")

    def test_validates_max_length(self):
        """Should reject very long keys."""
        with pytest.raises(ValueError, match="too long"):
            rotate_api_key("A" * 300)


class TestSecurityHeaders:
    """Test security headers middleware."""

    def test_security_headers_present(self):
        """Should include security headers in response."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy" in response.headers


class TestAuthEndpoints:
    """Test authentication on protected endpoints."""

    def test_build_requires_auth_when_configured(self, monkeypatch):
        """Should require auth when VOICEKIT_API_KEY is set."""
        monkeypatch.setenv("VOICEKIT_API_KEY", "test-key-1234567890")
        # Need to reimport to pick up new env
        import importlib
        import voicekit.api
        importlib.reload(voicekit.api)
        from voicekit.api import app as reloaded_app
        client = TestClient(reloaded_app)

        response = client.post(
            "/profiles/build",
            data={"author": "Test Author"},
            files={"files": ("test.md", b"content", "text/markdown")},
        )
        # Should get 401 without token
        assert response.status_code == 401

    def test_build_succeeds_with_valid_token(self, monkeypatch):
        """Should succeed with valid bearer token."""
        monkeypatch.setenv("VOICEKIT_API_KEY", "test-key-1234567890")
        import importlib
        import voicekit.api
        importlib.reload(voicekit.api)
        from voicekit.api import app as reloaded_app
        client = TestClient(reloaded_app)

        response = client.post(
            "/profiles/build",
            data={"author": "Test Author"},
            files={"files": ("test.md", b"content", "text/markdown")},
            headers={"Authorization": "Bearer test-key-1234567890"},
        )
        # Should not get 401 (may get 500 due to missing OPENAI_API_KEY)
        assert response.status_code != 401
