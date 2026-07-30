#!/usr/bin/env python3
"""Ghost-token audit: measure the fixed per-message prompt cost of each fleet instance,
and find tokens that are paid for on every call but contribute nothing new.

Replicates bot.py's own accounting so the numbers are comparable to /audit:
  _est_tokens(text) == max(1, len(text) // 4)      (bot.py ~line 968)
  load_character() field merge                      (bot.py ~line 2340)

RAW units throughout (calibration ratio 1.0), matching .env.example's "raw" column.
"""
import json
import re
import sys
from pathlib import Path

BASE = Path("/home/user/SillyTavernPresets/telegram-companion-bot")


def est_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


# --- the recommended stacks, transcribed from .env.example lines 296-306 ---------------
STACKS = {
    "cass":   ["preset-core.txt", "preset-stepped.txt", "preset-cass.txt"],
    "priya":  ["preset-core.txt", "preset-stepped.txt", "preset-priya.txt"],
    "nora":   ["preset-core.txt", "preset-rp.txt", "preset-explicit.txt",
               "preset-stepped.txt", "preset-nora.txt"],
    "bonnie": ["preset-core.txt", "preset-rp.txt", "preset-explicit.txt",
               "preset-stepped.txt", "preset-bonnie.txt"],
    "emily":  ["preset-core.txt", "preset-rp.txt", "preset-explicit.txt",
               "preset-stepped.txt", "preset-emily.txt"],
    "jules":  ["preset-core.txt", "preset-rp.txt", "preset-explicit.txt",
               "preset-stepped.txt", "preset-jules.txt"],
    "marcus": ["preset-core.txt", "preset-rp.txt", "preset-explicit.txt",
               "preset-stepped.txt", "preset-marcus.txt"],
}

CARDS = {
    "nora": "nora.json", "bonnie": "bonnie.json", "cass": "cass.json",
    "emily": "emily_harper.json", "priya": "priya.json",
    "jules": "jules_nakagawa.json", "marcus": "marcus_calder.json",
}

# Fields bot.py's load_character() actually reads (bot.py 2340-2402).
READ_FIELDS = {
    "name", "system_prompt", "description", "personality", "scenario",
    "mes_example", "post_history_instructions", "character_book",
    "first_mes", "extensions",
}


