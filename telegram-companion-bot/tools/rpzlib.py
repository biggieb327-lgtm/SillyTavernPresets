#!/usr/bin/env python3
"""
rpzlib.py -- compression-based diagnostics for RP logs, Writers' Room rooms,
character cards, and preset layers. Stdlib only, so it runs as-is in Termux.

  python rpzlib.py chat   LOG [LOG ...]    redundancy, loop detection, opener/closer ruts,
                                           style counts, banned-phrase scan
  python rpzlib.py rooms  LOG [LOG ...]    voice distinctness between rooms (one log per room)
  python rpzlib.py card   CARD.json        field density, token estimate, duplicate lorebook
                                           entries, 15-field check, non-ASCII check, banned scan
  python rpzlib.py preset LAYER [LAYER..]  preset-stack budget, per-layer density, layer
                                           overlap, banned scan, non-ASCII check
  python rpzlib.py echo   CARD.json LOG    how much of the output recycles card text
  python rpzlib.py banned OUT.txt          write the default banned list to a file for editing

LOG = SillyTavern/Tavo .jsonl chat export (or a JSON array of messages), or a .txt
file with replies separated by a line of three or more hyphens.

LAYER = a plain-text preset layer file (preset.txt, preset-core.txt, preset-<name>.txt,
...). Pass an instance's layers in the order its PRESET_FILES lists them, e.g.:
  python rpzlib.py preset preset-core.txt preset-stepped.txt preset-cass.txt

Why compression works here: zlib finds repeated byte sequences. Text that repeats
itself compresses well (low ratio). Text that can be compressed well *given* some
other text (a previous reply, the card) is borrowing from it. zlib's back-reference
window is 32 KB, so every comparison below keeps the combined text under that.
"""
import argparse
import json
import random
import re
import sys
import unicodedata
import zlib
from collections import Counter, defaultdict
from itertools import combinations
from statistics import mean, median

CTX = 24000          # max context chars used for conditional compression
ROOM_CHUNK = 10000   # chunk size for room-vs-room comparisons

# ---------------------------------------------------------------- core metrics

def C(s):
    """Compressed size in bytes."""
    return len(zlib.compress(s.encode("utf-8"), 9))


def ratio(s):
    """Compressed/original. Lower = more repetitive. Short texts read high
    because of fixed header overhead, so compare like-length texts."""
    b = len(s.encode("utf-8"))
    return C(s) / b if b else 0.0


def chunk_ratio(s, size=4000):
    """Mean ratio over fixed-size chunks, so logs of different lengths compare fairly."""
    if len(s) < size:
        return ratio(s), False
    parts = [s[i:i + size] for i in range(0, len(s) - size + 1, size)]
    return mean(ratio(p) for p in parts), True


def novelty(ctx, x):
    """Share of x's information that ctx does not already supply.
    Fresh English prose continuing its own document scores about 0.7-0.8,
    so read this relatively: a reply far below the log's usual level is a loop."""
    if not ctx or not x:
        return 1.0
    ctx = ctx[-CTX:]
    cx = C(x)
    return max(0.0, (C(ctx + "\n" + x) - C(ctx)) / cx)


def ncd(a, b):
    """Normalized compression distance. 0 = same text, ~1 = unrelated."""
    ca, cb = C(a), C(b)
    return (C(a + "\n" + b) - min(ca, cb)) / max(ca, cb)

# ---------------------------------------------------------------- text handling

THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
DETAILS = re.compile(r"<details>.*?</details>", re.S | re.I)
TAGS = re.compile(r"<[^>]+>")
QUOTES = re.compile("\"[^\"]*\"|“[^”]*”")
SENT = re.compile("(?<=[.!?])\\s+|(?<=[.!?][\"”])\\s+")
WORDS = re.compile(r"[A-Za-z']+")


def clean(t, keep_details=False):
    t = THINK.sub("", t)
    if "</think>" in t.lower():                 # leaked trace with no opening tag
        t = re.split(r"</think>", t, flags=re.I)[-1]
    if not keep_details:                         # plot-tracking blocks inflate repetition
        t = DETAILS.sub("", t)
    return TAGS.sub("", t).strip()


def narration(t):
    return QUOTES.sub(" ", t)


def sentences(t):
    return [s.strip() for s in SENT.split(t) if s.strip()]


def stem(s, n=3):
    return " ".join(WORDS.findall(s.lower())[:n])


