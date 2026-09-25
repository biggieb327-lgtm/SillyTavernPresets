#!/usr/bin/env python3
"""weekly_audit.py -- weekly audit of the fleet's message logs (MESSAGE_LOG_DESIGN.md).

Runs on the VPS from root's crontab. Standard library only, so the system python3 runs it
(no bot venv needed):

  python3 weekly_audit.py                  # every instance under /opt/telegram-bots
  python3 weekly_audit.py --notify nora    # also send the summary through nora's bot
  python3 weekly_audit.py --dry-run        # print the report; write and send nothing

An instance is audited when its msglog/ holds day files from the last --days days, i.e.
the bots that have the message log turned on and were talked to. Everything is fixed
rules over rpzlib.py's metrics; no model is called.

Every rule result has exactly one of four statuses, and they are counted separately:
  FLAG         the rule's condition was observed -- something to look at
  OK           checked, and the condition was not observed
  BASELINE     a rule with a numeric threshold, shown but not judged until
               --baseline-weeks earlier reports exist (the thresholds are untested on real
               bot output; the first weeks show what normal looks like for each bot)
  NOT CHECKED  could not be determined: too few replies, a file missing or unreadable
Exit codes: 0 report written, nothing flagged; 1 report written, at least one FLAG;
2 no report could be produced.

Reports go to <base>/audits/<date>.md (+ .json for week-over-week comparison). That folder
is not copied by vps-backup.sh (it copies instance folders and shared/ only), so the
report stays on the VPS like the logs it reads.
"""
import argparse
import json
import random
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rpzlib  # noqa: E402

FLAG, OK, BASELINE, NOT_CHECKED = "FLAG", "OK", "BASELINE", "NOT CHECKED"
STATUS_ORDER = [FLAG, BASELINE, NOT_CHECKED, OK]
MIN_REPLIES = 8          # below this, rut and format rules are NOT CHECKED
MIN_PROACTIVE = 4
TELEGRAM_LIMIT = 3900    # stay under Telegram's 4096-char message cap

DAY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
PLACEHOLDER_RE = re.compile(r"^\[(sent a |reacted )")
LEAK_RE = re.compile(r"</?think>|Thinking Process:", re.I)
MOJIBAKE_RE = re.compile("â€|Ã[\u0080-¿]|Â[ -¿]")
ASSISTANT_RE = re.compile(
    r"\b(let me know if|i'?m here (?:to help|for you)|feel free to|i hope (?:this|that) helps"
    r"|is there anything else|as an ai)\b", re.I)
NEG_DIRECTIVE_RE = re.compile(r"^\s*(?:[-*•]\s+)?(Never|Don't|Do not|Avoid|No)\b")
FIRST_PERSON_RE = re.compile(r"\b(I|I'm|I've|I'd|I'll|me|my|mine)\b")
ACTION_BEAT_RE = re.compile(r"\*[^*\n]{2,}\*")
MARKDOWN_RE = re.compile(r"\*|^#{1,6}\s|(?<!\w)_[^_\n]+_(?!\w)", re.M)
NOISY_BANNED = {"vice", "vise", "asset", "electric", "slick", "architecture", "the weight of"}


def res(rule, status, detail, fix=""):
    return {"rule": rule, "status": status, "detail": detail, "fix": fix}


def gated(rule, observed_bad, detail, fix, ready):
    """A thresholded rule: judged only once enough earlier reports exist."""
    if not ready:
        return res(rule, BASELINE, detail + (" (would flag)" if observed_bad else ""))
    return res(rule, FLAG if observed_bad else OK, detail, fix if observed_bad else "")


# --- per-character format contracts, each read from that bot's preset-<name>.txt ------
# (share_function, threshold, what the share measures, positively worded fix)
def _share(replies, pred):
    return sum(1 for r in replies if pred(r)) / len(replies)


