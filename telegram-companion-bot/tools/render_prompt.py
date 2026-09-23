#!/usr/bin/env python3
"""Render the full prompt an instance sends, offline, and diff it across a change (ROADMAP 2.8).

Why this exists: `preset.txt` changes all seven bots, and a card or preset-layer edit changes
the prompt in ways nobody can see from the diff. The Jules speaker-label incident (operational
log 2026-07-20) came from how bot.py assembled the prompt, not from the card. `test_pure.py`
checks `assemble_messages` one piece at a time; this shows the whole message list.

    python3 tools/render_prompt.py nora                 # one instance
    python3 tools/render_prompt.py --all                # all seven
    python3 tools/render_prompt.py --all --diff HEAD~1  # render at a ref and at the working tree, print the diff
    python3 tools/render_prompt.py priya --conversation my-chat.json
    python3 tools/render_prompt.py --all --check        # what the prompt-render eval runs

Offline by construction (CLAUDE.md Working principle #10): the child process gets a
placeholder API key, `query_vec=None`, and every socket connect raises. A render that tries
to reach the network fails loudly instead of spending NanoGPT tokens.

Deterministic: the clock is fixed at FIXED_NOW, `random` is seeded, and the child runs with
TZ=UTC and PYTHONHASHSEED=0, so two renders of the same tree are byte-identical and a
`--diff` shows only what the change did.

What it CANNOT know: each live instance's `.env` is on the VPS, not in the repo. PRESET_FILES
comes from the recommended stacks documented in `.env.example` (the INSTANCES table below),
and every other variable is its bot.py default. `--env KEY=VALUE` overrides one. The header of
every render says this. If a live instance disagrees, the live instance is authoritative.

Needs the packages in requirements.lock (it imports bot.py), the same as pytest.

Repo-only: nothing here deploys, and `vps-sync.sh` does not copy tools/.
"""
import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parent.parent
REPO = BOT_DIR.parent

# instance -> (card file, PRESET_FILES). The stacks are `.env.example`'s "Recommended
# stacks" table; update both together when an instance's live PRESET_FILES changes.
_SCENE = ["preset-core.txt", "preset-rp.txt", "preset-explicit.txt", "preset-stepped.txt"]
INSTANCES = {
    "nora": ("nora.json", _SCENE + ["preset-nora.txt"]),
    "bonnie": ("bonnie.json", _SCENE + ["preset-bonnie.txt"]),
    "cass": ("cass.json", ["preset-core.txt", "preset-stepped.txt", "preset-cass.txt"]),
    "emily": ("emily_harper.json", _SCENE + ["preset-emily.txt"]),
    "priya": ("priya.json", ["preset-core.txt", "preset-stepped.txt", "preset-priya.txt"]),
    "jules": ("jules_nakagawa.json", _SCENE + ["preset-jules.txt"]),
    "marcus": ("marcus_calder.json", _SCENE + ["preset-marcus.txt"]),
}

# A Tuesday evening, so schedule, time-of-day and weekday blocks all render.
FIXED_NOW = "2026-09-22T19:30:00-07:00"
CHAT_ID = 1

# Used when --conversation is not given. `ago_minutes` is relative to FIXED_NOW.
DEFAULT_CONVERSATION = {
    "user_name": "Sam",
    "history": [
        {"role": "user", "content": "morning! how'd you sleep", "ago_minutes": 600},
        {"role": "assistant", "content": "badly lol. you?", "ago_minutes": 598},
        {"role": "user", "content": "same. long day at work, my boss moved the deadline up",
         "ago_minutes": 45},
        {"role": "assistant", "content": "ugh. to when?", "ago_minutes": 44},
    ],
    "latest": "friday. anyway what are you up to tonight",
}


# --- child: runs inside the temp instance dir, imports bot.py, writes the render ----------

def _block_network() -> None:
    """Make every socket connect in this process raise. Nothing in assemble_messages
    connects today; this makes sure a future block that does fails loudly here instead of
    spending NanoGPT tokens or hanging on a timeout."""
    import socket

    def _offline(*a, **k):
        raise RuntimeError("render_prompt is offline: something tried to open a network "
                           "connection while assembling the prompt")
    socket.socket.connect = _offline
    socket.socket.connect_ex = _offline
    socket.create_connection = _offline