def load_log(path, keep_details=False):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    msgs = []
    if path.lower().endswith(".txt"):
        msgs = re.split(r"(?m)^\s*-{3,}\s*$", raw)
    else:
        s = raw.strip()
        items = []
        if s.startswith("["):
            items = json.loads(s)
        else:
            for line in s.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        for m in items:
            if not isinstance(m, dict) or "mes" not in m:
                continue
            if m.get("is_user") or m.get("is_system") is True:
                continue
            msgs.append(m["mes"])
    out = [clean(m, keep_details) for m in msgs]
    return [m for m in out if m]

# ---------------------------------------------------------------- banned list

DEFAULT_BANNED = [
    # spatial presence metaphors
    r"takes? up (?:the )?space", r"fill(?:s|ed|ing)? (?:the|every) room",
    r"command(?:s|ed|ing)? the room", r"own(?:s|ed)? the room",
    r"dominat(?:es|ed|ing) the space",
    # house list
    r"predatory", r"velvet\w*", r"breath(?:ing)? (?:hitch|catch|caught)\w*",
    r"architecture", r"electric", r"visceral", r"something shifted",
    r"luminous", r"the weight of", r"moreover", r"furthermore", r"additionally",
    r"not only\b.{0,60}?\bbut also",
    # DS4 additions
    r"fresh meat", r"husky", r"ozone", r"asset", r"shivers? (?:ran |run |running )?down (?:\w+ )?spine",
    r"pupils (?:blown|dilated)\w*", r"(?:blown|dilated) pupils?", r"nails bit\w*",
    r"vise", r"vice", r"structural integrity", r"deep curve", r"furnace",
    r"throaty", r"calloused", r"guttural", r"slick", r"unadulterated",
    r"jaw (?:clench|tighten)\w*", r"clenched jaw", r"barely above a whisper", r"musk\w*",
]


