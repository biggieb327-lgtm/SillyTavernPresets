#!/usr/bin/env python3
"""Search the operational log by describing the symptom in your own words.

    python3 .claude/tools/oplog-search.py "two copies of the bot seem to be running"

WHY THIS AND NOT grep. Measured 2026-08-21 over 71 rows with queries frozen before the
run (.claude/experiments/2026-08-21-oplog-retrieval/): grep finds the right row 9 times
in 10, so recall was never the problem — but a grep hit means reading 8.9 rows on
average and up to 21 to find it. This ranks instead: 7/10 in the top 5, every hit at
rank 1-4. It is a precision tool, not a recall tool, and it does not replace grep when
you already know the exact string.

WHY NOT EMBEDDINGS. Same experiment: the recall ceiling is nearly reached by grep alone,
and the only clear win case is a jargon gap (the log says "offset-naive", you say
"timezone"). Buying that would cost an API key in a repo with a secret-scan eval, or a
~90MB model in git, plus an index and a model-fingerprint guard — the bots' whole
embedding subsystem, for 71 rows. Rejected on cost, not on accuracy. RESULTS.md has the
numbers and the limits, including the arm that could not be run.

Scores CELLS, not whole rows, and credits the row. That one change took BM25 from 5/10
to 7/10 in the experiment — chunk size mattered more than the algorithm.

No dependencies, no network, no key. Stdlib only.
"""
import math
import re
import sys
from collections import Counter
from pathlib import Path

LOG = Path(".claude/memory/operational-log.md")
SPLIT = re.compile(r"(?<!\\)\|")          # a separator is a pipe that is not escaped
TOK = re.compile(r"[a-z][a-z0-9_-]{2,}")
TOP = 5


def tokens(s):
    return TOK.findall(s.lower())


def load():
    """Rows as (date, cells). Raises rather than returning empty — a search tool that
    silently finds nothing is indistinguishable from a corpus with no answer, which is
    the failure mode this repo keeps paying for (C13)."""
    if not LOG.is_file():
        sys.exit(f"oplog-search: {LOG} not found — run from the repo root")
    rows = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| 20"):
            continue
        cells = [c.strip() for c in SPLIT.split(line)]
        cells = [c for c in cells if c]
        if len(cells) < 2:
            continue
        rows.append((cells[0], cells[1:]))
    if not rows:
        sys.exit("oplog-search: parsed 0 rows out of the log. The row format changed and "
                 "this tool cannot read it — fix the parser rather than trusting an empty "
                 "result, which is not the same as 'nothing matched'.")
    return rows


def search(query, rows):
    chunks = [(i, c) for i, (_, cells) in enumerate(rows) for c in cells]
    docs = [tokens(c) for _, c in chunks]
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n
    df = Counter()
    for d in docs:
        df.update(set(d))
    q = tokens(query)
    if not q:
        sys.exit("oplog-search: give me some words to search for")
    k1, b = 1.5, 0.75
    scored = []
    for i, d in enumerate(docs):
        tf = Counter(d)
        s = 0.0
        for t in q:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
        if s > 0:
            scored.append((s, i))
    scored.sort(reverse=True)
    out, seen = [], set()
    for s, i in scored:                    # best cell wins, one entry per row
        r = chunks[i][0]
        if r in seen:
            continue
        seen.add(r)
        out.append((s, r))
        if len(out) >= TOP:
            break
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip().splitlines()[0] + "\n\nusage: oplog-search.py \"symptom in your own words\"")
    query = " ".join(sys.argv[1:])
    rows = load()
    hits = search(query, rows)
    if not hits:
        print(f"no row shares a word with that query ({len(rows)} rows searched).")
        print("Try the symptom in different words, or grep if you know the exact string.")
        return
    print(f"{len(rows)} rows searched — top {len(hits)} by relevance:\n")
    for rank, (score, i) in enumerate(hits, 1):
        date, cells = rows[i]
        failure = re.sub(r"[*`]", "", cells[0])
        link = re.search(r"\(incidents/([^)]+)\)", cells[0])
        print(f"  #{rank}  {date}  (score {score:.1f})")
        print(f"      {failure[:150]}{'…' if len(failure) > 150 else ''}")
        if link:
            print(f"      full record: .claude/memory/incidents/{link.group(1)}")
        print()


if __name__ == "__main__":
    main()
