"""The LLM boundary: a tiny protocol, a deterministic MockLLM, and a stdlib
OpenAI-compatible client.

The whole loop talks to models only through `LLM.chat`. That lets the exact same
orchestrator run offline against `MockLLM` (deterministic, no network — used by
the tests and the demo) or against any OpenAI-compatible endpoint such as
NanoGPT (the endpoint this repo already uses).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Callable, Protocol, runtime_checkable

Message = dict  # {"role": "system"|"user"|"assistant", "content": str}


@runtime_checkable
class LLM(Protocol):
    def chat(self, messages: list[Message], **kwargs) -> str: ...


class MockLLM:
    """Deterministic model. `responder(messages) -> str` is the brain.

    Records every call in `.calls` so tests can assert on what each agent asked.
    """

    def __init__(self, responder: Callable[[list[Message]], str]):
        self._responder = responder
        self.calls: list[list[Message]] = []

    def chat(self, messages: list[Message], **kwargs) -> str:
        self.calls.append(messages)
        return self._responder(messages)


def scripted(responses: list[str]) -> Callable[[list[Message]], str]:
    """A responder that returns queued strings in order (then repeats the last)."""
    box = {"i": 0}

    def _r(_messages: list[Message]) -> str:
        i = box["i"]
        box["i"] = min(i + 1, len(responses) - 1)
        return responses[i]

    return _r


class OpenAICompatLLM:
    """Minimal OpenAI-compatible /chat/completions client using only urllib."""

    def __init__(
        self,
        model: str,
        base_url: str = "https://nano-gpt.com/api/v1",
        api_key: str | None = None,
        timeout: float = 120.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("SKILLFORGE_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )
        self.timeout = timeout

    def chat(self, messages: list[Message], **kwargs) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.0),
        }
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:  # pragma: no cover - network
            raise RuntimeError(f"LLM HTTP {e.code}: {e.read().decode()[:500]}") from e
        return body["choices"][0]["message"]["content"]


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str):
    """Pull the first JSON object/array out of a model reply.

    Tolerates ```json fences and leading prose. Raises ValueError if none parses.
    """
    candidates: list[str] = []
    for m in _FENCE_RE.finditer(text or ""):
        candidates.append(m.group(1).strip())
    candidates.append(text or "")
    for cand in candidates:
        for opener, closer in (("{", "}"), ("[", "]")):
            start = cand.find(opener)
            end = cand.rfind(closer)
            if start != -1 and end != -1 and end > start:
                blob = cand[start : end + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    continue
    raise ValueError("no parseable JSON found in model reply")
