#!/usr/bin/env python3
"""Validate a spec v2 character card JSON.

Checks (hard bugs -> exit 1):
  - JSON parses
  - ASCII-safety of all string values
  - Lorebook entries contain all 15 required fields with correct types
  - Banned phrases in text fields

Checks (warnings -> exit 0 unless combined with hard bugs):
  - Negative-directive patterns in directive fields
  - Missing creator_notes
  - Permanent token estimate vs budget
  - DS4-mode style violations (with --ds4)

Usage: python validate_card.py card.json [--ds4] [--budget 2500]
"""
import argparse
import json
import re
import sys

BANNED_PHRASES = [
    "takes up space", "fills the room", "fills every room", "commands the room",
    "owns the room", "dominates the space", "fresh meat", "breath hitching",
    "breath catching", "breath hitches", "husky", "ozone", "shivers down spine",
    "pupils blown wide", "pupils dilated", "nails biting", "structural integrity",
    "deep curve", "furnace", "throaty", "calloused", "guttural", "slick",
    "unadulterated", "jaw clenched", "barely above a whisper", "musk",
    "predatory", "velvet", "electric", "visceral", "something shifted",
    "luminous", "the weight of",
]
# Word-boundary-sensitive short terms checked separately to avoid false hits
BANNED_WORDS = ["vise", "vice", "asset"]

LOREBOOK_FIELDS = {
    "id": int, "keys": list, "content": str, "enabled": bool,
    "insertion_order": int, "case_sensitive": bool, "name": str,
    "priority": int, "comment": str, "selective": bool,
    "secondary_keys": list, "constant": bool, "position": (str, int),
    "selectiveLogic": int, "probability": int,
}

DIRECTIVE_FIELDS = ["description", "personality", "post_history_instructions", "system_prompt"]
PERMANENT_FIELDS = ["description", "personality", "scenario", "mes_example", "post_history_instructions", "system_prompt"]
NEG_PATTERNS = [
    (re.compile(r"\bnever\b", re.I), "never"),
    (re.compile(r"\bdo(es)? not\b", re.I), "do not"),
    (re.compile(r"\bdon't\b", re.I), "don't"),
    (re.compile(r"\bavoid(s|ed|ing)?\b", re.I), "avoid"),
    (re.compile(r"\bNot [A-Z]?\w+\. Not\b"), "Not X. Not Y."),
    (re.compile(r"\brefuse(s|d)? to\b", re.I), "refuses to"),
]
DS4_FEMALE_VOICE = ["low", "deep", "husky", "throaty", "gravelly"]


def get_data(card):
    return card.get("data", card)


def iter_strings(obj, path="root"):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_strings(v, f"{path}[{i}]")


def check_ascii(card, bugs):
    for path, s in iter_strings(card):
        bad = sorted({c for c in s if ord(c) > 127})
        if bad:
            shown = ", ".join(f"{c!r} (U+{ord(c):04X})" for c in bad[:8])
            bugs.append(f"NON-ASCII in {path}: {shown}")


def check_banned(card, bugs):
    for path, s in iter_strings(card):
        low = s.lower()
        for p in BANNED_PHRASES:
            if p in low:
                bugs.append(f"BANNED PHRASE '{p}' in {path}")
        for w in BANNED_WORDS:
            if re.search(rf"\b{w}\b", low):
                bugs.append(f"BANNED WORD '{w}' in {path} (verify context)")
        if re.search(r"\barchitecture\b", low) and "lorebook" not in path.lower():
            bugs.append(f"POSSIBLE BANNED 'architecture' (psych metaphor?) in {path}")


def check_lorebook(card, bugs):
    data = get_data(card)
    book = data.get("character_book") or {}
    entries = book.get("entries", []) if isinstance(book, dict) else []
    if isinstance(entries, dict):
        entries = list(entries.values())
    for i, e in enumerate(entries):
        label = e.get("name", f"entry {i}")
        for field, typ in LOREBOOK_FIELDS.items():
            if field not in e:
                bugs.append(f"LOREBOOK '{label}': missing required field '{field}'")
            elif not isinstance(e[field], typ) or (typ is int and isinstance(e[field], bool)):
                bugs.append(f"LOREBOOK '{label}': field '{field}' wrong type "
                            f"(got {type(e[field]).__name__})")
        p = e.get("probability")
        if isinstance(p, int) and not 0 <= p <= 100:
            bugs.append(f"LOREBOOK '{label}': probability {p} outside 0-100")
    return entries


def check_negatives(card, warns):
    data = get_data(card)
    for f in DIRECTIVE_FIELDS:
        text = data.get(f) or ""
        for rx, name in NEG_PATTERNS:
            for m in rx.finditer(text):
                ctx = text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
                warns.append(f"NEGATIVE-DIRECTIVE pattern '{name}' in {f}: ...{ctx}...")


def estimate_tokens(card, entries, budget, warns, info):
    data = get_data(card)
    chars = sum(len(data.get(f) or "") for f in PERMANENT_FIELDS)
    chars += sum(len(e.get("content", "")) for e in entries if e.get("constant"))
    est = chars // 4
    info.append(f"Permanent token estimate: ~{est} (budget {budget})")
    if est > budget:
        warns.append(f"TOKEN BUDGET: estimate ~{est} exceeds target {budget}")


def check_ds4(card, warns):
    data = get_data(card)
    for f in ["mes_example", "first_mes"]:
        text = data.get(f) or ""
        if not text:
            continue
        if "..." in text or "\u2026" in text:
            warns.append(f"DS4: ellipsis present in {f} (banned globally)")
        # em-dash outside quotes = narration em-dash
        outside = re.sub(r'"[^"]*"', "", text)
        if "--" in outside or "\u2014" in outside:
            warns.append(f"DS4: em-dash in narration in {f}")
        low = text.lower()
        for w in DS4_FEMALE_VOICE:
            if re.search(rf"\b{w}\b[^.]*\bvoice\b|\bvoice\b[^.]*\b{w}\b", low):
                warns.append(f"DS4: female-voice descriptor '{w}' near 'voice' in {f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("card")
    ap.add_argument("--ds4", action="store_true")
    ap.add_argument("--budget", type=int, default=2500)
    args = ap.parse_args()

    bugs, warns, info = [], [], []
    try:
        with open(args.card, encoding="utf-8") as f:
            card = json.load(f)
    except Exception as e:
        print(f"HARD BUG: JSON failed to parse: {e}")
        sys.exit(1)

    check_ascii(card, bugs)
    check_banned(card, bugs)
    entries = check_lorebook(card, bugs)
    check_negatives(card, warns)
    estimate_tokens(card, entries, args.budget, warns, info)
    if args.ds4:
        check_ds4(card, warns)

    data = get_data(card)
    if not (data.get("creator_notes") or "").strip():
        warns.append("creator_notes missing or empty (required on every build/rebuild)")

    print(f"=== {args.card} ===")
    for line in info:
        print(f"[info] {line}")
    if bugs:
        print(f"\nHARD BUGS ({len(bugs)}):")
        for b in bugs:
            print(f"  [BUG] {b}")
    if warns:
        print(f"\nWARNINGS ({len(warns)}) - review, not all are errors:")
        for w in warns:
            print(f"  [warn] {w}")
    if not bugs and not warns:
        print("Clean: no hard bugs, no warnings.")
    sys.exit(1 if bugs else 0)


if __name__ == "__main__":
    main()
