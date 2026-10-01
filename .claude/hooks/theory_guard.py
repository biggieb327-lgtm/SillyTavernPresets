#!/usr/bin/env python3
"""Theory guard — C5: label a theory as a theory until evidence arrives.

Stop hook. Catches one mechanizable slice of C5: asserting what code *does* at runtime
without hedging. Two kinds of line are checked:

1. A claim whose subject is **code-shaped** — backticked, snake_case, or called with `()` —
   followed by a behavior verb (returns, removes, strips, catches, writes, ...). These are
   checked against the session transcript (`transcript_path`), which already records every
   tool call and its output:
     run   the name appears in a Bash command that executed something (not only grep/cat/…)
           and did not error  -> PASS: the claim was checked by running it
     read  the name appears only in files read, searches, or tool output  -> BLOCK: source
           tells you what code says, not what it produces
     none  the name appears in no tool call or output this session  -> BLOCK: never looked
2. A claim whose subject is a plain word ("the bot output ...") — no name to look up, so the
   original rule applies: BLOCK unless hedged.
3. Since 2026-10-01, `check_external`: a claim about a billing or capacity property of an
   external service or the runtime ("bills nothing", "a 16k window", "~1,800 tokens over").
   No name to look up, so the evidence is a NUMBER: it passes if hedged, sourced (URL or
   file), or one of its numbers was printed by a command executed this session. Rules and
   limits are at `check_external`.

Limits, stated so nobody reads more into a pass than it holds: "run" means the name was
executed in some command this session, not that the command tested the exact behavior now
claimed. A claim that names nothing ("never checked", "nothing like that exists") is C5's
uncovered half; this guard cannot see it, except the billing/capacity slice (3). Nor, since 2026-09-25, a claim built on a noun
phrase ("the bot output always ends on a question"): matching "<word> output" as a verb
blocked correct sentences ("raw model output") far more often than it caught one.

Escape hatch: `# theory-ok`. Hedging ("probably", "[hypothesis]", "source-traced") also
satisfies it. Verify cheaply with `.claude/tools/probe.py`. Fails OPEN on anything unexpected.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from host_guard import last_assistant_text
except ImportError:
    sys.exit(0)

# Plain-word subjects need the third-person verb: "the parser returns" is a claim, while
# "model output" / "bot output" is a noun phrase (2026-09-25: both fired as claims).
# Code-shaped subjects go through CODE_CLAIM, which keeps every verb form.
IDENT = re.compile(
    r'\b([a-z_][a-z0-9_]{2,})\b'
    r'(?:\s*\([^)]*\))?'
    r'\s+'
    r'(?:returns|produces|outputs|causes|results\s+in|'
    r'will\s+(?:return|produce|output|cause|result\s+in)|'
    r'would\s+(?:return|produce|output|cause|result\s+in))\b',
    re.I)

_VERBS = (r'returns?|returned|produces?|produced|outputs?|causes?|caused|results?\s+in|'
          r'removes?|removed|strips?|stripped|deletes?|deleted|writes?|wrote|'
          r'matches?|matched|catches?|caught|flags?|flagged|blocks?|blocked|rejects?|rejected|'
          r'skips?|skipped|drops?|dropped|raises?|raised|fires?|fired|sends?|sent|'
          r'filters?|filtered|ignores?|ignored|leaves?|left')
# Subject is code-shaped: `backticked`, snake_case, or name(...).
CODE_CLAIM = re.compile(
    r'(`[A-Za-z_][\w.]*(?:\([^)`]*\))?`|\b[A-Za-z_]\w*_\w+\b(?:\([^)]*\))?|\b[A-Za-z_]\w*\([^)]*\))'
    r"(?:'s)?\s+(?:" + _VERBS + r'|(?:will|would|should\s+not|does\s+not|doesn\'t)\s+(?:' + _VERBS + r'))\b',
    re.I)
CODE_NAME = re.compile(r'`([A-Za-z_][\w.]*)(?:\([^)`]*\))?`|\b([A-Za-z_]\w*_\w+)\b|\b([A-Za-z_]\w*)\(')

HEDGE = re.compile(
    r'\b(?:probably|likely|might|may\b|could\b|possibly|I think|I believe|'
    r'hypothesis|hypothesize|unverified|uncertain|untested|not sure|unclear|'
    r'suggests?|seems?\s+to|appears?\s+to|in theory|should\s+(?:return|produce|remove|strip|'
    r'catch|write|match|flag|block|skip|drop|raise|fire|send|filter|leave|be)|I expect|'
    r'source-traced|from reading)\b'
    r'|\[hypothesis\]',
    re.I)

# The hook's scope is a claim about a NAMED FUNCTION. Common English words are not function
# names, so when the IDENT "identifier" is one of these AND does not look like code (no `_`,
# not called with `()`), the match is a false positive — e.g. the noun "cause" after a
# possessive ("shares its cause"), or a preposition before a noun ("run with output").
STOPWORDS = frozenset(
    "the a an its it this that these those each one ones our your their his her my "
    "any all some both same such which what who whom whose they them then here there "
    "only also root main first last next same other another every no not "
    "with without from into onto for of by as at to in on via than per".split()
)

# Doc-description sentences describe what a document SAYS, not what code DOES at runtime.
DOCDESC = re.compile(
    r'\b(?:changelog|constraints?|entry|entries|docs?|document|readme|'
    r'note|notes|log|oplog|comment|section|table|row|rule|skill|manual|guide|'
    r'handoff|roadmap|audit|file|header|field|instruction|policy)\b'
    r'[^.]{0,60}?\b'
    r'(?:records?|says?|states?|notes?|documents?|describes?|lists?|covers?|'
    r'flags?|mentions?|explains?|reads?|warns?|specifies|defines?|names?|'
    r'captures?|shows?|reminds?|tells?|spells?\s+out)\b',
    re.I)

CODE_FENCE = re.compile(r'```')
ESCAPE = re.compile(r'#\s*theory-ok\b', re.I)

# Commands that look at code or output without executing the thing named.
LOOK_ONLY = frozenset("grep rg sed cat head tail find ls wc awk less sort uniq cut tr echo "
                      "printf git xargs nl file stat diff".split())
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\s*(?:\n|$)", re.S)


def _looks_like_named_function(match) -> bool:
    """A real target: called with `()`, or a snake_case identifier — not a plain word."""
    ident = match.group(1).lower()
    called = "(" in match.group(0)
    return called or "_" in ident or ident not in STOPWORDS


def _names(line: str) -> list:
    """Code-shaped names in a line, reduced to the part a transcript would contain
    (`bot._strip_slop(...)` -> `_strip_slop`)."""
    out = []
    for m in CODE_NAME.finditer(line):
        raw = next(g for g in m.groups() if g)
        name = raw.split(".")[-1]
        if re.fullmatch(r"[A-Za-z_]\w*", name) and len(name) > 2 and name.lower() not in STOPWORDS:
            out.append(name)
    return list(dict.fromkeys(out))


def check(text: str) -> list:
    """Unhedged behavioral claims in `text`, as (quoted line, [code-shaped names])."""
    if ESCAPE.search(text):
        return []
    found = []
    in_fence = False
    for line in text.splitlines():
        s = line.strip()
        if CODE_FENCE.match(s):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if len(s) < 20 or s.startswith(("$", "|", "#", ">")):
            continue
        if HEDGE.search(s) or DOCDESC.search(s):
            continue
        code_claim = CODE_CLAIM.search(s)
        plain_claim = any(_looks_like_named_function(m) for m in IDENT.finditer(s))
        if code_claim or plain_claim:
            names = _names(s) if code_claim else []
            found.append(("  " + (s[:150] + ("…" if len(s) > 150 else "")), names))
    return found


# --- second classifier: claims about an EXTERNAL or runtime property ------------------------
# C5's uncovered half had a repeat shape with no code name in it (2026-09-04, twice): a vendor's
# billing ("a rejected call bills nothing") and a resource ceiling ("can't fit a 16k fallback,
# ~1,800 over") stated as fact. The first was never checked; the second came from an "e.g." in
# the changelog and the measured window turned out to be ~19,859. Two shapes are checked:
#   billing  a metering verb (bills, billed, charged, metered, counts against ...)
#   capacity a token quantity ("16k", "1,800 tokens", "19,859-token") or a request rate
#            ("60 requests/min", RPM) next to a ceiling word (window, limit, fit, over ...)
# Such a line passes only if it is hedged, cites a source (a URL or a repo file path), or at
# least one of its numbers appears in the output of a command that EXECUTED this session and
# did not error. A number seen only in a file read or a grep does not count: that is the 16k
# case exactly. Limits: "one number was printed" is not "the claim was measured" (an
# arithmetic line passes on one measured operand); vendor-behavior claims with neither a
# billing verb nor a number ("NanoGPT returns 400 on oversize") are not seen.
EXT_BILLING = re.compile(
    r"\b(?:bills?|billed|charged|charges|metered|meters|unmetered|free\s+of\s+charge|"
    r"costs?\s+nothing)\b"
    r"|\b(?:counts?|counted|deducted)\s+(?:against|toward|from)\s+(?:the\s+|your\s+|our\s+|its\s+)?"
    r"(?:weekly\s+|daily\s+|monthly\s+|account\s+)?(?:quota|allowance|balance|bill|credits?)\b", re.I)
EXT_QUANTITY = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:k\b|-?\s*tokens?\b)"
    r"|\b\d[\d,]*\s*(?:requests?|calls?|messages?)\s*(?:/|\s+per\s+)\s*(?:s|sec|second|min|minute|hour|day)\b"
    r"|\b\d[\d,]*\s*(?:RPM|TPM|RPD)\b", re.I)
EXT_CEILING = re.compile(
    r"\b(?:window|context|limit|limits|ceiling|cap|capped|max|maximum|fits?|fitting|over|under|"
    r"exceeds?|exceeded|exceeding|allowance|quota|serves?|served|accepts?|accepted|rejects?|"
    r"rejected|throttled?|rate)\b", re.I)
EXT_HEDGE = re.compile(r"\b(?:unknown|unmeasured|unconfirmed|not\s+(?:yet\s+)?(?:measured|"
                       r"verified|confirmed|checked)|guess(?:ed)?|assum(?:e|ed|ing|ption))\b", re.I)
EXT_SOURCE = re.compile(r"https?://\S+|\b[\w-]+\.(?:md|py|sh|json|example|txt|lock|toml|ya?ml)\b")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?k?", re.I)


def check_external(text: str) -> list:
    """Unhedged, unsourced claims about a billing or capacity property, as (quoted line,
    [numbers on the line]). Independent of check(): it looks for no code name."""
    if ESCAPE.search(text):
        return []
    found = []
    in_fence = False
    for line in text.splitlines():
        s = line.strip()
        if CODE_FENCE.match(s):
            in_fence = not in_fence
            continue
        if in_fence or len(s) < 20 or s.startswith(("$", "|", "#", ">")):
            continue
        if HEDGE.search(s) or EXT_HEDGE.search(s) or DOCDESC.search(s) or EXT_SOURCE.search(s):
            continue
        billing = EXT_BILLING.search(s)
        capacity = EXT_QUANTITY.search(s) and EXT_CEILING.search(s)
        if billing or capacity:
            nums = [m.group(0) for m in NUMBER.finditer(s)]
            found.append(("  " + (s[:150] + ("…" if len(s) > 150 else "")), nums))
    return found


def _number_forms(num: str) -> set:
    """Spellings a printed value could take: "19,859" -> {19,859, 19859}; "16k" -> {16k,
    16000, 16384}."""
    bare = num.replace(",", "").lower()
    forms = {num, bare}
    if bare.endswith("k"):
        try:
            v = float(bare[:-1])
            forms |= {str(int(v * 1000)), str(int(v * 1024))}
        except ValueError:
            pass
    return {f for f in forms if f}


def measured(path: str, nums: list) -> bool:
    """True if any of `nums` appears in the output of a Bash command that executed (not
    only searched or printed files) and did not error, before the final message."""
    if not nums:
        return False
    uses, outputs = {}, []
    for r in _prior_records(path):
        content = (r.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") == "Bash":
                uses[b.get("id")] = str((b.get("input") or {}).get("command", ""))
            elif b.get("type") == "tool_result" and not b.get("is_error"):
                cmd = uses.get(b.get("tool_use_id"))
                if cmd is not None and not _look_only(cmd):
                    outputs.append(_text_of(b.get("content")).replace(",", ""))
    blob = "\n".join(outputs)
    for n in nums:
        for f in _number_forms(n):
            if re.search(r"(?<![\d.])" + re.escape(f.replace(",", "")) + r"(?![\d])", blob):
                return True
    return False


def _look_only(cmd: str) -> bool:
    """True when every command in `cmd` only reads or searches (heredoc bodies ignored)."""
    body = HEREDOC.sub("\n", cmd)
    for seg in re.split(r"\|\||&&|[|;\n]", body):
        words = seg.strip().split()
        while words and ("=" in words[0] or words[0] in ("sudo", "time", "env", "then", "do",
                                                          "done", "fi", "else", "{", "}", "(", ")")):
            words = words[1:]
        if words and words[0] == "cd":
            continue
        if words and os.path.basename(words[0]) not in LOOK_ONLY:
            return False
    return True


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return ""


def _prior_records(path: str) -> list:
    """Transcript records before the final assistant text message ([] if unreadable)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            recs = [json.loads(l) for l in fh if l.strip()]
    except (OSError, ValueError):
        return []
    last_text = max((i for i, r in enumerate(recs)
                     if (r.get("message") or {}).get("role") == "assistant"
                     and any(isinstance(c, dict) and c.get("type") == "text"
                             for c in ((r.get("message") or {}).get("content") or [])
                             if isinstance((r.get("message") or {}).get("content"), list))),
                    default=len(recs))
    return recs[:last_text]