def parse_card(path: Path) -> dict:
    """Mirror load_character()'s field usage and return a per-field token breakdown."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = raw.get("data", raw) if isinstance(raw, dict) else {}
    # bot.py handles both v2 (data:) and flat; detect which fields are present.
    out = {"fields": {}, "unread": {}, "lore": {}}

    for f in ("system_prompt", "description", "personality", "scenario",
              "mes_example", "post_history_instructions"):
        t = est_tokens((data.get(f) or "").strip())
        if t:
            out["fields"][f] = t

    depth = (data.get("extensions") or {}).get("depth_prompt") or {}
    if depth.get("prompt"):
        out["fields"]["depth_prompt"] = est_tokens(depth["prompt"].strip())

    book = data.get("character_book") or {}
    entries = book.get("entries") or []
    const_t = 0
    trig_t = 0
    for e in entries:
        if not e.get("enabled", True):
            continue
        t = est_tokens((e.get("content") or "").strip())
        if e.get("constant"):
            const_t += t
        else:
            trig_t += t
    out["lore"] = {"constant": const_t, "triggered": trig_t, "entries": len(entries)}

    # Fields present in the JSON that load_character() never reads.
    for k, v in data.items():
        if k in READ_FIELDS:
            continue
        blob = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        t = est_tokens(blob)
        if t > 20:
            out["unread"][k] = t

    out["first_mes"] = est_tokens((data.get("first_mes") or "").strip())
    return out


def read(name: str) -> str:
    p = BASE / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


# --- sentence-level duplication -------------------------------------------------------
def norm_sentences(text: str, min_words: int = 7) -> list:
    """Normalized sentences long enough that a collision is meaningful, not incidental."""
    text = re.sub(r"\{\{char\}\}|\{\{user\}\}", "X", text)
    text = re.sub(r"[*_`#>\[\]]", " ", text)
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    out = []
    for c in chunks:
        c = re.sub(r"\s+", " ", c).strip().lower()
        c = re.sub(r"^[-•\d.)\s]+", "", c)
        c = re.sub(r"[^a-z0-9 ]", "", c)
        if len(c.split()) >= min_words:
            out.append(c)
    return out


def shingles(text: str, n: int = 8) -> set:
    words = re.sub(r"[^a-z0-9 ]", " ",
                   re.sub(r"\s+", " ", text.lower())).split()
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def main():
    print("=" * 78)
    print("GHOST-TOKEN AUDIT — fixed per-message prompt cost, raw units (len//4)")
    print("=" * 78)

    # --- 1. preset layer sizes --------------------------------------------------------
    layer_files = sorted(p.name for p in BASE.glob("preset*.txt"))
    print("\n[1] PRESET LAYERS ON DISK")
    layer_tok = {}
    for f in layer_files:
        t = est_tokens(read(f))
        layer_tok[f] = t
        print(f"    {f:<26} {t:>6} tok")

    # --- 2. seed files per instance ---------------------------------------------------
    print("\n[2] PER-INSTANCE FIXED BLOCKS (seed files + card + layers)")
    hdr = (f"    {'inst':<8}{'card_sys':>9}{'post_hx':>9}{'lore_c':>8}"
           f"{'seeds':>7}{'layers':>8}{'FIXED':>8}{'lore_trig':>10}")
    print(hdr)
    print("    " + "-" * (len(hdr) - 4))
    rows = {}
    for inst, cardname in CARDS.items():
        card = parse_card(BASE / cardname)
        # card_sys = the merged system block load_character builds
        card_sys = sum(card["fields"].get(f, 0) for f in
                       ("system_prompt", "description", "personality",
                        "scenario", "mes_example"))
        post_hx = (card["fields"].get("post_history_instructions", 0)
                   + card["fields"].get("depth_prompt", 0))
        seeds = sum(est_tokens(read(f"{inst}/{n}"))
                    for n in ("people.txt", "projects.txt", "schedule.txt"))
        atlas_all = est_tokens(read(f"{inst}/atlas.txt"))
        layers = sum(layer_tok.get(f, 0) for f in STACKS[inst])
        lore_c = card["lore"]["constant"]
        fixed = card_sys + post_hx + lore_c + seeds + layers
        rows[inst] = dict(card=card, card_sys=card_sys, post_hx=post_hx,
                          seeds=seeds, layers=layers, fixed=fixed,
                          atlas=atlas_all, lore_c=lore_c,
                          lore_t=card["lore"]["triggered"])
        print(f"    {inst:<8}{card_sys:>9}{post_hx:>9}{lore_c:>8}"
              f"{seeds:>7}{layers:>8}{fixed:>8}{card['lore']['triggered']:>10}")

    print("\n    FIXED = paid on EVERY message before any history, memory, or live state.")
    print("    lore_trig = keyword-gated, not always paid (correctly conditional).")

    # --- 3. card field detail ---------------------------------------------------------
    print("\n[3] CARD FIELD BREAKDOWN (which part of the card you pay for every turn)")
    for inst in CARDS:
        c = rows[inst]["card"]
        parts = ", ".join(f"{k}={v}" for k, v in
                         sorted(c["fields"].items(), key=lambda kv: -kv[1]))
        print(f"    {inst:<8} {parts}")

    # --- 4. unread card fields -------------------------------------------------------
    print("\n[4] CARD FIELDS NEVER READ BY load_character()  (file weight, not tokens)")
    any_unread = False
    for inst in CARDS:
        u = rows[inst]["card"]["unread"]
        if u:
            any_unread = True
            tot = sum(u.values())
            det = ", ".join(f"{k}={v}" for k, v in sorted(u.items(), key=lambda kv: -kv[1]))
            print(f"    {inst:<8} {tot:>6} tok equiv unreachable — {det}")
    if not any_unread:
        print("    (none above threshold)")

    # --- 5. cross-layer sentence duplication -----------------------------------------
    print("\n[5] DUPLICATED INSTRUCTIONS ACROSS PRESET LAYERS")
    sent_index = {}
    for f in layer_files:
        for s in norm_sentences(read(f)):
            sent_index.setdefault(s, set()).add(f)
    dups = {s: fs for s, fs in sent_index.items() if len(fs) > 1}
    # exclude the monolith from pair counting separately
    live_layers = [f for f in layer_files if f != "preset.txt"]
    dup_live = {s: fs for s, fs in dups.items()
                if len({x for x in fs if x != "preset.txt"}) > 1}
    print(f"    exact repeated sentences among live layers: {len(dup_live)}")
    wasted = sum(est_tokens(s) * (len({x for x in fs if x != 'preset.txt'}) - 1)
                 for s, fs in dup_live.items())
    print(f"    tokens paid more than once per message:      ~{wasted}")
    for s, fs in sorted(dup_live.items(), key=lambda kv: -est_tokens(kv[0]))[:8]:
        f2 = sorted(x for x in fs if x != "preset.txt")
        print(f"      [{est_tokens(s):>3}t] {', '.join(f2)}")
        print(f"            \"{s[:96]}...\"")

    # --- 6. monolith drift -----------------------------------------------------------
    print("\n[6] IS THE MONOLITH preset.txt STILL A SAFE FALLBACK?")
    mono = read("preset.txt")
    mono_s = set(norm_sentences(mono))
    core_s = set(norm_sentences(read("preset-core.txt")))
    rp_s = set(norm_sentences(read("preset-rp.txt")))
    exp_s = set(norm_sentences(read("preset-explicit.txt")))
    union = core_s | rp_s | exp_s | set(norm_sentences(read("preset-stepped.txt")))
    only_mono = mono_s - union
    only_layers = union - mono_s
    print(f"    preset.txt sentences:                 {len(mono_s)}")
    print(f"    in preset.txt but in NO live layer:   {len(only_mono)}"
          f"  (~{sum(est_tokens(s) for s in only_mono)}t of orphaned rules)")
    print(f"    in live layers but NOT in preset.txt: {len(only_layers)}"
          f"  (~{sum(est_tokens(s) for s in only_layers)}t the fallback would LOSE)")

    # --- 7. layer <-> card duplication -----------------------------------------------
    print("\n[7] CARD vs PRESET-LAYER OVERLAP (same rule stated twice per message)")
    for inst, cardname in CARDS.items():
        raw = json.loads((BASE / cardname).read_text(encoding="utf-8"))
        d = raw.get("data", raw)
        cardtext = " ".join(str(d.get(f) or "") for f in
                            ("system_prompt", "description", "personality",
                             "scenario", "mes_example", "post_history_instructions"))
        cs = shingles(cardtext)
        stack_text = " ".join(read(f) for f in STACKS[inst])
        ls = shingles(stack_text)
        inter = cs & ls
        if inter:
            print(f"    {inst:<8} {len(inter):>4} shared 8-gram(s) between card and layers")

    # --- 8. cache-prefix split --------------------------------------------------------
    # Block order in assemble_messages (bot.py 4430-4760):
    #   1 card system block        STATIC
    #   2 SETTING                  static (no setting.txt in repo -> 0)
    #   3 people / projects        static (TTL file reads)
    #   4 ATLAS  random.sample()   <-- VOLATILE: re-randomized every message
    #   5 capabilities             static
    #   6 conversation history     append-only
    #   7 ~20 per-turn state blocks VOLATILE
    #   8 post_history + PRESET LAYERS   STATIC, but sits behind all of the above
    #   9 environment_note (clock)  VOLATILE (minute resolution)
    print("\n[8] CACHE-PREFIX SPLIT — static tokens stranded behind volatile blocks")
    hdr8 = (f"    {'inst':<8}{'cacheable':>11}{'stranded':>10}"
            f"{'FIXED':>8}{'stranded_%':>12}")
    print(hdr8)
    print("    " + "-" * (len(hdr8) - 4))
    tot_str = 0
    for inst in CARDS:
        r = rows[inst]
        people = est_tokens(read(f"{inst}/people.txt"))
        projects = est_tokens(read(f"{inst}/projects.txt"))
        prefix = r["card_sys"] + people + projects       # blocks 1-3, before ATLAS
        stranded = r["layers"] + r["post_hx"]            # block 8: static, uncacheable
        tot_str += stranded
        pct = 100.0 * stranded / r["fixed"]
        print(f"    {inst:<8}{prefix:>11}{stranded:>10}{r['fixed']:>8}{pct:>11.0f}%")
    print(f"\n    Stranded = invariant text re-billed at full rate every message because")
    print(f"    a random.sample() (block 4) and ~20 volatile blocks precede it.")
    print(f"    fleet stranded-static per message round: {tot_str} tok")

    # --- 9. the ATLAS cache-buster ----------------------------------------------------
    print("\n[9] ATLAS — the cheapest cache breaker on the fleet")
    for inst in CARDS:
        lines = [l for l in read(f"{inst}/atlas.txt").splitlines()
                 if l.strip() and not l.strip().startswith("#")]
        block = est_tokens(", ".join(lines[:6]))
        print(f"    {inst:<8} {len(lines):>3} places, samples 6 -> ~{block:>3}t "
              f"re-randomized per message")

    print("\n" + "=" * 78)
    print("TOTALS")
    print("=" * 78)
    tot = sum(r["fixed"] for r in rows.values())
    print(f"    fleet fixed cost per message (7 bots, 1 msg each): {tot:>7} tok")
    print(f"    mean per instance:                                 {tot // 7:>7} tok")


if __name__ == "__main__":
    main()
