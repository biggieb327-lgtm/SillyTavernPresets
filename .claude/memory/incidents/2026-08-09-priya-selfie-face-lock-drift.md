# 2026-08-09 — priya selfie face lock drift

Archived from `.claude/memory/operational-log.md` on 2026-08-21, verbatim. The row
there is the index entry; this is the full record, including every correction
appended after the fact.

## Failure

**Priya's selfies drift into a stranger with the face lock on** — owner-reported. The same symptom class as v2026-08-03.2, and the same wall: nothing in the system can show what her reference photo looks like, so the leading hypothesis could not be checked from a session or from Telegram.

## Root cause

`[code]` v2026-08-03.2 already root-caused this symptom on Emily to the **reference photo**, not the prompt — a full-body beach shot with her face at ~8% of frame height, which an edit model cannot copy so it synthesises one. `[code]` that release wrote the observability gap into the changelog verbatim (*"Nothing in the system ever showed anyone what the reference photo **is**"*) and shipped without closing it; `grep` confirms it was never tracked in ROADMAP.md, IMPROVEMENTS_PLAN.md or this log, so it survived six days and eleven releases. `[code]` `/audit` printed a bare filename and `/setbase` reported only format and KB — neither can distinguish a portrait crop from a beach shot. `[hypothesis]` that Priya's reference is badly framed the way Emily's was: consistent with the symptom, **not confirmed** — no one has looked at `priya_base.png`.

## System patch

v2026-08-09.1: bare `/setbase` sends the current reference photo back with filename, pixel dimensions and size; `/audit` and the startup audit line carry dimensions; the install confirmation reports them too. Kill switch `SELFIE_BASE_PREVIEW`. A face-size metric was deliberately not built — it needs face detection, and a dimensions-based verdict would have passed the beach photo anyway (C8 applied before the fact).

## Eval

`TestBaseImageDimensions` and `TestSetbaseShowsTheCurrentPhoto` (11 tests, 5 assertions break-tested RED one injection at a time). No new eval: this is a missing *capability*, not a check that failed to fire.

## Next

**RESOLVED 2026-08-09, same day.** `/audit` showed `priya_base.jpg 1024×1024` with no `AUTODETECTED` warning, so resolution and `.env` were correct — the extension-mismatch theory (v2026-08-01.10's shape) was wrong. The photo was a real front-facing portrait with her face at roughly 30% of frame height, not an 8% beach shot, so the framing hypothesis above was wrong **as stated** — but directionally right: the owner re-cropped it tighter and reinstalled via `/setbase`, and six subsequent selfies read as recognisably one woman. `[observed]` **Uncontrolled:** no A/B, and the pre-crop outputs were never seen, so the size of the improvement is not measured — only that the "different stranger every time" symptom is gone. **Open, owner-deferred to a future release (ROADMAP 3.17):** the bindi survives in about half those six. `_SELFIE_PRESERVE_RULE` has a dedicated conditional clause for eyewear and nothing for any other worn face item; "bindi" appears once in the repo, in `priya/appearance.txt`, and never in `bot.py`. **Still true and still unswept:** six other instances' reference photos have never been looked at. **Worth knowing before any selfie prompt work:** priya runs `gemini-3-pro-image-preview`, and no face-lock A/B in the changelog was ever run against that model.

