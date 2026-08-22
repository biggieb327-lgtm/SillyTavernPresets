#!/usr/bin/env python3
"""Does ranked search do better on FINER chunks?

run.py treated a whole row as one document. Rows are ~2,000 chars spanning failure,
root cause, patch, eval and next — topically heterogeneous, which dilutes a short
query. Testing my own stated limitation rather than leaving it as a caveat: split each
row into its six cells and rank cells, crediting the row they belong to.
"""
import math, re
from collections import Counter
from pathlib import Path

ROWS=[l for l in Path(".claude/memory/operational-log.md").read_text(encoding="utf-8").splitlines()
      if l.startswith("| 20")]
SPLIT=re.compile(r'(?<!\\)\|')
chunks=[]                      # (row_index, cell_text)
for i,r in enumerate(ROWS):
    cells=[c.strip() for c in SPLIT.split(r) if c.strip()]
    for c in cells[1:]:
        chunks.append((i,c))

QUERIES=[("bot reports conditions for the wrong location",{12}),
 ("character forgets we already discussed something and raises it again",{33}),
 ("generated picture is not the same woman as the reference",{15,22,28,31}),
 ("hitting a rate limit and our own retries make it last longer",{10}),
 ("setting an on/off environment variable had no effect",{8,11}),
 ("crash on startup comparing times with and without timezone info",{68}),
 ("duplicate process fighting over the same telegram token",{45,46,57}),
 ("trimming the prompt throws away recent conversation turns",{53}),
 ("documented rule with nothing enforcing it gets ignored",{65,24}),
 ("check passed because it silently examined nothing",{1,4,37})]

TOK=re.compile(r"[a-z][a-z0-9_-]{2,}")
def toks(s): return TOK.findall(s.lower())
docs=[toks(c) for _,c in chunks]; N=len(docs)
avgdl=sum(len(d) for d in docs)/N
df=Counter()
for d in docs: df.update(set(d))

def bm25(q,k1=1.5,b=0.75):
    out=[]
    for i,d in enumerate(docs):
        tf=Counter(d); s=0.0
        for t in toks(q):
            if t in tf:
                idf=math.log(1+(N-df[t]+0.5)/(df[t]+0.5))
                s+=idf*tf[t]*(k1+1)/(tf[t]+k1*(1-b+b*len(d)/avgdl))
        if s>0: out.append((s,i))
    out.sort(reverse=True)
    seen=[];ranked=[]
    for s,i in out:                       # dedupe to first hit per row
        r=chunks[i][0]
        if r not in seen: seen.append(r); ranked.append(r)
        if len(ranked)>=5: break
    return ranked

print(f"chunks: {len(chunks)} cells from {len(ROWS)} rows\n")
hit=0
for n,(q,truth) in enumerate(QUERIES,1):
    res=bm25(q)
    rank=next((p for p,r in enumerate(res,1) if r in truth), None)
    if rank: hit+=1
    print(f"{n:>2}  {('#'+str(rank)) if rank else 'miss':<6}  {q[:58]}")
print(f"\n    BM25 over cells: {hit}/{len(QUERIES)} in top 5   (row-level BM25 was 5/10)")
