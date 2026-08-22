# Results — semantic search over the operational log

**Verdict: don't build it.** Recall is not the bottleneck, and the cheap fix for the
bottleneck that does exist needs no embeddings, no API and no dependencies.

Protocol, queries and ground truth were committed in `PROTOCOL.md` (`464f858`) before any
result was seen. Corpus: 71 operational-log rows.

## Numbers

| arm | hit rate | precision |
|---|---|---|
| grep, patterns I chose | 10/10 | 4.1 rows avg per hit |
| **grep, patterns derived only from the query text** | **9/10** | **8.9 rows avg, worst 21; 4/9 buried in >5 rows** |
| TF-IDF, row as document | 5/10 in top 5 | — |
| BM25, row as document | 5/10 in top 5 | — |
| **BM25, cell as document** | **7/10 in top 5** | every hit at rank 1–4 |
| embeddings | **NOT RUN** | HuggingFace blocked by the egress proxy (403); no `NANOGPT_API_KEY` here |

## What actually decided it

**1. Plain grep already finds the row.** 9 of 10, using only words from the question. The
maximum recall any better retrieval could add is about one query in ten. The reason is
unglamorous: rows average ~2,000 characters, so nearly any content word from a plausible
question appears somewhere in the right row. **Verbosity that hurts readability helps
lexical recall.**

**2. The real problem is precision, not recall.** A grep "hit" means reading 8.9 rows on
average and up to 21 to find the one. That is the actual cost a session pays, and it is
what made this feel like a retrieval problem when it is a *ranking* problem.

**3. Chunk size mattered more than the algorithm.** The only change between 5/10 and 7/10
was splitting each row into its six cells. Same BM25, same queries. **The lever is
document structure, not retrieval technology** — which is the lever already pulled on
2026-08-21 by moving nine investigations into `incidents/` and capping rows at 3,000
characters. Continuing that does more for this than any index would.

**4. My first grep arm was contaminated and the correction mattered.** I picked its
patterns having read the corpus: `429` when the question says "rate limit", `tz` when it
says "timezone" — vocabulary you only have if you already know the answer. That is C4's
failure mode being masked by the experimenter. The strict re-run (`run_strict.py`) takes
only words from the question and is the number to trust. It cost one hit and doubled the
noise, which is the honest shape of the problem.

## The one clear C4 instance

Query 5 — "setting an on/off environment variable had no effect". The log says **"env
var"**; the question says **"environment variable"**. Plain grep missed it entirely and
row-level BM25 missed it; **cell-level BM25 found it at #4**. So the failure C4 describes
is real, it appeared once in ten, and a lexical ranker over finer chunks caught it without
any semantic model.

## What I would do instead, if anything

Nothing urgent. If the wading cost becomes annoying, `run_chunked.py` is ~40 lines of
stdlib BM25 over row cells and could become `.claude/tools/oplog-search.sh` — no
dependency, no key, no network, runs in milliseconds. That is the whole proposal, and it
is a fraction of what a vector index would cost.

## Addendum: a fresh query, after the tool was built

`.claude/tools/oplog-search.py` was built from this result. The first query tried on it
that was **not** in the frozen set — *"an eval passed but it was not actually checking
anything"*, aimed at the 12-of-15-evals row — **missed, and so did grep.** The row says
"reported PASS whenever their own parser died"; the query said "passed… checking
anything". Only `eval` overlaps, and it appears in 39 of 71 rows.

That is a second confirmed C4 instance and the honest ceiling on this tool: **7/10 came
from queries I wrote, and the first uncontaminated query failed.** It does not reverse
the build decision — the tool is still cheap and still better than grep on precision when
both find the row — but it does mean the tool must never be read as "no result = never
happened". The skill pointer and the tool's own output say so.

It is also the clearest evidence for where an embedding arm would pay: both failures so
far are jargon gaps, not ranking failures.

## Limits of this experiment — stated, not buried

- **The embedding arm never ran.** So the honest claim is "lexical retrieval leaves little
  recall headroom", not "embeddings would not help". Embeddings could still improve
  *ranking*; so did chunking, for free.
- n = 10, and one person wrote the queries, the ground truth and the greps.
- Ground truth is my judgement of which row "answers" each question; two of the queries
  have several defensible answers.
- Rows are a moving target — the corpus was reshaped earlier the same day.

Reproduce: `python3 .claude/experiments/2026-08-21-oplog-retrieval/run.py`,
`run_strict.py`, `run_chunked.py`.
