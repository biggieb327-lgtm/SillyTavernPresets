"""Reusable runtime logic for voicekit commands."""

from __future__ import annotations

import importlib.resources
import json
import os
import re
import sys
import warnings
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
CORPUS_CHAR_WARNING_THRESHOLD = 100_000


def get_model(override: str | None = None) -> str:
    if override:
        return override
    return os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Set it and re-run:\n"
            '  export OPENAI_API_KEY="sk-..."\n'
            "For local OpenAI-compatible servers (ollama, vLLM, LM Studio), also set:\n"
            '  export OPENAI_BASE_URL="http://localhost:11434/v1"'
        )
    base_url = os.environ.get("OPENAI_BASE_URL")
    return OpenAI(api_key=api_key, base_url=base_url)


def slugify(name: str) -> str:
    """Turn an author name into a safe filename fragment."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "author"


def _collect_from_dir(d: Path, paths: set[Path]) -> int:
    """Add supported files from a directory; return how many were found."""
    found = 0
    for p in sorted(d.iterdir()):
        if p.suffix.lower() in ALLOWED_EXTENSIONS and p.is_file():
            paths.add(p)
            found += 1
    return found


def collect_samples(files: list[str] | None, samples_dir: str | None) -> list[Path]:
    """Collect and de-duplicate sample file paths, reporting skipped files.

    Entries in ``files`` may be individual files or directories; directories
    are expanded to their supported files.
    """
    paths: set[Path] = set()
    skipped: list[str] = []
    if files:
        for f in files:
            p = Path(f).resolve()
            if not p.exists():
                skipped.append(f"{f} (not found)")
            elif p.is_dir():
                if _collect_from_dir(p, paths) == 0:
                    skipped.append(f"{f} (directory contains no .txt, .md, or .markdown files)")
            elif not p.is_file():
                skipped.append(f"{f} (not a regular file)")
            elif p.suffix.lower() not in ALLOWED_EXTENSIONS:
                skipped.append(f"{f} (unsupported extension '{p.suffix}'; use .txt, .md, .markdown)")
            else:
                paths.add(p)
    if samples_dir:
        d = Path(samples_dir).resolve()
        if not d.is_dir():
            raise ValueError(f"--samples-dir {samples_dir!r} is not a directory")
        _collect_from_dir(d, paths)
    if skipped:
        print(f"Skipped {len(skipped)} file(s):", file=sys.stderr)
        for reason in skipped:
            print(f"  - {reason}", file=sys.stderr)
    if not paths:
        raise ValueError("No valid sample files found (.txt, .md, .markdown)")
    return sorted(paths)


def build_corpus_text(paths: list[Path]) -> tuple[str, int, list[dict]]:
    """Read files and build a labeled corpus string. Warns if corpus is very large."""
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
    if len(corpus_text) > CORPUS_CHAR_WARNING_THRESHOLD:
        approx_tokens = len(corpus_text) // 4
        warnings.warn(
            f"Corpus is ~{approx_tokens:,} tokens ({len(corpus_text):,} chars). "
            f"This may exceed model context limits and cause API errors or truncation.",
            stacklevel=2,
        )
    return corpus_text, total_words, sources


def load_template() -> dict:
    """Load the bundled voice profile template using importlib.resources."""
    ref = importlib.resources.files("voicekit").joinpath("templates/voice_profile_template.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def validate_profile(profile: dict) -> None:
    """Validate a profile dict against the schema. Raises on failure."""
    jsonschema.validate(instance=profile, schema=VOICE_PROFILE_SCHEMA)


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences wrapping JSON output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    return text


def call_llm(
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    json_mode: bool = False,
) -> str:
    """Single LLM call returning the assistant message content."""
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("LLM returned empty response")
    return content.strip()


def build_profile(
    author: str,
    files: list[str] | None,
    samples_dir: str | None,
    out: str | None = None,
    project_name: str | None = None,
    source_type: str | None = None,
    use_cases: str | None = None,
    retries: int = 2,
    model: str | None = None,
) -> Path:
    """Extract a voice profile from a writing corpus."""
    paths = collect_samples(files, samples_dir)
    corpus_text, total_words, sources = build_corpus_text(paths)
    client = get_client()
    resolved_model = get_model(model)
    print(
        f"Read {len(paths)} sample file(s), {total_words:,} words total.",
        file=sys.stderr,
    )
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

        print(
            f"Extracting voice profile with {resolved_model} (attempt {attempt}/{retries})...",
            file=sys.stderr,
        )
        raw = call_llm(client, resolved_model, PROFILE_BUILDER_SYSTEM, prompt, json_mode=True)
        raw = strip_markdown_fences(raw)

        try:
            profile = json.loads(raw)
        except json.JSONDecodeError as e:
            last_error = f"Invalid JSON: {e}"
            if attempt == retries:
                raise RuntimeError(f"Failed to get valid JSON after {retries} attempts: {last_error}")
            print("Output was not valid JSON; retrying with repair guidance.", file=sys.stderr)
            continue

        try:
            validate_profile(profile)
        except jsonschema.ValidationError as e:
            last_error = f"{e.message} (path: {list(e.absolute_path)})"
            if attempt == retries:
                raise RuntimeError(f"Schema validation failed after {retries} attempts: {last_error}")
            print("Output failed schema validation; retrying with repair guidance.", file=sys.stderr)
            continue

        # Success
        out_path = Path(out) if out else Path(f"{slugify(author)}-profile.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
        return out_path

    raise RuntimeError("Unreachable: retry loop exited without return or raise")


def generate(
    profile_path: str,
    task_file: str,
    facts_file: str | None,
    register: str,
    out: str | None = None,
    model: str | None = None,
) -> tuple[str, Path | None]:
    """Generate a draft using a voice profile.

    Returns the draft text and the path it was written to (None when no
    output path was given — the caller decides how to present the text).
    """
    profile_json = Path(profile_path).read_text(encoding="utf-8")
    task_text = Path(task_file).read_text(encoding="utf-8")
    if facts_file:
        facts_text = Path(facts_file).read_text(encoding="utf-8")
    else:
        facts_text = "(no separate facts file; use only facts stated in the task/brief)"
    client = get_client()
    resolved_model = get_model(model)

    user_prompt = GENERATOR_USER.format(
        profile_json=profile_json,
        register=register,
        task_text=task_text,
        facts_text=facts_text,
    )

    print(f"Generating {register} draft with {resolved_model}...", file=sys.stderr)
    result = call_llm(client, resolved_model, GENERATOR_SYSTEM, user_prompt)

    if not out:
        return result, None
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result, encoding="utf-8")
    return result, out_path


def judge(
    profile_path: str,
    draft_file: str,
    register: str,
    out: str | None = None,
    model: str | None = None,
) -> tuple[dict | None, Path]:
    """Judge a draft against a voice profile.

    Returns the parsed evaluation (None if the model returned unparseable
    JSON) and the path the evaluation was written to. Defaults the output
    path to ``<draft-stem>-eval.json`` next to the draft.
    """
    draft_path = Path(draft_file)
    profile_json = Path(profile_path).read_text(encoding="utf-8")
    draft_text = draft_path.read_text(encoding="utf-8")
    client = get_client()
    resolved_model = get_model(model)

    user_prompt = JUDGE_USER.format(
        profile_json=profile_json,
        register=register,
        draft_text=draft_text,
    )

    print(f"Judging draft with {resolved_model}...", file=sys.stderr)
    raw = call_llm(client, resolved_model, JUDGE_SYSTEM, user_prompt, json_mode=True)
    raw = strip_markdown_fences(raw)

    # Validate that judge output is parseable JSON before saving
    parsed: dict | None = None
    try:
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            parsed = loaded
        result = json.dumps(loaded, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        # Save raw output but warn the user
        result = raw
        print("Warning: judge output is not valid JSON; saving raw response.", file=sys.stderr)

    out_path = Path(out) if out else draft_path.with_name(f"{draft_path.stem}-eval.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result, encoding="utf-8")
    return parsed, out_path