CONTRACTS = {
    "priya": [
        ("priya-lowercase", lambda rs: _share(rs, lambda r: r[:1].isupper()), 0.20,
         "replies opening with a capital letter",
         "preset-priya.txt: every reply stays lowercase from the first letter."),
        ("priya-no-markdown", lambda rs: _share(rs, lambda r: bool(MARKDOWN_RE.search(r))), 0.05,
         "replies with markdown or asterisks",
         "preset-priya.txt: plain text only, the way she'd type it."),
    ],
    "emily": [
        ("emily-third-person", lambda rs: _share(
            rs, lambda r: bool(FIRST_PERSON_RE.search(rpzlib.narration(r)))), 0.25,
         "replies with first-person narration outside quotes",
         "preset-emily.txt: narration stays in third person; 'I' lives inside her quoted lines."),
    ],
    "marcus": [
        ("marcus-third-person", lambda rs: _share(
            rs, lambda r: bool(FIRST_PERSON_RE.search(rpzlib.narration(r)))), 0.25,
         "replies with first-person narration outside quotes",
         "preset-marcus.txt: narration stays in third person; 'I' lives inside his quoted lines."),
    ],
    "cass": [
        ("cass-no-narration", lambda rs: _share(rs, lambda r: bool(ACTION_BEAT_RE.search(r))), 0.05,
         "replies with *action beats*",
         "preset-cass.txt: she texts -- every reply is words she'd send, with no stage directions."),
    ],
    "bonnie": [
        ("bonnie-length", lambda rs: _share(
            rs, lambda r: len([p for p in re.split(r"\n\s*\n", r) if p.strip()]) <= 2), 0.50,
         "replies of 1-2 paragraphs",
         "preset-bonnie.txt: restate that her card's 3-6 paragraphs win over the core's shorter default."),
    ],
    "nora": [
        ("nora-questions", lambda rs: _share(rs, lambda r: r.rstrip().endswith("?")), 0.50,
         "replies ending on a question",
         "preset-nora.txt: curiosity shows as her own stories and reactions, with a question when she means one."),
    ],
}


# --- loading ----------------------------------------------------------------------------

def read_env(path):
    env = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def instances(base):
    return sorted(d for d in base.iterdir() if d.is_dir() and (d / "state.json").is_file())


def load_chats(inst, since):
    """{chat_id: [record, ...]} from day files dated >= since; plus unreadable-line count."""
    chats, bad = {}, 0
    root = inst / "msglog"
    if not root.is_dir():
        return chats, bad
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            m = DAY_RE.match(f.name)
            try:
                if not m or date.fromisoformat(m.group(1)) < since:
                    continue
            except ValueError:  # e.g. 2026-13-40.jsonl -- not a day file
                continue
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                if isinstance(rec, dict):
                    chats.setdefault(folder.name, []).append(rec)
    return chats, bad


def replies_of(recs, kinds=("chat", "group", "proactive")):
    out = []
    for r in recs:
        mes = r.get("mes") or ""
        if r.get("is_user") or r.get("is_system") or r.get("kind") not in kinds:
            continue
        if mes and not PLACEHOLDER_RE.match(mes):
            out.append(mes)
    return out


# --- rules --------------------------------------------------------------------------------

def tier1(raw):
    """Bugs: any hit is a finding, no baseline. Scans the raw text -- rpzlib.clean() would
    delete a leaked think block before any other check could see it."""
    out = []
    n = sum(1 for m in raw if LEAK_RE.search(m))
    out.append(res("reasoning-leak", FLAG if n else OK, f"{n} of {len(raw)} replies contain think tags or 'Thinking Process:'",
                   "A leak got past _looks_like_reasoning_leak: check leak_samples/ and add the case to tests/leak_corpus/." if n else ""))
    n = sum(1 for m in raw if MOJIBAKE_RE.search(m))
    out.append(res("mojibake", FLAG if n else OK, f"{n} replies contain mojibake sequences",
                   "_fix_mojibake missed a sequence: add it to its table." if n else ""))
    hits = {}
    for m in raw:
        for h in ASSISTANT_RE.findall(m):
            hits[h.lower()] = hits.get(h.lower(), 0) + 1
    detail = ", ".join(f'"{k}" x{v}' for k, v in sorted(hits.items(), key=lambda kv: -kv[1])) or "none"
    out.append(res("assistant-voice", FLAG if hits else OK, f"assistant phrases that got past the filters: {detail}",
                   "Openers: extend _SLOP_OPENER_RE. Closers: add a preset-<name>.txt rule worded as what she does "
                   "instead, e.g. 'replies end on her own thought, a detail, or a question she means'." if hits else ""))
    return out


