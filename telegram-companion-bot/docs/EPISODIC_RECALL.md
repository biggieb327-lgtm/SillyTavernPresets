# Episodic recall

Verbatim long-term memory for the companion bots, built on embeddings.

## The problem it solves

The bot keeps three memory tiers: the verbatim window (`conversation_history`,
last ~40 messages), the rolling **recent** summary + facts (~a week), and the
durable **long-term** summary + facts. When messages scroll out of the verbatim
window, `maintain_memory` summarizes them and then **discards the raw turns**.
She keeps the gist forever but loses the specifics — she can't recall the actual
exchange from three months ago, only its smoothed-over summary.

Episodic recall keeps an embedded archive of those scrolled-off turns and pulls
back the single most relevant *past exchange*, verbatim, when the current turn
resonates with it.

## How it works

- **Archive on scroll-off.** In `maintain_memory`, the `batch` of messages about
  to be dropped is chunked (~6 messages, 1 overlap), each chunk embedded and
  appended to a per-bot archive. Runs off the event loop; only fires when a
  conversation ages out (every `SUMMARY_EVERY` turns), so embedding cost is
  occasional, not per-message.
- **Retrieve per turn.** `handle_message` already embeds the turn into `query_vec`
  for semantic memory retrieval. Episodic recall **reuses that same vector** — so
  it adds *no* extra per-turn embedding call. Cosine similarity against the
  archive matrix, top-K above a floor, injected next to the memory block.
- **Time-gated.** Chunks newer than `EPISODE_MIN_AGE_HOURS` (default 24h) are
  skipped, so the live window / today's conversation isn't echoed back as a
  "memory."

## Storage & RAM

- Per bot: `.episodes.jsonl` (append-only, one `{ts, text, vec}` per line) plus a
  `.episodes.model` sidecar recording which embedding model the vectors came from.
- Loaded once at startup into an in-RAM **float32 numpy matrix** (normalized rows,
  so cosine is a single matmul). At 1024 dims a chunk is ~4 KB; the default
  `EPISODE_MAX=4000` cap is ~16 MB/bot.
- The file is append-only at runtime; RAM is capped on every append (newest kept).
  The on-disk file is trimmed back to `EPISODE_MAX` at the next startup load.
- **numpy is required.** Without it, episodic recall disables itself with a startup
  warning (everything else keeps working). On Termux, don't `pip install numpy` (it
  compiles from source and fails on `spawn.h`) — instead `pkg install python-numpy`
  and set `include-system-site-packages = true` in the venv's `pyvenv.cfg` so the
  venv can see it.

## Model coupling

Episodes and NPC memories are both compared against the same per-turn `query_vec`,
so they share `EMBED_MODEL`. Changing a bot's embedding model invalidates the
episode vectors; on a model mismatch the archive is discarded and rebuilt going
forward (the `.episodes.model` sidecar detects the change at load).

## What it deliberately does *not* touch

The always-on tiers (recent/long-term summary, facts, milestones) are unchanged.
Episodic recall is purely additive detail — it never gates the identity-level
facts she should always know.

## Config

See `.env.example` (the "Episodic recall" block). Defaults:

| Var | Default | Meaning |
|---|---|---|
| `EPISODIC_RECALL` | `1` | On when `EMBED_MODEL` is set; `0` disables |
| `EPISODE_MAX` | `4000` | Hard cap on archived chunks (RAM/disk bound) |
| `EPISODE_CHUNK_MSGS` | `6` | Messages per chunk (1 overlap) |
| `EPISODE_EMBED_CHARS` | `1600` | Truncate chunk text before embedding (model token cap) |
| `EPISODE_MIN_SIM` | `0.40` | Cosine floor to surface a past moment |
| `EPISODE_TOPK` | `1` | How many past moments per turn |
| `EPISODE_MIN_AGE_HOURS` | `24` | Don't recall anything newer than this |

## Inspecting it

`/episodes` shows how many chunks are archived and the most recent one.
