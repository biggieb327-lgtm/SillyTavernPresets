#!/usr/bin/env python3
"""FastAPI server for voicekit-starter."""

import json
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from voicekit.core import build_profile, generate, judge, validate_profile
from voicekit.profile_mgmt import list_profiles, merge_profiles, validate_profile_cmd
from voicekit.analysis import compare_profiles, track_evolution
from voicekit.schemas import VOICE_PROFILE_SCHEMA


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print("VoiceKit API starting up...")
    yield
    print("VoiceKit API shutting down...")


app = FastAPI(
    title="VoiceKit API",
    description="REST API for author voice profile extraction, generation, and judging",
    version="0.3.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "voicekit-api"}


@app.get("/schema")
async def get_schema():
    """Get the voice profile JSON schema."""
    return VOICE_PROFILE_SCHEMA


@app.post("/profiles/build")
async def build_profile_endpoint(
    author: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    model: Optional[str] = Form(None),
):
    """Build a voice profile from uploaded writing samples."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Save uploaded files to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        file_paths = []
        for file in files:
            file_path = Path(tmpdir) / file.filename
            content = await file.read()
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


@app.post("/drafts/generate")
async def generate_draft_endpoint(
    profile: UploadFile = File(...),
    task: str = Form(...),
    register: str = Form(...),
    facts: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
):
    """Generate a draft using a voice profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        profile_path = Path(tmpdir) / profile.filename
        content = await profile.read()
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


@app.post("/drafts/judge")
async def judge_draft_endpoint(
    profile: UploadFile = File(...),
    draft: str = Form(...),
    register: str = Form(...),
    model: Optional[str] = Form(None),
):
    """Judge a draft against a voice profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        profile_path = Path(tmpdir) / profile.filename
        content = await profile.read()
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


@app.get("/profiles/list")
async def list_profiles_endpoint(directory: str):
    """List and validate all profiles in a directory."""
    try:
        profiles = list_profiles(directory)
        return {"status": "success", "profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/profiles/compare")
async def compare_profiles_endpoint(
    profile_a: UploadFile = File(...),
    profile_b: UploadFile = File(...),
):
    """Compare two voice profiles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = Path(tmpdir) / profile_a.filename
        path_b = Path(tmpdir) / profile_b.filename
        path_a.write_bytes(await profile_a.read())
        path_b.write_bytes(await profile_b.read())

        try:
            result = compare_profiles(str(path_a), str(path_b))
            return {"status": "success", "comparison": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/profiles/validate")
async def validate_profile_endpoint(profile: UploadFile = File(...)):
    """Validate a voice profile against the schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / profile.filename
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