def banned_rule(clean, banned):
    hits = rpzlib.scan_banned(clean, banned)
    if not hits:
        return res("banned-phrases", OK, "no banned phrases")
    parts = [f'"{k}" x{len(v)}' + (" (often literal)" if k in NOISY_BANNED else "")
             for k, v in sorted(hits.items(), key=lambda kv: -len(kv[1]))]
    return res("banned-phrases", FLAG, ", ".join(parts[:10]),
               "For each real hit, add a positively worded substitute to preset-<name>.txt "
               "(what she says instead), not a 'never say X' line.")


def rut_rules(clean, ready):
    if len(clean) < MIN_REPLIES:
        return [res("loops", NOT_CHECKED, f"only {len(clean)} replies (need {MIN_REPLIES})"),
                res("openers", NOT_CHECKED, f"only {len(clean)} replies (need {MIN_REPLIES})")]
    nov = [rpzlib.novelty("\n\n".join(clean[max(0, i - 5):i]), clean[i]) for i in range(1, len(clean))]
    fresh = sorted(nov)[int(len(nov) * 0.75)]
    loops = sum(1 for v in nov if v < fresh * 0.65)
    share = loops / len(nov)
    out = [gated("loops", share > 0.15, f"{loops} of {len(nov)} replies read as loops ({share:.0%}; median novelty {median(nov):.2f})",
                 "Replies are recycling recent ones: check the sampler repetition settings and whether a preset rule "
                 "pushes toward one shape.", ready)]
    firsts = [(rpzlib.WORDS.findall(r.lower()) or [""])[0] for r in clean]
    top = max(set(firsts), key=firsts.count)
    fshare = firsts.count(top) / len(firsts)
    out.append(gated("openers", fshare >= 0.30, f'"{top}" starts {fshare:.0%} of replies',
                     f"Add to preset-<name>.txt: 'openers vary -- a reaction, a detail from her day, or straight into the "
                     f"point' (current rut: \"{top}\").", ready))
    return out


def echo_scores(src, replies):
    """rpzlib echo, as its `echo` command computes it: source-supplied share minus the share a
    word-shuffled copy supplies, so shared vocabulary alone scores ~0."""
    rng = random.Random(0)
    chunks = [src[i:i + 20000] for i in range(0, len(src), 20000)]
    ctrl = []
    for c in chunks:
        w = c.split()
        rng.shuffle(w)
        ctrl.append(" ".join(w))
    return [max(0.0, (1 - min(rpzlib.novelty(c, r) for c in chunks))
                - (1 - min(rpzlib.novelty(c, r) for c in ctrl))) for r in replies]


def echo_rule(card, clean, ready):
    if card is None:
        return res("card-echo", NOT_CHECKED, "card not found or unreadable")
    if len(clean) < MIN_REPLIES:
        return res("card-echo", NOT_CHECKED, f"only {len(clean)} replies (need {MIN_REPLIES})")
    worst = []
    for name, src in (("card body", "\n".join(card.get(f) or "" for f in ("description", "personality", "scenario"))),
                      ("mes_example", card.get("mes_example") or "")):
        if src.strip():
            worst.append((max(echo_scores(src, clean)), name))
    if not worst:
        return res("card-echo", NOT_CHECKED, "card has no body or mes_example text")
    score, name = max(worst)
    return gated("card-echo", score >= 0.15, f"highest echo {score:.2f} from {name} (0.15+ reads as copied lines)",
                 f"Replies are lifting lines from the card's {name}: rewrite that passage so it describes "
                 f"her behavior instead of scripting her words.", ready)


def contract_rules(name, clean, ready):
    out = []
    for rule, fn, threshold, what, fix in CONTRACTS.get(name, []):
        if len(clean) < MIN_REPLIES:
            out.append(res(rule, NOT_CHECKED, f"only {len(clean)} replies (need {MIN_REPLIES})"))
            continue
        share = fn(clean)
        out.append(gated(rule, share > threshold, f"{share:.0%} {what} (limit {threshold:.0%})", fix, ready))
    return out


