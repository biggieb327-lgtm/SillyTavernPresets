"""Reusable runtime logic for voicekit commands."""

from __future__ import annotations

import json
import os
from pathlib import Path

import jsonschema
from openai import OpenAI

from voicekit.prompts import (
    GENERATOR_SYSTEM,
    GENERATOR_USER,
    JUDGE_SYSTEM,
    JUDGE_USER,
    PROFILE_BUILDER_SYSTEM,
    PROFILE_BUILDER_USER,
    PROFILE_REPAIR_ADDENDUM,
)
from voicekit.schemas import VOICE_PROFILE_SCHEMA

ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown"}


def get_model(override: str | None = None) -> str:
    if override:
        return override
    return os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key)


def collect_samples(files: list[str] | None, samples_dir: str | None) -> list[Path]:
    """Collect and de-duplicate sample file paths."""
    paths: set[Path] = set()
    if files:
        for f in files:
            p = Path(f).resolve()
            if p.suffix.lower() in ALLOWED_EXTENSIONS and p.is_file():
                paths.add(p)
    if samples_dir:
        d = Path(samples_dir).resolve()
        if d.is_dir():
            for p in d.iterdir():
                if p.suffix.lower() in ALLOWED_EXTENSIONS and p.is_file():
                    paths.add(p)
    if not paths:
        raise ValueError("No valid sample files found (.txt, .md, .markdown)")
    return sorted(paths)


def build_corpus_text(paths: list[Path]) -> tuple[str, int, list[dict]]:
    """Read files and build a labeled corpus string."""
    sections = []
    sources = []
    total_words = 0
    for p in paths:
        content = p.read_text(encoding="utf-8")
        word_count = len(content.split())
        total_words += word_count
        label = p.stem
        sources.append({"label": label, "word_count": word_count})
        sections.append(f"--- [{label}] ({word_count} words) ---\n{content}")
    corpus_text = "\n\n".join(sections)
    return corpus_text, total_words, sources


def load_template() -> dict:
    """Load the bundled voice profile template."""
    template_path = Path(__file__).parent.parent.parent / "templates" / "voice_profile_template.json"
    return json.loads(template_path.read_text(encoding="utf-8"))


def validate_profile(profile: dict) -> None:
    """Validate a profile dict against the schema. Raises on failure."""
    jsonschema.validate(instance=profile, schema=VOICE_PROFILE_SCHEMA)


def call_llm(client: OpenAI, model: str, system: str, user: str) -> str:
    """Single LLM call returning the assistant message content."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("LLM returned empty response")
    return content.strip()


def build_profile(
    author: str,
    files: list[str] | None,
    samples_dir: str | None,
    out: str,
    project_name: str | None = None,
    source_type: str | None = None,
    use_cases: str | None = None,
    retries: int = 2,
    model: str | None = None,
) -> Path:
    """Extract a voice profile from a writing corpus."""
    client = get_client()
    resolved_model = get_model(model)
    paths = collect_samples(files, samples_dir)
    corpus_text, total_words, sources = build_corpus_text(paths)
    template = load_template()
    template_json = json.dumps(template, indent=2)

    meta_parts = []
    if project_name:
        meta_parts.append(f"Project: {project_name}")
    if source_type:
        meta_parts.append(f"Source type: {source_type}")
    if use_cases:
        meta_parts.append(f"Use cases: {use_cases}")
    meta_block = "\n".join(meta_parts)

    user_prompt = PROFILE_BUILDER_USER.format(
        author=author,
        meta_block=meta_block,
        file_count=len(paths),
        total_words=total_words,
        corpus_text=corpus_text,
        template_json=template_json,
    )

    last_error = None
    for attempt in range(1, retries + 1):
        prompt = user_prompt
        if last_error:
            prompt += PROFILE_REPAIR_ADDENDUM.format(error=last_error)

        raw = call_llm(client, resolved_model, PROFILE_BUILDER_SYSTEM, prompt)

        # Strip markdown fences if the model wraps anyway
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        try:
            profile = json.loads(raw)
        except json.JSONDecodeError as e:
            last_error = f"Invalid JSON: {e}"
            if attempt == retries:
                raise RuntimeError(f"Failed to get valid JSON after {retries} attempts: {last_error}")
            continue

        try:
            validate_profile(profile)
        except jsonschema.ValidationError as e:
            last_error = f"{e.message} (path: {list(e.absolute_path)})"
            if attempt == retries:
                raise RuntimeError(f"Schema validation failed after {retries} attempts: {last_error}")
            continue

        # Success
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
        return out_path

    raise RuntimeError("Unreachable: retry loop exited without return or raise")


def generate(
    profile_path: str,
    task_file: str,
    facts_file: str,
    register: str,
    out: str,
    model: str | None = None,
) -> Path:
    """Generate a draft using a voice profile."""
    client = get_client()
    resolved_model = get_model(model)

    profile_json = Path(profile_path).read_text(encoding="utf-8")
    task_text = Path(task_file).read_text(encoding="utf-8")
    facts_text = Path(facts_file).read_text(encoding="utf-8")

    user_prompt = GENERATOR_USER.format(
        profile_json=profile_json,
        register=register,
        task_text=task_text,
        facts_text=facts_text,
    )

    result = call_llm(client, resolved_model, GENERATOR_SYSTEM, user_prompt)

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result, encoding="utf-8")
    return out_path


def judge(
    profile_path: str,
    draft_file: str,
    register: str,
    out: str,
    model: str | None = None,
) -> Path:
    """Judge a draft against a voice profile."""
    client = get_client()
    resolved_model = get_model(model)

    profile_json = Path(profile_path).read_text(encoding="utf-8")
    draft_text = Path(draft_file).read_text(encoding="utf-8")

    user_prompt = JUDGE_USER.format(
        profile_json=profile_json,
        register=register,
        draft_text=draft_text,
    )

    result = call_llm(client, resolved_model, JUDGE_SYSTEM, user_prompt)

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result, encoding="utf-8")
    return out_path
