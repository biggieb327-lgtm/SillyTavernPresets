# Does semantic search beat grep on the operational log?

**Question.** C4 ("Search for the bug's shape, not its remembered vocabulary") is
prose-only and unmechanised. It exists because grepping a log by the words you *remember*
misses entries that describe the same thing differently. The operational log is now 71
index rows plus 9 incident files — big enough that "have we hit this before?" is a real
question and too big to read whole. Would semantic retrieval answer it where grep can't?

**Decision this informs.** Whether to build semantic search over `.claude/memory/`. A
"no" is a real outcome and cheaper than a "yes".

## Rules, fixed before any result was seen

1. **Queries are written from the SITUATION, never from the row.** Each one describes a
   symptom in the words a future session would plausibly use, having *not* read the log.
   Where I know the log's distinctive phrasing, I deliberately avoid it — copying its
   vocabulary would rig the test in grep's favour and prove nothing.
2. **Ground truth is fixed here, before running.** Listed per query as row indices.
   A retrieval counts as correct only if it returns a row listed here.
3. **grep gets its best realistic shot**, not a strawman: up to three candidate patterns
   per query, scored on the best one. Grep is also credited only if a human would
   actually find the row — 40 matches containing the answer is a weak hit, so the match
   count is recorded as noise.
4. **No query is edited after seeing results.** If a query turns out to be badly posed,
   it stays in and is reported as such.
5. **Arms that cannot run are reported as not run**, never silently dropped.

## Scoring

| arm | hit criterion | noise measure |
|---|---|---|
| grep | ground-truth row appears in output | number of rows returned |
| ranked (BM25 / embeddings) | ground-truth row in top 5 | rank of first correct hit |

## The corpus

`.claude/memory/operational-log.md`, 71 index rows, each treated as one document
(date + all six cells). Incident files are excluded: they are pointed at by their row, so
retrieving the row is what matters.

## The queries

Ground truth refers to the row indices printed by the corpus lister (newest = 0).

| # | The situation a session is in | Query text | Ground truth |
|---|---|---|---|
| 1 | A bot keeps answering about the weather somewhere the user doesn't live | "bot reports conditions for the wrong location" | 12 |
| 2 | She mentioned something we'd already talked about days ago as if it were new | "character forgets we already discussed something and raises it again" | 33 |
| 3 | The picture she sent doesn't look like the same person | "generated picture is not the same woman as the reference" | 15, 22, 28, 31 |
| 4 | An upstream API started refusing us and it seems to be getting worse, not better | "hitting a rate limit and our own retries make it last longer" | 10 |
| 5 | I set a feature flag and nothing changed | "setting an on/off environment variable had no effect" | 8, 11 |
| 6 | The bot dies on boot with a date/time error | "crash on startup comparing times with and without timezone info" | 68 |
| 7 | It looks like two copies of the same bot are running | "duplicate process fighting over the same telegram token" | 45, 46, 57 |
| 8 | Long conversations seem to lose recent context | "trimming the prompt throws away recent conversation turns" | 53 |
| 9 | A written rule keeps getting skipped by sessions | "documented rule with nothing enforcing it gets ignored" | 65, 24 |
| 10 | A check said everything was fine but it wasn't looking at anything | "check passed because it silently examined nothing" | 1, 4, 37 |

## Candidate greps (fixed here, before running)

1. `weather`, `location`, `city`
2. `memory`, `forget`, `recall`
3. `selfie`, `photo`, `face`
4. `rate limit`, `429`, `retry`
5. `env var`, `flag`, `feature`
6. `timezone`, `startup crash`, `tz`
7. `Conflict`, `two process`, `poller`
8. `prompt budget`, `history`, `trim`
9. `enforcement`, `rule`, `skipped`
10. `silently`, `passed`, `no-op`