def load_banned(path=None):
    pats = DEFAULT_BANNED
    if path:
        with open(path, encoding="utf-8") as f:
            pats = [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
    return [(p, re.compile(r"\b" + p + r"\b", re.I | re.S)) for p in pats]


def scan_banned(texts, banned):
    hits = defaultdict(list)
    for i, t in enumerate(texts):
        for p, rx in banned:
            for m in rx.finditer(t):
                hits[m.group(0).lower()].append(i + 1)
    return hits


def print_banned(hits, label="#"):
    if not hits:
        print("  Banned      none")
        return
    rows = sorted(hits.items(), key=lambda kv: -len(kv[1]))
    print("  Banned      %d hits" % sum(len(v) for v in hits.values()))
    for phrase, where in rows:
        locs = ",".join(str(w) for w in where[:8]) + ("..." if len(where) > 8 else "")
        print("    %-26s x%-3d %s%s" % ('"' + phrase[:24] + '"', len(where), label, locs))

# ---------------------------------------------------------------- chat

def cmd_chat(args):
    banned = load_banned(args.banned)
    for path in args.logs:
        rs = load_log(path, args.keep_details)
        print("\n== %s  (%d replies)" % (path, len(rs)))
        if not rs:
            print("  no AI replies found")
            continue
        corpus = "\n\n".join(rs)
        dens, full = chunk_ratio(corpus)
        print("  Length      avg %d chars, median %d" %
              (mean(len(r) for r in rs), median(len(r) for r in rs)))
        print("  Density     %.3f%s   (higher = less repetitive phrasing)" %
              (dens, "" if full else " (short log)"))
        print("  In-reply    median ratio %.3f; most self-repetitive #%d" %
              (median(ratio(r) for r in rs), min(range(len(rs)), key=lambda i: ratio(rs[i])) + 1))

        nov = []
        for i in range(1, len(rs)):
            ctx = "\n\n".join(rs[max(0, i - args.window):i])
            nov.append((i + 1, novelty(ctx, rs[i])))
        if nov:
            vals = [v for _, v in nov]
            print("  Novelty     median %.2f, min %.2f @ #%d  (vs last %d replies)" %
                  (median(vals), min(vals), min(nov, key=lambda t: t[1])[0], args.window))
            if len(vals) >= 8:
                h = len(vals) // 2
                a, b = median(vals[:h]), median(vals[h:])
                trend = "falling - drifting into a rut" if b < a - 0.05 else "steady"
                print("  Trend       1st half %.2f -> 2nd half %.2f  (%s)" % (a, b, trend))
            fresh = sorted(vals)[int(len(vals) * 0.75)]   # this log's typical fresh reply
            cut = fresh * args.loop
            loops = [(i, v) for i, v in nov if v < cut]
            if loops:
                print("  Loop flags  " + ", ".join("#%d %.2f" % t for t in loops[:12]) +
                      (" ..." if len(loops) > 12 else ""))
            else:
                print("  Loop flags  none below %.2f (%.0f%% of this log's fresh level)" %
                      (cut, 100 * args.loop))

        for name, pick in (("Openers", 0), ("Closers", -1)):
            c = Counter(stem(sentences(r)[pick]) for r in rs if sentences(r))
            reps = [(k, v) for k, v in c.most_common(4) if v > 1 and k]
            txt = ", ".join('"%s" x%d' % kv for kv in reps) if reps else "no repeats"
            print("  %-11s %s" % (name, txt))
        first = Counter((WORDS.findall(r.lower()) or [""])[0] for r in rs)
        w, cnt = first.most_common(1)[0]
        if cnt / len(rs) >= 0.3:
            print("  First word  \"%s\" starts %d%% of replies" % (w, 100 * cnt // len(rs)))

        dash = sum(narration(r).count("—") + narration(r).count(" -- ") for r in rs)
        ell = sum(r.count("…") + r.count("...") for r in rs)
        semi = sum(narration(r).count(";") for r in rs)
        print("  Style       em-dash (narration) %d, ellipsis %d, semicolon (narration) %d" %
              (dash, ell, semi))
        print_banned(scan_banned(rs, banned))

# ---------------------------------------------------------------- rooms

def pick_chunks(s, size=ROOM_CHUNK, k=3):
    cs = [s[i:i + size] for i in range(0, len(s) - size + 1, size)]
    if len(cs) < 2:                     # short log: split in halves so a baseline still exists
        h = len(s) // 2
        cs = [s[:h], s[h:]] if h >= 2000 else [s]
    if len(cs) > k:
        step = len(cs) / k
        cs = [cs[int(j * step)] for j in range(k)]
    return cs


def cmd_rooms(args):
    rooms = {}
    for path in args.logs:
        name = re.sub(r"\.[^.]+$", "", path.split("/")[-1])
        rs = load_log(path, args.keep_details)
        if rs:
            rooms[name] = pick_chunks("\n\n".join(rs))
    if len(rooms) < 2:
        sys.exit("need at least two non-empty logs")
    within = {}
    print("\nWithin-room baseline (NCD between a room's own samples):")
    for n, cs in rooms.items():
        if len(cs) >= 2:
            within[n] = mean(ncd(a, b) for a, b in combinations(cs, 2))
            print("  %-24s %.3f" % (n[:24], within[n]))
        else:
            print("  %-24s n/a (log under 4000 chars)" % n[:24])
    pairs = []
    for a, b in combinations(rooms, 2):
        d = mean(ncd(x, y) for x in rooms[a] for y in rooms[b])
        base = [within[r] for r in (a, b) if r in within]
        gap = d - mean(base) if base else None
        pairs.append((a, b, d, gap))
    pairs.sort(key=lambda t: t[3] if t[3] is not None else t[2])
    print("\nRoom pairs, least distinct first (gap = cross distance minus baseline;")
    print("near 0 means the two rooms sound like one room):")
    for a, b, d, gap in pairs:
        g = "gap %+.3f" % gap if gap is not None else "gap n/a"
        print("  %s <-> %s\n      %.3f  %s" % (a, b, d, g))

# ---------------------------------------------------------------- card

FIELDS = ["description", "personality", "scenario", "first_mes", "mes_example",
          "system_prompt", "post_history_instructions", "creator_notes"]
PERMANENT = ["description", "personality", "scenario", "system_prompt",
             "post_history_instructions"]
LORE_REQ = ["id", "keys", "content", "enabled", "insertion_order", "case_sensitive",
            "name", "priority", "comment", "selective", "secondary_keys", "constant",
            "position", "selectiveLogic", "probability"]


def load_card(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("data", d)


def entries_of(card):
    book = card.get("character_book") or {}
    return book.get("entries") or []


def walk_strings(obj, where=""):
    if isinstance(obj, str):
        yield where, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, where + "." + str(k) if where else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, "%s[%d]" % (where, i))


def cmd_card(args):
    card = load_card(args.card)
    print("\n== %s  (%s)" % (args.card, card.get("name", "?")))
    print("  %-26s %6s %6s %6s" % ("field", "chars", "~tok", "ratio"))
    perm = 0
    for f in FIELDS:
        t = card.get(f) or ""
        if not t:
            continue
        r = ratio(t)
        flag = "  <- padded/repetitive" if r < args.pad and len(t) > 600 else ""
        print("  %-26s %6d %6d %6.3f%s" % (f, len(t), len(t) // 4, r, flag))
        if f in PERMANENT:
            perm += len(t) // 4
    print("  Permanent ~%d tokens (chars/4 estimate; target ~2500)" % perm)

    ents = entries_of(card)
    print("\n  Lorebook: %d entries" % len(ents))
    for i, e in enumerate(ents):
        miss = [k for k in LORE_REQ if k not in e]
        if miss:
            print("    entry %d (%s) missing: %s" % (i, e.get("comment") or e.get("name") or "?",
                                                   ", ".join(miss)))
    label = lambda i: "%d:%s" % (i, (ents[i].get("comment") or ents[i].get("name") or "")[:18])
    dups = []
    for i, j in combinations(range(len(ents)), 2):
        a, b = ents[i].get("content") or "", ents[j].get("content") or ""
        if a and b:
            d = ncd(a, b)
            if d < args.dup:
                dups.append((d, label(i), label(j)))
    desc = card.get("description") or ""
    for i, e in enumerate(ents):
        c = e.get("content") or ""
        if c and desc and len(desc) + len(c) < 30000:
            n = novelty(desc, c)
            if n < args.dup:
                dups.append((n, label(i), "description"))
    if dups:
        print("    Overlap (lower = more duplicated; wasted tokens on trigger):")
        for d, a, b in sorted(dups):
            print("      %.2f  %s <-> %s" % (d, a, b))
    else:
        print("    No overlapping entries below %.2f" % args.dup)

    bad = []
    for where, s in walk_strings(card):
        chars = Counter(ch for ch in s if ord(ch) > 127)
        for ch, n in chars.items():
            name = unicodedata.name(ch, "U+%04X" % ord(ch))
            bad.append("%s: %s x%d" % (where, name, n))
    print("\n  Non-ASCII   " + ("none" if not bad else "%d kinds" % len(bad)))
    for b in bad[:20]:
        print("    " + b)

    texts, names = [], []
    for f in FIELDS:
        if f != "creator_notes" and card.get(f):
            texts.append(card[f]); names.append(f)
    for i, e in enumerate(ents):
        if e.get("content"):
            texts.append(e["content"]); names.append("lore" + str(i))
    hits = scan_banned(texts, load_banned(args.banned))
    hits = {k: [names[i - 1] for i in v] for k, v in hits.items()}
    print()
    print_banned(hits, label="")

# ---------------------------------------------------------------- preset

def cmd_preset(args):
    """Analyze a preset LAYER stack in PRESET_FILES order (bot.py, v2026-07-25.5):
    a per-bot ordered list of plain-text files concatenated into TEXTING_STYLE and
    sent as system blocks on every message. Same metrics as `card`, applied to
    layers instead of fields, plus layer-vs-layer overlap since a stack is built
    from independent files that can end up saying the same thing twice."""
    banned = load_banned(args.banned)
    layers = []
    for path in args.layers:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        name = re.sub(r"\.[^.]+$", "", path.split("/")[-1])
        layers.append((name, text))

    print("\n== preset stack: %s" % ", ".join(n for n, _ in layers))
    print("  %-20s %7s %7s %7s" % ("layer", "chars", "~tok", "ratio"))
    total_chars = total_tok = 0
    for name, t in layers:
        r = ratio(t)
        tok = len(t) // 4
        total_chars += len(t)
        total_tok += tok
        flag = "  <- padded/repetitive" if r < args.pad and len(t) > 600 else ""
        print("  %-20s %7d %7d %7.3f%s" % (name, len(t), tok, r, flag))
    print("  %-20s %7d %7d" % ("TOTAL", total_chars, total_tok))
    print("  (chars/4 -- the same raw heuristic as bot.py's _est_tokens; the live")
    print("   NanoGPT calibration bot.py applies for /audit, ~0.92x recently per")
    print("   .env.example, is NOT reproduced here -- no API call is made)")

    if len(layers) > 1:
        combined = "\n\n".join(t for _, t in layers)
        dens, full = chunk_ratio(combined)
        print("  Combined density %.3f%s" % (dens, "" if full else " (short stack)"))
        print("\n  Layer overlap (NCD; lower = more redundant -- a duplicated layer wastes budget):")
        for (na, ta), (nb, tb) in combinations(layers, 2):
            d = ncd(ta, tb)
            flag = "  <- check for duplication" if d < args.dup else ""
            print("    %.2f  %s <-> %s%s" % (d, na, nb, flag))

    names = [n for n, _ in layers]
    hits = scan_banned([t for _, t in layers], banned)
    hits = {k: [names[i - 1] for i in v] for k, v in hits.items()}
    print()
    print_banned(hits, label="")

    bad = []
    for name, t in layers:
        chars = Counter(ch for ch in t if ord(ch) > 127)
        for ch, n in chars.items():
            bad.append("%s: %s x%d" % (name, unicodedata.name(ch, "U+%04X" % ord(ch)), n))
    print("\n  Non-ASCII   " + ("none" if not bad else "%d kinds" % len(bad)))
    for b in bad[:20]:
        print("    " + b)

# ---------------------------------------------------------------- echo

def cmd_echo(args):
    card = load_card(args.card)
    rs = load_log(args.log, args.keep_details)
    if not rs:
        sys.exit("no AI replies found")
    parts = [card.get(f) or "" for f in ("description", "personality", "scenario")]
    parts += [e.get("content") or "" for e in entries_of(card)]
    body = "\n".join(p for p in parts if p)
    sources = [("card body", body), ("first_mes", card.get("first_mes") or ""),
               ("mes_example", card.get("mes_example") or "")]
    print("\n== echo: %s vs %s  (%d replies)" % (args.card, args.log, len(rs)))
    print("  Echo = share of a reply the source phrasing supplies, minus what the same")
    print("  words supply when shuffled (so shared vocabulary alone scores ~0).")
    print("  Above ~0.05 the reply is lifting phrases; above ~0.15 it is copying lines.")
    rng = random.Random(0)
    for name, src in sources:
        if not src:
            continue
        chunks = [src[i:i + 20000] for i in range(0, len(src), 20000)]
        ctrl = []
        for c in chunks:
            w = c.split()
            rng.shuffle(w)
            ctrl.append(" ".join(w))

        def echo(r):
            raw = 1 - min(novelty(c, r) for c in chunks)
            base = 1 - min(novelty(c, r) for c in ctrl)
            return max(0.0, raw - base)
        ev = [(k + 1, echo(r)) for k, r in enumerate(rs)]
        vals = [v for _, v in ev]
        top = sorted(ev, key=lambda t: -t[1])[:3]
        print("  %-12s median %.2f, max %.2f" % (name, median(vals), max(vals)))
        for k, v in top:
            snippet = re.sub(r"\s+", " ", rs[k - 1])[:60]
            print("    #%-4d %.2f  %s..." % (k, v, snippet))

# ---------------------------------------------------------------- main

def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--keep-details", action="store_true",
                        help="keep <details> blocks (plot trackers) in replies")
    common.add_argument("--banned", help="banned list file, one regex per line")

    ap = argparse.ArgumentParser(description="Compression diagnostics for RP output, cards, and presets.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("chat", parents=[common])
    p.add_argument("logs", nargs="+")
    p.add_argument("--loop", type=float, default=0.65,
                   help="flag replies whose novelty is below this fraction of the log's 75th percentile")
    p.add_argument("--window", type=int, default=5, help="previous replies used as context")
    p.set_defaults(fn=cmd_chat)

    p = sub.add_parser("rooms", parents=[common])
    p.add_argument("logs", nargs="+")
    p.set_defaults(fn=cmd_rooms)

    p = sub.add_parser("card", parents=[common])
    p.add_argument("card")
    p.add_argument("--dup", type=float, default=0.6, help="overlap threshold")
    p.add_argument("--pad", type=float, default=0.40, help="ratio below this = padded field")
    p.set_defaults(fn=cmd_card)

    p = sub.add_parser("preset", parents=[common])
    p.add_argument("layers", nargs="+", help="preset layer files, in PRESET_FILES order")
    p.add_argument("--dup", type=float, default=0.6, help="overlap threshold")
    p.add_argument("--pad", type=float, default=0.40, help="ratio below this = padded layer")
    p.set_defaults(fn=cmd_preset)

    p = sub.add_parser("echo", parents=[common])
    p.add_argument("card")
    p.add_argument("log")
    p.set_defaults(fn=cmd_echo)

    p = sub.add_parser("banned")
    p.add_argument("out")
    p.set_defaults(fn=lambda a: open(a.out, "w").write("\n".join(DEFAULT_BANNED) + "\n"))

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