def proactive_rule(recs, clean_chat, ready):
    pro = [rpzlib.clean(m) for m in replies_of(recs, kinds=("proactive",))]
    if len(pro) < MIN_PROACTIVE or len(clean_chat) < MIN_REPLIES:
        return res("proactive-staleness", NOT_CHECKED,
                   f"{len(pro)} proactive / {len(clean_chat)} chat replies (need {MIN_PROACTIVE} / {MIN_REPLIES})")
    p = median(rpzlib.novelty("\n\n".join(pro[max(0, i - 5):i]), pro[i]) for i in range(1, len(pro)))
    c = median(rpzlib.novelty("\n\n".join(clean_chat[max(0, i - 5):i]), clean_chat[i]) for i in range(1, len(clean_chat)))
    return gated("proactive-staleness", p < c * 0.65,
                 f"proactive messages median novelty {p:.2f} vs replies {c:.2f}",
                 "Scheduled messages reuse one shape: vary the triggers in morning_briefing_job / vigil_checkin_job, "
                 "or give her day more to report.", ready)


def static_rules(inst, env, prior_card, ready):
    out, metrics = [], {}
    layers = [p.strip() for p in (env.get("PRESET_FILES") or env.get("PRESET_FILE") or "preset.txt").split(",") if p.strip()]
    neg, missing = [], []
    for layer in layers:
        p = inst / layer
        if not p.is_file():
            missing.append(layer)
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if NEG_DIRECTIVE_RE.match(line):
                neg.append(f"{layer}:{i}")
    if missing and len(missing) == len(layers):
        out.append(res("preset-negative-directives", NOT_CHECKED, "no preset layer files found: " + ", ".join(missing)))
    else:
        out.append(res("preset-negative-directives", FLAG if neg else OK,
                       (", ".join(neg) if neg else "none") + (f" (missing: {', '.join(missing)})" if missing else ""),
                       "Rewrite each as the behavior wanted (define-by-positive-substitution): naming the thing to "
                       "avoid activates it in a reasoning model's trace." if neg else ""))

    card_path = inst / env["CHARACTER_CARD"] if env.get("CHARACTER_CARD") else None
    card = None
    if card_path and card_path.is_file():
        try:
            card = rpzlib.load_card(str(card_path))
        except (OSError, ValueError):
            card = None
    if card is None:
        out.append(res("card-regression", NOT_CHECKED, "CHARACTER_CARD not set in .env, or the card is missing/unreadable"))
        return out, metrics, None
    metrics = {
        "non_ascii": sum(1 for _, s in rpzlib.walk_strings(card) for ch in s if ord(ch) > 127),
        "perm_tokens": sum(len(card.get(f) or "") // 4 for f in rpzlib.PERMANENT),
        "lore_missing": sum(1 for e in rpzlib.entries_of(card) if any(k not in e for k in rpzlib.LORE_REQ)),
    }
    shown = ", ".join(f"{k}={v}" for k, v in metrics.items())
    if not prior_card:
        out.append(res("card-regression", BASELINE, f"{shown} (first week recorded)"))
    else:
        worse = [f"{k} {prior_card.get(k)} -> {v}" for k, v in metrics.items()
                 if isinstance(prior_card.get(k), int) and v > prior_card[k]]
        out.append(res("card-regression", FLAG if worse else OK, ", ".join(worse) if worse else shown,
                       "The card changed for the worse since last week: non-ASCII breaks the importer, permanent "
                       "tokens are paid every message, and every lorebook entry needs all 15 fields." if worse else ""))
    return out, metrics, card


def blending_rule(texts, ready):
    rooms = {n: rpzlib.pick_chunks(t) for n, t in texts.items() if len(t) >= 4000}
    if len(rooms) < 2:
        return res("voice-blending", NOT_CHECKED, f"{len(rooms)} bot(s) with 4000+ chars of replies (need 2)")
    within = {n: median(rpzlib.ncd(a, b) for i, a in enumerate(cs) for b in cs[i + 1:])
              for n, cs in rooms.items() if len(cs) >= 2}
    pairs = []
    names = sorted(rooms)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if a in within and b in within:
                cross = median(rpzlib.ncd(x, y) for x in rooms[a] for y in rooms[b])
                pairs.append((cross - (within[a] + within[b]) / 2, a, b))
    if not pairs:
        return res("voice-blending", NOT_CHECKED, "no bot had two samples to set its own baseline")
    pairs.sort()
    gap, a, b = pairs[0]
    detail = "closest pairs: " + ", ".join(f"{x}<->{y} gap {g:+.3f}" for g, x, y in pairs[:3])
    return gated("voice-blending", gap < 0.02, detail,
                 f"{a} and {b} are converging on one voice: strengthen what's distinct in their "
                 f"preset-<name>.txt layers.", ready)


# --- report -------------------------------------------------------------------------------

def run_audit(base, today, days=7, baseline_weeks=3, banned_path=None):
    """Return (report_markdown, summary_text, data_for_json, exit_code)."""
    audits = base / "audits"
    prior = sorted(p for p in audits.glob("*.json") if p.stem < today.isoformat()) if audits.is_dir() else []
    ready = len(prior) >= baseline_weeks
    last = {}
    if prior:
        try:
            last = json.loads(prior[-1].read_text(encoding="utf-8")).get("instances", {})
        except (OSError, ValueError):
            last = {}
    banned = rpzlib.load_banned(banned_path)
    since = today - timedelta(days=days - 1)
    sections, skipped, data, texts = [], [], {}, {}
    for inst in instances(base):
        chats, bad = load_chats(inst, since)
        if not chats:
            skipped.append(f"{inst.name}: no message-log files since {since} (logging off, or nobody talked to it)")
            continue
        env = read_env(inst / ".env")
        results, metrics, card = [], {}, None
        st, metrics, card = static_rules(inst, env, (last.get(inst.name) or {}).get("card"), ready)
        all_raw = []
        for cid, recs in sorted(chats.items()):
            raw = replies_of(recs)
            all_raw += raw
            clean = [c for c in (rpzlib.clean(m) for m in raw) if c]
            chat_only = [rpzlib.clean(m) for m in replies_of(recs, kinds=("chat", "group"))]
            chat_only = [c for c in chat_only if c]
            rs = tier1(raw) + [banned_rule(clean, banned)] + rut_rules(clean, ready) \
                + contract_rules(inst.name, clean, ready) + [echo_rule(card, clean, ready),
                                                              proactive_rule(recs, chat_only, ready)]
            for r in rs:
                r["where"] = f"{inst.name} chat {cid}" + (" (group)" if cid.startswith("-") else "")
            results += rs
            if not cid.startswith("-"):
                texts[inst.name] = texts.get(inst.name, "") + "\n\n".join(clean)
        for r in st:
            r["where"] = inst.name
        results = st + results
        persona = 0
        try:
            state = json.loads((inst / "state.json").read_text(encoding="utf-8"))
            cutoff = (today - timedelta(days=days)).toordinal()
            persona = sum(1 for ts in state.get("error_counts", {}).get("persona_break", [])
                          if date.fromtimestamp(ts).toordinal() > cutoff)
        except (OSError, ValueError, TypeError):
            persona = None
        data[inst.name] = {"card": metrics, "replies": len(all_raw), "persona_break": persona}
        sections.append((inst.name, results, len(all_raw), bad, persona))

    blend = blending_rule(texts, ready)
    blend["where"] = "fleet"
    all_results = [r for _, rs, *_ in sections for r in rs] + [blend]
    counts = {s: sum(1 for r in all_results if r["status"] == s) for s in STATUS_ORDER}

    lines = [f"# Weekly message audit -- {today}", "",
             f"Window: {since} to {today} ({days} days). "
             + ("Thresholds active." if ready else
                f"Baseline mode: {len(prior)} of {baseline_weeks} earlier reports, so threshold rules are shown, not judged."),
             "", "Totals: " + ", ".join(f"{counts[s]} {s}" for s in STATUS_ORDER), ""]
    # A shared preset layer loaded by six bots is one finding, not six: group identical
    # (rule, detail) flags and name every bot they came from.
    flagged, seen = [], {}
    for r in all_results:
        if r["status"] != FLAG:
            continue
        key = (r["rule"], r["detail"])
        if key in seen:
            seen[key]["where"] += ", " + r["where"]
        else:
            seen[key] = dict(r)
            flagged.append(seen[key])
    lines.append("## What could be improved")
    lines += [f"- **{r['where']} / {r['rule']}**: {r['detail']}\n  - {r['fix']}" for r in flagged] or ["- Nothing flagged this week."]
    for name, rs, n, bad, persona in sections:
        lines += ["", f"## {name}",
                  f"{n} replies audited" + (f"; {bad} unreadable log lines" if bad else "")
                  + (f"; persona-break filter fired {persona}x" if persona else
                     "; persona-break count unavailable" if persona is None else "")]
        for s in STATUS_ORDER[1:]:
            lines += [f"- {s}: {r['rule']} ({r['where']}) -- {r['detail']}" for r in rs if r["status"] == s]
    lines += ["", "## Fleet", f"- {blend['status']}: voice-blending -- {blend['detail']}"]
    if skipped:
        lines += ["", "## Skipped"] + [f"- {s}" for s in skipped]
    report = "\n".join(lines) + "\n"

    summary = [f"Weekly audit {today}: " + ", ".join(f"{counts[s]} {s}" for s in STATUS_ORDER)]
    summary += [f"- {r['where']} / {r['rule']}: {r['detail']}" for r in flagged] or ["Nothing flagged."]
    if not ready:
        summary.append(f"(baseline week {len(prior) + 1} of {baseline_weeks}: threshold rules not judged yet)")
    if skipped:
        summary.append(f"Skipped: {', '.join(s.split(':')[0] for s in skipped)}")
    summary.append(f"Full report: {audits / (today.isoformat() + '.md')}")
    text = "\n".join(summary)
    if len(text) > TELEGRAM_LIMIT:
        text = text[:TELEGRAM_LIMIT - 60] + "\n... (truncated; see the full report)"
    payload = {"date": today.isoformat(), "instances": data}
    if not sections:
        text = (f"Weekly audit {today}: NOTHING AUDITED -- no bot has message-log files since {since}. "
                f"If logging is meant to be on, check /msglog on each bot.\n" + text)
        return report, text, payload, 2
    return report, text, payload, 1 if flagged else 0


def notify(base, instance, text):
    """Send `text` through `instance`'s bot to its owner. Returns an error string or None."""
    inst = base / instance
    env = read_env(inst / ".env")
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat = env.get("OWNER_CHAT_ID")
    if not chat and (inst / "owner_chat.txt").is_file():
        chat = (inst / "owner_chat.txt").read_text(encoding="utf-8").strip()
    if not token or not chat:
        return f"no TELEGRAM_BOT_TOKEN or owner chat for {instance}"
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=body, timeout=20) as r:
            if r.status != 200:
                return f"Telegram answered HTTP {r.status}"
    except Exception as e:  # report the failure; never print the token
        return f"send failed: {type(e).__name__}"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Weekly audit of the fleet's message logs.")
    ap.add_argument("--base", default="/opt/telegram-bots")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--baseline-weeks", type=int, default=3)
    ap.add_argument("--banned", help="banned list file, one regex per line (default: rpzlib's list)")
    ap.add_argument("--notify", metavar="INSTANCE", help="send the summary through this instance's bot")
    ap.add_argument("--today", help="YYYY-MM-DD, for re-running a past week")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    base = Path(a.base)
    if not base.is_dir():
        print(f"weekly_audit: {base} does not exist", file=sys.stderr)
        return 2
    today = date.fromisoformat(a.today) if a.today else date.today()
    report, summary, payload, code = run_audit(base, today, a.days, a.baseline_weeks, a.banned)
    if a.dry_run:
        print(report)
        return code
    out = base / "audits"
    out.mkdir(mode=0o700, exist_ok=True)
    (out / f"{today}.md").write_text(report, encoding="utf-8")
    # A week with nothing audited must not count toward the baseline, but the owner still
    # hears about it: a silent week and a broken message log should not look the same.
    if code != 2:
        (out / f"{today}.json").write_text(json.dumps(payload, ensure_ascii=True, indent=1), encoding="utf-8")
    print(summary)
    if a.notify:
        err = notify(base, a.notify, summary)
        if err:
            print(f"weekly_audit: notify skipped -- {err}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
