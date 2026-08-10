#!/usr/bin/env python3
"""Print the selfie prompts an instance would actually send, without sending anything.

Why this exists: `build_selfie_prompt` is where every reported face-drift bug has lived
(v2026-08-01.7/.9, v2026-08-03.2), and the only way anyone has ever seen its output is by
generating a real image and inferring backwards. This renders the text so a prompt can be
read, diffed across a release, or pasted straight into Gemini/nano-banana with the
instance's reference photo attached.

    python3 tools/selfie_prompt_preview.py emily -n 3
    python3 tools/selfie_prompt_preview.py emily --diff          # face lock off vs on
    python3 tools/selfie_prompt_preview.py emily --weather "72°F, clear, wind 5mph"

Repo-only: nothing here deploys, and `vps-sync.sh` does not copy tools/. It builds a
throwaway instance directory from the repo's seed files, so it reads what is COMMITTED,
not what a live VPS instance has on disk — if the two have diverged, the live instance is
authoritative (v2026-08-01.10).
"""
import argparse
import json
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEED_FILES = ("appearance.txt", "atlas.txt", "setting.txt")
# Any id works; it only has to be a key the stubbed state answers to.
_PREVIEW_CHAT_ID = 1


def _fake_instance(instance: str, card: Path) -> Path:
    """A minimal instance dir bot.py can import against — the conftest.py recipe, plus the
    real card and seed files so NAME and SELFIE_APPEARANCE are the instance's own."""
    d = Path(tempfile.mkdtemp(prefix=f"selfie_preview_{instance}_"))
    (d / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=preview:not-a-real-token\n"
        "NANOGPT_API_KEY=preview-not-a-real-key\n"
        f"CHARACTER_CARD={card.name}\n"
        "BOT_TIMEZONE=America/Los_Angeles\n"
    )
    shutil.copy(card, d / card.name)
    for name in SEED_FILES:
        src = REPO / instance / name
        if src.exists():
            shutil.copy(src, d / name)
    return d


def _find_card(instance: str) -> Path:
    """Cards are named after the character, not the directory (emily -> emily_harper.json)."""
    exact = REPO / f"{instance}.json"
    if exact.exists():
        return exact
    matches = sorted(REPO.glob(f"{instance}*.json"))
    if not matches:
        sys.exit(f"no character card found for '{instance}' in {REPO}")
    return matches[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instance", help="seed directory name, e.g. emily")
    ap.add_argument("-n", type=int, default=5, help="how many prompts to render (default 5)")
    ap.add_argument("--seed", type=int, default=0, help="first RNG seed (default 0)")
    # Contiguous seeds sample the pools evenly, which is the wrong sample when you are
    # hunting one draw. The 2026-08-03 A/B ran seeds 0-3 and drew no wide framing at all,
    # so it never tested the shape the reported failure had.
    ap.add_argument("--seeds", default="",
                    help="comma-separated explicit seeds, e.g. 4,16,22 (overrides --seed/-n)")
    ap.add_argument("--hint", default="", help="pin the scene, as a [selfie: ...] tag would")
    ap.add_argument("--weather", default="55°F, overcast, wind 6mph",
                    help="weather reading to simulate; empty string for none")
    # The fake .env has no WEATHER_LOCATION, so every previewed prompt otherwise says
    # "Seattle" — wrong for all seven instances, and it lands in the pasted prompt.
    ap.add_argument("--location", default="",
                    help="override WEATHER_LOCATION, e.g. 'Olympia, WA' (default: the .env default)")
    # Production ALWAYS passes a real chat_id, which adds two blocks this tool was silently
    # dropping — the mood line ("let it read in her face", an instruction to change her face)
    # and the scene-dedup list. A preview that omits them is not previewing production.
    ap.add_argument("--mood", default="neutral",
                    help="mood string for the 'let it read in her face' line; empty to omit it")
    ap.add_argument("--recent", default="",
                    help="semicolon-separated recent scenes for the dedup block, as production sends")
    ap.add_argument("--diff", action="store_true",
                    help="render each prompt with SELFIE_FACE_LOCK off, then on")
    args = ap.parse_args()

    card = _find_card(args.instance)
    home = _fake_instance(args.instance, card)
    try:
        sys.argv = [sys.argv[0], str(home)]
        os.environ["BOT_HOME"] = str(home)
        sys.path.insert(0, str(REPO))
        try:
            import bot  # noqa: E402  -- module-level init needs the env above
        except ModuleNotFoundError as e:
            # The VPS's system python has none of bot.py's dependencies; the fleet runs
            # from a shared venv. Without this the failure is a bare ModuleNotFoundError
            # from inside bot.py's import block, naming no interpreter (hit 2026-08-10 on
            # atlas_audit — this tool had the identical trap since v2026-08-03.2).
            sys.exit(
                f"cannot import bot.py — {e.name} is missing.\n"
                f"This tool imports bot.py, so it needs bot.py's dependencies:\n"
                f"  on the VPS:  /opt/telegram-bots/venv/bin/python3 "
                f"{Path(__file__).resolve()} ...\n"
                f"  elsewhere:   pip install -r <repo>/telegram-companion-bot/requirements.txt")

        # No reference photo can be committed (.gitignore keeps every *.png/*.jpg out), so
        # the edit branch is forced on. That is the branch every live instance with a base
        # photo takes, and the only one the face lock touches.
        bot._has_base_image = lambda: True
        if args.location:
            bot.WEATHER_LOCATION = args.location
        if args.weather:
            bot._weather_cache["text"] = args.weather
            bot._weather_cache["ts"] = 9e9

        # chat_id is what gates the mood line and the dedup block. Passing None renders a
        # prompt no live instance ever sends; passing an id with the state stubbed renders
        # the real one.
        chat_id = None if not args.mood else _PREVIEW_CHAT_ID
        if chat_id is not None:
            bot._mood_vibe = lambda _cid: args.mood
            recent = [s.strip() for s in args.recent.split(";") if s.strip()]
            bot._recent_selfie_hints[chat_id] = recent

        print(f"# instance={args.instance}  card={card.name}  NAME={bot.NAME}")
        print(f"# appearance.txt: {'yes' if (REPO / args.instance / 'appearance.txt').exists() else 'NO'}")
        print(f"# weather={args.weather or '(none)'}  hint={args.hint or '(none)'}")
        print(f"# mood={args.mood or '(omitted — chat_id=None, NOT what production sends)'}  recent={args.recent or '(none)'}")
        # Read from the fake .env, so they are defaults and not this instance's real values.
        print(f"# NOT previewed (live .env only): WEATHER_LOCATION={bot.WEATHER_LOCATION!r}, "
              f"OUTDOOR_LAYER={bot.OUTDOOR_LAYER!r}, wardrobe.json\n")

        modes = [False, True] if args.diff else [bot.SELFIE_FACE_LOCK]
        seeds = ([int(s) for s in args.seeds.split(",") if s.strip()] if args.seeds
                 else [args.seed + i for i in range(args.n)])
        for seed in seeds:
            for lock in modes:
                bot.SELFIE_FACE_LOCK = lock
                random.seed(seed)
                prompt = bot.build_selfie_prompt(args.hint, chat_id)
                label = f"seed {seed}" + (f"  FACE_LOCK={'on' if lock else 'off'}"
                                          if args.diff else "")
                print(f"--- {label}  ({len(prompt)} chars) ---")
                print(prompt)
                print()
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    main()
