#!/usr/bin/env python3
"""Security middleware and utilities for voicekit API."""

import hashlib
import hmac
import os
import time
from collections import defaultdict
from functools import wraps
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


# ── Rate Limiting ─────────────────────────────────────────────────────────────

class RateLimiter:
    """Simple in-memory rate limiter using sliding window."""

    def __init__(self, requests_per_minute: int = 60, burst: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst = burst
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed under rate limit."""
        now = time.monotonic()
        window_start = now - 60.0

        # Clean old entries
        self._requests[client_id] = [
            t for t in self._requests[client_id] if t > window_start
        ]

        # Check burst (per-minute rate)
        if len(self._requests[client_id]) >= self.requests_per_minute:
            return False

        # Check burst
        if len(self._requests[client_id]) >= self.burst:
            return False

        self._requests[client_id].append(now)
        return True

    def get_retry_after(self, client_id: str) -> int:
        """Get seconds until next request is allowed."""
        if not self._requests[client_id]:
            return 0
        oldest = min(self._requests[client_id])
        return max(0, int(60 - (time.monotonic() - oldest)))


# Global rate limiter instance
rate_limiter = RateLimiter(
    requests_per_minute=int(os.environ.get("VOICEKIT_RATE_LIMIT", "60")),
    burst=10,
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting to all requests."""

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting if no API key is configured (e.g., tests)
        if not os.environ.get("VOICEKIT_API_KEY"):
            return await call_next(request)

        # Get client identifier
        client_id = _get_client_id(request)

        if not rate_limiter.is_allowed(client_id):
            retry_after = rate_limiter.get_retry_after(client_id)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded", "retry_after": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        return response


# ── Security Headers ──────────────────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy (for any HTML)
        response.headers["Content-Security-Policy"] = "default-src 'none'"

        # Remove server header
        if "server" in response.headers:
            del response.headers["server"]

        return response


# ── Request Validation ────────────────────────────────────────────────────────

def _get_client_id(request: Request) -> str:
    """Get a unique client identifier from the request."""
    # Use X-Forwarded-For if behind a proxy, else direct IP
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def validate_author_name(author: str) -> str:
    """Validate and sanitize author name."""
    if not author or not author.strip():
        raise HTTPException(status_code=400, detail="Author name is required")

    author = author.strip()

    if len(author) > 200:
        raise HTTPException(status_code=400, detail="Author name too long (max 200 chars)")

    # Remove control characters
    author = "".join(c for c in author if ord(c) >= 32 or c in "\t\n\r")

    return author


def validate_register(register: str) -> str:
    """Validate register name."""
    if not register or not register.strip():
        raise HTTPException(status_code=400, detail="Register is required")

    register = register.strip().lower()

    allowed = {"essay", "email", "dialogue", "sales", "formal", "casual", "creative", "technical"}
    if register not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid register '{register}'. Allowed: {', '.join(sorted(allowed))}",
        )

    return register


# ── API Key Rotation ─────────────────────────────────────────────────────────

def rotate_api_key(new_key: str) -> None:
    """Validate a new API key meets minimum requirements."""
    if len(new_key) < 16:
        raise ValueError("API key must be at least 16 characters")
    if len(new_key) > 256:
        raise ValueError("API key too long (max 256 chars)")


def generate_api_key() -> str:
    """Generate a secure random API key."""
    import secrets
    return "vk_" + secrets.token_urlsafe(32)


# ── Audit Logging ─────────────────────────────────────────────────────────────

def log_security_event(event_type: str, details: dict) -> None:
    """Log security-relevant events."""
    import logging
    logger = logging.getLogger("voicekit.security")
    logger.warning(f"Security event: {event_type} - {details}")


# ── Input Sanitization ───────────────────────────────────────────────────────

def sanitize_text_input(text: str, max_length: int = 50_000) -> str:
    """Sanitize text input for LLM processing."""
    if not text:
        return ""

    if len(text) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"Text too long ({len(text):,} chars). Maximum: {max_length:,} chars",
        )

    # Remove null bytes
    text = text.replace("\x00", "")

    return text


def validate_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC signature for webhook payloads."""
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