def evidence(path: str, names: list) -> dict:
    """{name: "run" | "read" | "none"} from every tool call and result in the transcript
    before the final assistant message."""
    level = {n: "none" for n in names}
    if not names:
        return level
    uses, errored = {}, set()
    for r in _prior_records(path):
        content = (r.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                uses[b.get("id")] = b
            elif b.get("type") == "tool_result":
                if b.get("is_error"):
                    errored.add(b.get("tool_use_id"))
                text = _text_of(b.get("content"))
                for n in names:
                    if n in text and level[n] == "none":
                        level[n] = "read"
    for uid, b in uses.items():
        inp = b.get("input") or {}
        if b.get("name") == "Bash":
            cmd = str(inp.get("command", ""))
            for n in names:
                if n in cmd:
                    ran = not _look_only(cmd) and uid not in errored
                    level[n] = "run" if ran else ("read" if level[n] == "none" else level[n])
        else:
            blob = json.dumps(inp)
            for n in names:
                if n in blob and level[n] == "none":
                    level[n] = "read"
    return level


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    path = payload.get("transcript_path") or ""
    text = last_assistant_text(path)
    if not text:
        return 0
    found = check(text)
    external = [line + "\n    evidence: no source cited and none of its numbers came from a "
                "command run this session" for line, nums in check_external(text)
                if not measured(path, nums)]
    if not found and not external:
        return 0
    ev = evidence(path, sorted({n for _, names in found for n in names}))
    blocking = []
    for line, names in found:
        if names and all(ev.get(n) == "run" for n in names):
            continue  # every name in the claim was executed earlier this session
        if names:
            why = ", ".join(f"`{n}` " + {"none": "never read or run this session",
                                         "read": "read but never run",
                                         "run": "run"}[ev.get(n, "none")] for n in names)
            line += f"\n    evidence: {why}"
        blocking.append(line)
    if external:
        sys.stderr.write(
            "[theory-guard] C5 (.claude/memory/constraints.md) — a claim about an external or "
            "runtime property (billing, a limit, a window) was stated as fact:\n"
            + "\n".join(external[:3])
            + "\n Measure it and paste the number, cite the source (URL or file), or say it is "
              "unverified. An \"e.g.\" in a doc is an illustration, not a measurement.\n")
    if not blocking:
        return 2 if external else 0
    sys.stderr.write(
        "[theory-guard] C5 (.claude/memory/constraints.md) — a behavioral claim was stated "
        "without hedging:\n" + "\n".join(blocking[:3])
        + "\n Run it (python3 .claude/tools/probe.py 'bot.<fn>(...)') and paste the output, or "
          "hedge: \"should return\", \"I expect\", \"[hypothesis]\", \"source-traced\". Reading "
          "source tells you what code says; only running it tells you what it produces.\n")
    return 2


# ---------------------------------------------------------------------------------------
def _transcript(records):
    import tempfile
    tf = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in records:
        tf.write(json.dumps(r) + "\n")
    tf.close()
    return tf.name


def _run(records):
    import io
    path = _transcript(records)
    old_in, old_err = sys.stdin, sys.stderr
    sys.stdin, sys.stderr = io.StringIO(json.dumps({"transcript_path": path})), io.StringIO()
    try:
        return main()
    finally:
        sys.stdin, sys.stderr = old_in, old_err
        os.unlink(path)


def _say(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _bash(uid, cmd, out, err=False):
    return [{"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": uid, "name": "Bash", "input": {"command": cmd}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": uid, "content": out, "is_error": err}]}}]


def selftest() -> int:
    """Both halves pinned: the line classifier, and the transcript evidence check.
    Run: python3 theory_guard.py --selftest  (run-evals.sh runs it)."""
    cases = [
        # (should_flag?, text)
        (False, "it earns a `C`-number only if a second entry shares its cause."),
        (False, "The constraints entry records the lesson concretely for next time."),
        (False, "The changelog documents why the timeout was raised to thirty seconds."),
        (False, "The root cause was a stale checkout on the VPS."),
        (False, "I ran it and the output shows the same cause we saw yesterday."),
        (False, "This produces cleaner handoffs, probably."),  # hedged
        (False, "- run with output → pass, once the ledger exists."),  # preposition, 2026-09-25
        (False, "`_strip_slop` should leave a trailing phrase alone, source-traced."),
        (False, "It doesn't need the raw model output after all, measured this turn."),  # noun
        (True, "The parser returns an empty list on bad input."),
        (True, "_group_deliver() returns None when the shared ledger is empty."),
        (True, "The function build_prompt produces a truncated block for long cards."),
        (True, "update_cmd causes a repo_not_readable reply on the private repo."),
        (True, "The log can't see what `_strip_persona_breaks` removed from the reply."),
        (True, "`_strip_slop` strips assistant openers anywhere in the reply."),
    ]
    fails = 0
    for want, txt in cases:
        got = bool(check(txt))
        fails += got != want
        print(("PASS" if got == want else "**FAIL**"), "flag=%-5s want=%-5s |" % (got, want), txt[:66])

    claim = "Result: `_strip_persona_breaks` removed the self-reference sentence."
    t_cases = [
        # (want exit, transcript, label)
        (2, [_say(claim)], "never seen -> block"),
        (2, _bash("a", "grep -n _strip_persona_breaks bot.py", "7602:def _strip_persona_breaks") + [_say(claim)],
         "only grepped -> block"),
        (2, _bash("b", "python3 -c 'import bot; bot._strip_persona_breaks(\"x\")'", "Traceback", err=True)
         + [_say(claim)], "ran but errored -> block"),
        (0, _bash("c", "python3 .claude/tools/probe.py 'bot._strip_persona_breaks(\"As an AI. ok.\")'",
                  "  -> 'ok.'") + [_say(claim)], "run via probe.py -> pass"),
        (2, _bash("d", "cat > notes.txt <<'EOF'\n_strip_persona_breaks here\nEOF", "") + [_say(claim)],
         "only written into a heredoc -> block"),
        (2, [_say("The parser returns an empty list whenever the input is bad.")],
         "plain-word claim -> block (no name to look up)"),
    ]
    for want, recs, label in t_cases:
        got = _run(recs)
        fails += got != want
        print(("PASS" if got == want else "**FAIL**"), "exit=%s want=%s |" % (got, want), label)
    print("selftest:", "all green" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