def _child(src: str, inst_dir: str, conv_path: str, out_json: str) -> None:
    import random
    import time
    from datetime import datetime, date

    _block_network()
    fixed = datetime.fromisoformat(FIXED_NOW)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(fixed.timestamp(), tz)

        @classmethod
        def today(cls):
            return cls.now()

    class _FixedDate(date):
        @classmethod
        def today(cls):
            d = fixed.astimezone().date()
            return cls(d.year, d.month, d.day)

    time.time = lambda: fixed.timestamp()
    random.seed(0)

    sys.argv = [sys.argv[0], inst_dir]
    os.environ["BOT_HOME"] = inst_dir
    sys.path.insert(0, src)
    import bot  # noqa: E402 — must follow the argv/env setup above

    bot.datetime = _FixedDatetime
    bot.date = _FixedDate
    random.seed(0)

    conv = json.loads(Path(conv_path).read_text())
    now = fixed.timestamp()
    bot.user_names[CHAT_ID] = conv.get("user_name", "Sam")
    bot.conversation_history[CHAT_ID] = [
        {"role": m["role"], "content": m["content"],
         "ts": now - 60 * float(m.get("ago_minutes", 0))}
        for m in conv.get("history", [])
    ]
    messages = bot.assemble_messages(CHAT_ID, conv["latest"], query_vec=None)
    Path(out_json).write_text(json.dumps({
        "name": bot.NAME,
        "preset_layers": [name for name, _ in bot.PRESET_LAYERS],
        "preset_texts": [bot.fill(text, bot.NAME, bot.user_names[CHAT_ID])
                         for _, text in bot.PRESET_LAYERS],
        "post_history": bot.fill(bot.POST_HISTORY_RAW, bot.NAME, bot.user_names[CHAT_ID])
                        if bot.POST_HISTORY_RAW else "",
        "messages": messages,
    }, ensure_ascii=False, indent=1))


# --- parent ------------------------------------------------------------------------------

def _build_instance(src: Path, instance: str, overrides: list[str]) -> Path:
    """A throwaway instance dir from the tree at `src`: card, context files, preset layers,
    and a .env with placeholder keys. Returns the dir, or raises FileNotFoundError."""
    card, layers = INSTANCES[instance]
    seed_dir = src / instance
    if not (src / card).is_file() or not seed_dir.is_dir():
        raise FileNotFoundError(f"{card} or {instance}/ is not in this tree")
    d = Path(tempfile.mkdtemp(prefix=f"render_{instance}_"))
    for f in seed_dir.iterdir():
        if f.is_file():
            shutil.copy(f, d / f.name)
    shutil.copy(src / card, d / card)
    for name in ["preset.txt"] + layers:
        if (src / name).is_file():
            shutil.copy(src / name, d / name)
    env = [
        "TELEGRAM_BOT_TOKEN=0:render-offline-not-a-token",
        "NANOGPT_API_KEY=render-offline-not-a-key",
        f"CHARACTER_CARD={card}",
        f"PRESET_FILES={','.join(layers)}",
    ] + overrides
    (d / ".env").write_text("\n".join(env) + "\n")
    return d


def _render(src: Path, instance: str, conv_path: Path, overrides: list[str],
            label: str) -> tuple[dict | None, str]:
    """Render one instance from the tree at `src`. Returns (result, error)."""
    try:
        inst_dir = _build_instance(src, instance, overrides)
    except FileNotFoundError as e:
        return None, str(e)
    out = inst_dir / "_render.json"
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(inst_dir), "TZ": "UTC",
           "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"}
    try:
        p = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--child",
             str(src), str(inst_dir), str(conv_path), str(out)],
            cwd=inst_dir, env=env, capture_output=True, text=True, timeout=60)
        if p.returncode != 0 or not out.exists():
            err = (p.stderr or p.stdout).strip().splitlines()
            return None, (err[-1] if err else f"exit {p.returncode}")
        result = json.loads(out.read_text())
    finally:
        shutil.rmtree(inst_dir, ignore_errors=True)
    result["header"] = (
        f"# render_prompt: {instance} ({result['name']}) at {label}\n"
        f"# clock fixed at {FIXED_NOW}; random seeded 0; offline, query_vec=None\n"
        f"# PRESET_FILES (from .env.example's recommended stacks, not the live .env): "
        f"{', '.join(INSTANCES[instance][1])}\n"
        f"# layers bot.py loaded: {', '.join(result['preset_layers'])}\n"
        f"# overrides: {', '.join(overrides) or 'none'}; every other variable is its bot.py "
        f"default\n"
    )
    return result, ""


def _as_text(result: dict) -> str:
    parts = [result["header"]]
    for i, m in enumerate(result["messages"]):
        content = m["content"]
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        parts.append(f"=== [{i}] {m['role']} ({len(content)} chars) ===\n{content}\n")
    return "\n".join(parts)


def _problems(result: dict) -> list[str]:
    """What --check treats as a broken prompt assembly."""
    msgs = result["messages"]
    texts = [m["content"] for m in msgs if isinstance(m["content"], str)]
    probs = []
    if not msgs or msgs[0]["role"] != "system" or not msgs[0]["content"].strip():
        probs.append("first message is not a non-empty system prompt")
    if not msgs or msgs[-1]["role"] != "user":
        probs.append("last message is not the user's message")
    missing = [n for n in result["preset_layers"] if n.endswith("(fallback)") or n == "<built-in>"]
    if missing:
        probs.append(f"preset layers fell back ({', '.join(missing)}): a PRESET_FILES layer "
                     f"is missing from the repo")
    for name, text in zip(result["preset_layers"], result["preset_texts"]):
        if text not in texts:
            probs.append(f"preset layer {name} loaded but is not in the prompt")
    if result["post_history"] and result["post_history"] not in texts:
        probs.append("the card's post_history_instructions are not in the prompt")
    unfilled = [i for i, t in enumerate(texts) if "{{char}}" in t or "{{user}}" in t]
    if unfilled:
        probs.append(f"unfilled {{{{char}}}}/{{{{user}}}} placeholder in message(s) {unfilled}")
    return probs


