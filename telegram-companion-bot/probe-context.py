#!/usr/bin/env python3
"""probe-context.py - measure the context window a NanoGPT model is actually SERVED at.

Why this exists: NanoGPT's /v1/models listing returns no context-length field (checked
2026-09-04), and a base model's native window is not what a provider necessarily serves.
Qwen2.5-72B, for instance, is 32,768 native and rope-scales to 131,072 - which of those
you get is the provider's choice, and magnum-v4-72b is reported at both numbers by
different aggregators. Guessing that number wrong sets FALLBACK_CONTEXT_BUDGET wrong,
which either wastes context or ships a prompt the model rejects.

So this measures instead of asking: send filler of a known size, see whether the model
takes it, binary-search the boundary.

    export NANOGPT_API_KEY=...                      # or pass --env <instance-dir>
    python3 probe-context.py Sao10K/L3.3-70B-Euryale-v2.3
    python3 probe-context.py --env /opt/telegram-bots/jules anthracite-org/magnum-v4-72b

Costs a handful of cheap calls per model (max_tokens=16, and a rejected call bills
nothing). Sizes are approximate tokens at the chars/4 estimate bot.py itself uses
(_est_tokens), so the answer is directly comparable to CONTEXT_TOKEN_BUDGET and
FALLBACK_CONTEXT_BUDGET, which are denominated in those same units.

Reports UNKNOWN rather than a number when the failure is not clearly a context
rejection - an auth error, a rate limit, or a model that is simply down says nothing
about the window, and reporting it as a window would be a confident wrong answer.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://nano-gpt.com/api/v1/chat/completions"

# Substrings that mark a refusal as being about prompt SIZE. Anything else is a
# different failure and leaves the window undetermined.
CONTEXT_MARKERS = (
    "context length", "context_length", "context window", "maximum context",
    "too many tokens", "reduce the length", "maximum_tokens", "prompt is too long",
    "exceeds", "token limit",
)


def load_key(env_dir):
    """Key from --env <instance-dir>/.env, else NANOGPT_API_KEY."""
    if env_dir:
        path = os.path.join(env_dir, ".env")
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("NANOGPT_API_KEY="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except OSError as e:
            sys.exit(f"cannot read {path}: {e}")
        sys.exit(f"no NANOGPT_API_KEY in {path}")
    key = os.getenv("NANOGPT_API_KEY")
    if not key:
        sys.exit("set NANOGPT_API_KEY, or pass --env <instance-dir>")
    return key


def attempt(model, approx_tokens, key, timeout):
    """Send a prompt of ~approx_tokens. Returns (accepted, detail).

    accepted is True (model took it), False (model refused it for SIZE), or None
    (something else went wrong - the window stays unknown).
    """
    # chars/4 is bot.py's own estimator, so the number this prints lines up with the
    # budget vars. A single repeated token would compress oddly; varied words track
    # the estimate far more closely.
    filler = ("the quick brown fox jumps over the lazy dog " * (approx_tokens // 2))[:approx_tokens * 4]
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": filler + "\n\nReply with the word OK."}],
        "max_tokens": 16,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            json.load(r)
            return True, "accepted"
    except urllib.error.HTTPError as e:
        try:
            payload = e.read().decode("utf-8", "replace")
        except Exception:
            payload = ""
        low = payload.lower()
        if e.code in (400, 413) and any(m in low for m in CONTEXT_MARKERS):
            return False, f"HTTP {e.code}: size rejected"
        return None, f"HTTP {e.code}: {payload[:180].strip()}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def probe(model, key, lo, hi, timeout):
    print(f"\n=== {model} ===")

    ok, detail = attempt(model, lo, key, timeout)
    if ok is None:
        print(f"  UNKNOWN - probe at ~{lo} tok failed for a non-size reason: {detail}")
        return None
    if ok is False:
        print(f"  served window is under ~{lo} tok (floor probe was rejected)")
        return 0
    print(f"  ~{lo:>7} tok  accepted")

    ok, detail = attempt(model, hi, key, timeout)
    if ok is True:
        print(f"  ~{hi:>7} tok  accepted  -> at least {hi}, ceiling not found")
        return hi
    if ok is None:
        print(f"  UNKNOWN - ceiling probe failed for a non-size reason: {detail}")
        return None
    print(f"  ~{hi:>7} tok  rejected")

    # Invariant: lo accepted, hi rejected. Narrow to 5%.
    while hi - lo > max(1024, lo // 20):
        mid = (lo + hi) // 2
        ok, detail = attempt(model, mid, key, timeout)
        if ok is None:
            print(f"  stopped at ~{mid} tok: {detail}")
            break
        print(f"  ~{mid:>7} tok  {'accepted' if ok else 'rejected'}")
        if ok:
            lo = mid
        else:
            hi = mid
    print(f"  --> served context is between ~{lo} and ~{hi} tok")
    return lo


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("models", nargs="+", help="model ids to probe")
    p.add_argument("--env", metavar="DIR", help="instance dir to read .env from")
    p.add_argument("--lo", type=int, default=8000, help="floor probe (default 8000)")
    p.add_argument("--hi", type=int, default=140000, help="ceiling probe (default 140000)")
    p.add_argument("--timeout", type=int, default=180)
    a = p.parse_args()

    key = load_key(a.env)
    results = {}
    for m in a.models:
        results[m] = probe(m, key, a.lo, a.hi, a.timeout)

    print("\n=== summary ===")
    for m, v in results.items():
        if v is None:
            print(f"  {m:52} UNKNOWN")
        elif v == 0:
            print(f"  {m:52} under ~{a.lo}")
        else:
            print(f"  {m:52} >= ~{v} tok   "
                  f"(FALLBACK_CONTEXT_BUDGET ~{max(0, v - 4096)})")
    print("\nBudget suggestion subtracts MAX_TOKENS=4096 for the reply, matching the\n"
          "rule in .env.example. Lower it if that instance sets MAX_TOKENS higher.")


if __name__ == "__main__":
    main()
