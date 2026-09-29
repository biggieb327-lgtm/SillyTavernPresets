# Inbox -- raw capture, sort later

The lowest-friction memory file. When you notice something mid-task and don't know which
file it belongs in -- or don't want to interrupt your flow to decide -- put it here.

## What belongs here

Anything worth remembering that you haven't classified yet. A finding, an idea, a smell,
a question, a URL, a one-liner. The bar is "would I be annoyed if the next session had to
rediscover this?" If yes, write it down. If unsure, write it down -- sorting is cheaper
than rediscovery.

## What does NOT belong here long-term

Everything. This file is a buffer, not a home. Every item either moves to its real file
or gets dismissed. The session-debrief skill sorts the inbox; items that survive two
debriefs without being sorted are stale and should be dismissed or promoted.

## How it gets sorted

At session-debrief, each item gets one of:

| Route to | When |
|---|---|
| `operational-log.md` | the system failed |
| `constraints.md` | we made a mistake doing the work |
| `mycelium.md` | it's a message to the next session |
| `watchlist.md` | it hasn't happened yet, it just might |
| `decisions.md` | a choice among real alternatives was settled |
| Notion Fleet Knowledge Base | a finding or state change worth persisting without a commit |
| **dismissed** | not worth keeping; delete the line |

## Entry format

```
- YYYY-MM-DD: one line. just the observation. no format required.
```

No headers, no status fields, no metadata. The whole point is zero friction. One dash,
a date, a sentence. If it needs more than a sentence, it probably already knows which
file it belongs in -- write it there instead.

Newest first.

---

## Items


- 2026-09-26: egress proxy denied counterparts.ai (connect_rejected), but the Nimble connector (`nimble_extract`, driver vx8) fetched the full page text. Untested whether Nimble reaches docs.python-telegram-bot.org or nano-gpt.com, the two hosts CLAUDE.md calls unreadable; worth one try before reporting "host blocked".
