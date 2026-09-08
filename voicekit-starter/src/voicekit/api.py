#!/usr/bin/env python3
"""FastAPI server for voicekit-starter.

Provides REST API for voice profile operations with OpenAPI docs,
authentication, and input validation."""

import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from voicekit.core import build_profile, generate, judge, validate_profile
from voicekit.profile_mgmt import list_profiles, merge_profiles, validate_profile_cmd
from voicekit.analysis import compare_profiles, track_evolution
from voicekit.schemas import VOICE_PROFILE_SCHEMA


# ── Security ──────────────────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify the bearer token matches the configured API key."""
    expected = os.environ.get("VOICEKIT_API_KEY")
    if not expected:
        # No key configured — allow local development
        return True
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token",
        )
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Verify API key is configured in production
    if os.environ.get("VOICEKIT_API_KEY") is None:
        print(
            "⚠️  Warning: VOICEKIT_API_KEY not set. API is unauthenticated. "
            "Set it in production to enable bearer-token auth.",
            file=sys.stderr,
        )
    print("VoiceKit API starting up...")
    yield
    print("VoiceKit API shutting down...")


app = FastAPI(
    title="VoiceKit API",
    description="REST API for author voice profile extraction, generation, and judging",
    version="0.3.0",
    lifespan=lifespan,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown", ".json"}


def _safe_filename(filename: str) -> str:
    """Sanitize uploaded filename to prevent path traversal.

    Returns just the basename with null bytes and path separators stripped.
    """
    # Decode URL-encoded characters
    name = unquote(filename)
    # Take only the basename
    name = Path(name).name
    # Strip null bytes
    name = name.replace("\x00", "")
    # Ensure it's not empty or just dots
    name = name.strip(".")
    if not name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return name


def _validate_upload_file(file: UploadFile) -> None:
    """Validate an uploaded file's extension and size."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "voicekit-api"}


@app.get("/schema")
async def get_schema():
    """Get the voice profile JSON schema."""
    return VOICE_PROFILE_SCHEMA


@app.post("/profiles/build", dependencies=[Depends(verify_token)])
async def build_profile_endpoint(
    author: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    model: Optional[str] = Form(None),
):
    """Build a voice profile from uploaded writing samples."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Validate all files first
    for file in files:
        _validate_upload_file(file)

    with tempfile.TemporaryDirectory() as tmpdir:
        file_paths = []
        for file in files:
            safe_name = _safe_filename(file.filename)
            file_path = Path(tmpdir) / safe_name
            content = await file.read()
            # Limit file size (10MB per file)
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"File too large: {file.filename}")
            file_path.write_bytes(content)
            file_paths.append(str(file_path))

        try:
            result = build_profile(
                author=author,
                files=file_paths,
                model=model,
            )
            return {"status": "success", "profile_path": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/drafts/generate", dependencies=[Depends(verify_token)])
async def generate_draft_endpoint(
    profile: UploadFile = File(...),
    task: str = Form(...),
    register: str = Form(...),
    facts: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
):
    """Generate a draft using a voice profile."""
    _validate_upload_file(profile)

    with tempfile.TemporaryDirectory() as tmpdir:
        safe_name = _safe_filename(profile.filename)
        profile_path = Path(tmpdir) / safe_name
        content = await profile.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Profile file too large")
        profile_path.write_bytes(content)

        task_path = Path(tmpdir) / "task.md"
        task_path.write_text(task)

        facts_path = None
        if facts:
            facts_path = Path(tmpdir) / "facts.txt"
            facts_path.write_text(facts)

        try:
            draft_text, out_path = generate(
                profile_path=str(profile_path),
                task_file=str(task_path),
                facts_file=str(facts_path) if facts_path else None,
                register=register,
                model=model,
            )
            return {"status": "success", "draft": draft_text}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/drafts/judge", dependencies=[Depends(verify_token)])
async def judge_draft_endpoint(
    profile: UploadFile = File(...),
    draft: str = Form(...),
    register: str = Form(...),
    model: Optional[str] = Form(None),
):
    """Judge a draft against a voice profile."""
    _validate_upload_file(profile)

    with tempfile.TemporaryDirectory() as tmpdir:
        safe_name = _safe_filename(profile.filename)
        profile_path = Path(tmpdir) / safe_name
        content = await profile.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Profile file too large")
        profile_path.write_bytes(content)

        draft_path = Path(tmpdir) / "draft.md"
        draft_path.write_text(draft)

        try:
            evaluation, out_path = judge(
                profile_path=str(profile_path),
                draft_file=str(draft_path),
                register=register,
                model=model,
            )
            return {"status": "success", "evaluation": evaluation}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/profiles/list", dependencies=[Depends(verify_token)])
async def list_profiles_endpoint(directory: str):
    """List and validate all profiles in a directory."""
    try:
        profiles = list_profiles(directory)
        return {"status": "success", "profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/profiles/compare", dependencies=[Depends(verify_token)])
async def compare_profiles_endpoint(
    profile_a: UploadFile = File(...),
    profile_b: UploadFile = File(...),
):
    """Compare two voice profiles."""
    _validate_upload_file(profile_a)
    _validate_upload_file(profile_b)

    with tempfile.TemporaryDirectory() as tmpdir:
        safe_a = _safe_filename(profile_a.filename)
        safe_b = _safe_filename(profile_b.filename)
        path_a = Path(tmpdir) / safe_a
        path_b = Path(tmpdir) / safe_b
        path_a.write_bytes(await profile_a.read())
        path_b.write_bytes(await profile_b.read())

        try:
            result = compare_profiles(str(path_a), str(path_b))
            return {"status": "success", "comparison": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/profiles/validate", dependencies=[Depends(verify_token)])
async def validate_profile_endpoint(profile: UploadFile = File(...)):
    """Validate a voice profile against the schema."""
    _validate_upload_file(profile)

    with tempfile.TemporaryDirectory() as tmpdir:
        safe_name = _safe_filename(profile.filename)
        path = Path(tmpdir) / safe_name
        path.write_bytes(await profile.read())

        try:
            report = validate_profile_cmd(str(path))
            return {"status": "success", "validation": report}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


def start_server(host: str = "0.0.0.0", port: int = 8000):
    """Start the API server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
