#!/usr/bin/env python3
"""Retrieval experiment over the operational log. See PROTOCOL.md — queries and ground
truth were committed BEFORE this ran.

Arms: grep (status quo), TF-IDF cosine, BM25. The embedding arm could not run in this
container: the HuggingFace host is blocked by the egress proxy (httpx.ProxyError 403) and
there is no NANOGPT_API_KEY here.
"""
import math
import re
import subprocess
from collections import Counter
from pathlib import Path

LOG = Path(".claude/memory/operational-log.md")
ROWS = [l for l in LOG.read_text(encoding="utf-8").splitlines() if l.startswith("| 20")]

QUERIES = [
    ("bot reports conditions for the wrong location",              {12},          ["weather", "location", "city"]),
    ("character forgets we already discussed something and raises it again", {33},  ["memory", "forget", "recall"]),
    ("generated picture is not the same woman as the reference",   {15,22,28,31}, ["selfie", "photo", "face"]),
    ("hitting a rate limit and our own retries make it last longer", {10},        ["rate limit", "429", "retry"]),
    ("setting an on/off environment variable had no effect",       {8,11},        ["env var", "flag", "feature"]),
    ("crash on startup comparing times with and without timezone info", {68},     ["timezone", "startup crash", "tz"]),
    ("duplicate process fighting over the same telegram token",    {45,46,57},    ["Conflict", "two process", "poller"]),
    ("trimming the prompt throws away recent conversation turns",  {53},          ["prompt budget", "history", "trim"]),
    ("documented rule with nothing enforcing it gets ignored",     {65,24},       ["enforcement", "rule", "skipped"]),
    ("check passed because it silently examined nothing",          {1,4,37},      ["silently", "passed", "no-op"]),
]

TOK = re.compile(r"[a-z][a-z0-9_-]{2,}")
def toks(s): return TOK.findall(s.lower())


def grep_arm(pattern):
    """Best realistic shot: case-insensitive fixed-string over the row set."""
    hits = {i for i, r in enumerate(ROWS) if pattern.lower() in r.lower()}
    return hits


def bm25(query, k1=1.5, b=0.75):
    docs = [toks(r) for r in ROWS]
    N = len(docs)
    avgdl = sum(len(d) for d in docs) / N
    df = Counter()
    for d in docs:
        df.update(set(d))
    scores = []
    q = toks(query)
    for i, d in enumerate(docs):
        tf = Counter(d)
        s = 0.0
        for t in q:
            if t not in tf:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
        scores.append((s, i))
    scores.sort(reverse=True)
    return [i for s, i in scores if s > 0][:5]


def tfidf(query):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    vec = TfidfVectorizer(stop_words="english", sublinear_tf=True)
    M = vec.fit_transform(ROWS + [query])
    sims = cosine_similarity(M[-1], M[:-1])[0]
    order = sims.argsort()[::-1]
    return [int(i) for i in order if sims[i] > 0][:5]


def rank_of(results, truth):
    for pos, i in enumerate(results, 1):
        if i in truth:
            return pos
    return None


print(f"corpus: {len(ROWS)} operational-log rows\n")
print(f"{'#':>2}  {'grep (best pattern)':<34} {'TF-IDF':<9} {'BM25':<9}")
print("-" * 66)
tot = {"grep": 0, "tfidf": 0, "bm25": 0}
noise_total, noisy_wins = 0, 0
detail = []

for n, (q, truth, patterns) in enumerate(QUERIES, 1):
    best_pat, best_hits = None, None
    for p in patterns:
        h = grep_arm(p)
        if h & truth and (best_hits is None or len(h) < len(best_hits)):
            best_pat, best_hits = p, h
    if best_pat:
        tot["grep"] += 1
        noise_total += len(best_hits)
        if len(best_hits) > 5:
            noisy_wins += 1
        g = f"'{best_pat}' hit, {len(best_hits)} rows"
    else:
        g = f"MISS (tried {len(patterns)})"

    rt = rank_of(tfidf(q), truth)
    rb = rank_of(bm25(q), truth)
    if rt: tot["tfidf"] += 1
    if rb: tot["bm25"] += 1
    print(f"{n:>2}  {g:<34} {('#'+str(rt)) if rt else 'miss':<9} {('#'+str(rb)) if rb else 'miss':<9}")
    detail.append((n, q, best_pat, len(best_hits) if best_hits else 0, rt, rb))

N = len(QUERIES)
print("-" * 66)
print(f"    hit rate: grep {tot['grep']}/{N}   TF-IDF {tot['tfidf']}/{N}   BM25 {tot['bm25']}/{N}")
if tot["grep"]:
    print(f"    grep rows returned on a hit: {noise_total/tot['grep']:.1f} avg; "
          f"{noisy_wins}/{tot['grep']} hits buried in >5 rows")
print("\n    embedding arm: NOT RUN — HuggingFace blocked by the egress proxy (403),")
print("    no NANOGPT_API_KEY in this container. See PROTOCOL.md rule 5.")
