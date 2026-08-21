# 2026-08-01 — nora selfie wrong weather

Archived from `.claude/memory/operational-log.md` on 2026-08-21, verbatim. The row
there is the index entry; this is the full record, including every correction
appended after the fact.

## Failure

**Nora sent a selfie showing rain on a day Seattle was sunny throughout.** Owner-reported; image only — her caption and conversation were correctly sun-aware.

## Root cause

`build_selfie_prompt` composed the scene from weather-blind random pools, then appended the live reading as a trailing clause phrased for a text model: *"don't describe the weather explicitly, just let it show."* `[observed]` `/status` on nora returned `Weather: 70°F, clear, wind 11mph`, day context was the Eastlake bike lane with no rain, and her last message was about sun on her neck — which ruled out all three cheaper explanations in one command (fetch failure, stale cache, `world.txt` seeding a rainy day narrative). `[code]` `_weather_outdoor_ok` screens precipitation and `_weather_camera_pool` screens camera presets, but nothing screened the scene for **temperature**: `SELFIE_ACTIVITIES` holds "bundled up against the cold", `SELFIE_OUTFITS` holds "a beanie and a hoodie", and Ingrid's canvas courier jacket was appended to every outdoor shot unconditionally. `[code]` a rendered prompt at 70°F clear carried four cold-Seattle signals against one temperature token. The general shape: **a correct live reading appended after unfiltered random content does not override it — the specific scene wins over the abstract fact.**

## System patch

`v2026-08-01.7`: `_weather_temp_f` (first `°F` field, never "feels like") + `_weather_scene_pool` drop cold activities, cold outfits and the jacket at/above `SELFIE_WARM_F` (68°F). Weather clause is now directive, and a dry reading appends an explicit *it is NOT raining* negative — clear-sky and no-precipitation asserted separately so overcast never claims clear sky. Unknown weather is not treated as warm. Kill switch `SELFIE_WEATHER_MATCH=0`.

## Eval

`TestSelfieWeatherMatching`, 11 tests: contradictory content across 300 seeds 137 → 0 at 70°F clear, negative in 300/300, cold/rainy readings unchanged, kill switch reproduces the old prompt. Three load-bearing assertions break-tested RED independently (C3). 740/740 pytest, 32/32 evals.

## Next

**Not confirmed against a real generated image** — the fix is proven at the prompt layer only, and whether the image model now honors the negative needs a `/selfie` on a clear day to check. **Deliberately left open:** Ingrid's courier jacket is gated on `SELFIE_APPEARANCE is _APPEARANCE_DEFAULT`. **Corrected 2026-08-01 (v2026-08-01.8):** the original wording here — "any instance falling through to the default gets a different woman's face *and* Nora's dead grandmother's jacket" — was wrong, and the sentence flagging it as unverified is exactly where it went wrong. `[code]` `_APPEARANCE_DEFAULT` applies only when `not IS_NAMED_INSTANCE`, and `deploy/bot@.service` runs `bot.py /opt/telegram-bots/%i`, so all seven instances are named: neither the stale description nor the jacket has ever reached a live selfie. The lesson is C8's, one step earlier — an unverified claim was written into the durable record in the *assertive* voice with the hedge appended, rather than being written as the open question it was. Both issues fixed in v2026-08-01.8.

