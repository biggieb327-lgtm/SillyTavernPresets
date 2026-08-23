#!/usr/bin/env python3
"""Stricter grep arm: patterns derived MECHANICALLY from the query text, never chosen
by someone who has read the corpus.

The first run gave grep 10/10, but I picked its patterns — and '429' and 'tz' are
vocabulary you only know from having read the log. That is C4's failure mode being
masked by the experimenter's own contamination. Here a session gets only the words in
its own question.
"""
import re
from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location(
    "base", ".claude/experiments/2026-08-21-oplog-retrieval/run.py")

LOG = Path(".claude/memory/operational-log.md")
ROWS = [l for l in LOG.read_text(encoding="utf-8").splitlines() if l.startswith("| 20")]

QUERIES = [
    ("bot reports conditions for the wrong location", {12}),
    ("character forgets we already discussed something and raises it again", {33}),
    ("generated picture is not the same woman as the reference", {15,22,28,31}),
    ("hitting a rate limit and our own retries make it last longer", {10}),
    ("setting an on/off environment variable had no effect", {8,11}),
    ("crash on startup comparing times with and without timezone info", {68}),
    ("duplicate process fighting over the same telegram token", {45,46,57}),
    ("trimming the prompt throws away recent conversation turns", {53}),
    ("documented rule with nothing enforcing it gets ignored", {65,24}),
    ("check passed because it silently examined nothing", {1,4,37}),
]

STOP = {"bot","the","and","with","for","our","own","not","had","its","it","we","us",
        "make","last","longer","same","because","without","over","gets","was","has"}

def words(q):
    return [w for w in re.findall(r"[a-z]{4,}", q.lower()) if w not in STOP]

print(f"{'#':>2}  {'best query-derived grep':<30} {'rows':>5}  {'verdict':<8}  tried")
print("-"*78)
hits = 0
noise = []
for n,(q,truth) in enumerate(QUERIES,1):
    best=None
    for w in words(q):
        h={i for i,r in enumerate(ROWS) if w in r.lower()}
        if h & truth and (best is None or len(h)<best[1]):
            best=(w,len(h))
    if best:
        hits+=1; noise.append(best[1])
        print(f"{n:>2}  {best[0]:<30} {best[1]:>5}  {'HIT':<8}  {len(words(q))} words")
    else:
        print(f"{n:>2}  {'-':<30} {'-':>5}  {'MISS':<8}  {len(words(q))} words")
print("-"*78)
print(f"    query-derived grep hit rate: {hits}/{len(QUERIES)}")
if noise:
    print(f"    rows returned on a hit: {sum(noise)/len(noise):.1f} avg, "
          f"worst {max(noise)}; {sum(1 for x in noise if x>5)}/{hits} buried in >5 rows")