def _tree_at(ref: str) -> Path:
    """Extract telegram-companion-bot/ as it was at `ref` into a temp dir."""
    blob = subprocess.run(["git", "-C", str(REPO), "archive", ref, "telegram-companion-bot"],
                          capture_output=True, check=True).stdout
    d = Path(tempfile.mkdtemp(prefix="render_ref_"))
    with tarfile.open(fileobj=BytesIO(blob)) as t:
        t.extractall(d, filter="data")
    return d / "telegram-companion-bot"


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        _child(*sys.argv[2:6])
        return 0
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instances", nargs="*", help=f"any of: {', '.join(INSTANCES)}")
    ap.add_argument("--all", action="store_true", help="render all seven instances")
    ap.add_argument("--conversation", type=Path,
                    help="JSON with user_name, history [{role, content, ago_minutes}], latest")
    ap.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                    help="add a .env line to the render instance (repeatable)")
    ap.add_argument("--out", type=Path, help="write <instance>.json and <instance>.txt here")
    ap.add_argument("--diff", metavar="GIT_REF",
                    help="render at GIT_REF and at the working tree; print a unified diff")
    ap.add_argument("--check", action="store_true",
                    help="render, check each prompt is assembled whole, render nora twice to "
                         "confirm determinism; exit 1 on any problem")
    args = ap.parse_args()

    names = list(INSTANCES) if args.all else args.instances
    bad = [n for n in names if n not in INSTANCES]
    if bad or not names:
        ap.error(f"name one or more of {', '.join(INSTANCES)}, or use --all"
                 + (f" (unknown: {', '.join(bad)})" if bad else ""))
    for line in args.env:
        if "=" not in line:
            ap.error(f"--env takes KEY=VALUE, got {line!r}")

    tmp = Path(tempfile.mkdtemp(prefix="render_conv_"))
    conv_path = tmp / "conversation.json"
    if args.conversation:
        conv = json.loads(args.conversation.read_text())
        if "latest" not in conv:
            ap.error("--conversation needs a 'latest' field (the user's new message)")
        shutil.copy(args.conversation, conv_path)
    else:
        conv_path.write_text(json.dumps(DEFAULT_CONVERSATION))

    failed = 0
    if args.diff:
        try:
            old_src = _tree_at(args.diff)
        except subprocess.CalledProcessError as e:
            print(f"render_prompt: git archive {args.diff} failed: "
                  f"{e.stderr.decode().strip()}", file=sys.stderr)
            return 2
        for n in names:
            old, old_err = _render(old_src, n, conv_path, args.env, args.diff)
            new, new_err = _render(BOT_DIR, n, conv_path, args.env, "working tree")
            if new_err:
                print(f"## {n}: RENDER FAILED at working tree: {new_err}")
                failed += 1
                continue
            if old_err:
                print(f"## {n}: not rendered at {args.diff} ({old_err}); nothing to diff")
                continue
            # Drop the header before diffing: it names the ref, so it always differs.
            a = _as_text(old)[len(old["header"]):].splitlines(keepends=True)
            b = _as_text(new)[len(new["header"]):].splitlines(keepends=True)
            d = list(difflib.unified_diff(a, b, f"{n} @ {args.diff}", f"{n} @ working tree"))
            print(f"## {n}: " + ("no change" if not d else f"{len(d)} diff lines"))
            sys.stdout.writelines(d)
        shutil.rmtree(old_src.parent, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)
        return 1 if failed else 0

    out = args.out
    if out:
        out.mkdir(parents=True, exist_ok=True)
    for n in names:
        result, err = _render(BOT_DIR, n, conv_path, args.env, "working tree")
        if err:
            print(f"{n}: RENDER FAILED: {err}")
            failed += 1
            continue
        text = _as_text(result)
        if args.check:
            probs = _problems(result)
            if probs:
                failed += 1
                print(f"{n}: FAIL — " + "; ".join(probs))
            else:
                print(f"{n}: ok ({len(result['messages'])} messages, "
                      f"{sum(len(str(m['content'])) for m in result['messages'])} chars)")
        if out:
            (out / f"{n}.json").write_text(json.dumps(
                {"header": result["header"], "messages": result["messages"]},
                ensure_ascii=False, indent=1))
            (out / f"{n}.txt").write_text(text)
        elif not args.check:
            print(text)
    if args.check and not failed:
        a, _ = _render(BOT_DIR, "nora", conv_path, args.env, "working tree")
        b, _ = _render(BOT_DIR, "nora", conv_path, args.env, "working tree")
        if not a or not b or a["messages"] != b["messages"]:
            print("determinism: FAIL — two renders of nora differ; the clock or RNG is not "
                  "pinned, so --diff would show noise")
            failed += 1
        else:
            print("determinism: ok (two renders of nora are identical)")
    if out:
        print(f"wrote {len(names) - failed} render(s) to {out}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
