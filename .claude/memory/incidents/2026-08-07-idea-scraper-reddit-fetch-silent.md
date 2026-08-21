# 2026-08-07 — idea scraper reddit fetch silent

Archived from `.claude/memory/operational-log.md` on 2026-08-21, verbatim. The row
there is the index entry; this is the full record, including every correction
appended after the fact.

## Failure

**`idea-scraper-actor`'s Reddit fetch silently did nothing across three builds (v0.2 through v0.3.2)** — every run reported `SUCCEEDED`/`exitCode: 0` with zero dataset items, indistinguishable from a genuinely empty result. Found on an owner-requested on-demand fire specifically asking whether the actor's residential-proxy path got past Reddit's Cloudflare block.

## Root cause

`[code]` `main.py` defined `async def main()` but never called it — no `asyncio.run(main())`, no `if __name__ == "__main__":` guard; the Dockerfile's `CMD ["python3", "-m", "src.main"]` imported the module, defined some functions, and exited 0 having done nothing. `[observed]` confirmed by adding a log line as `main()`'s literal first statement and finding it never appeared in any of 3 separate live runs' logs. A concurrent session (commit `020ed25`) independently found and fixed `RESIDENTIAL`'s 0 `availableCount` (via `GET /v2/users/me`) and pushed a proxy-group switch straight to `main` — real finding, but not the actual cause of the empty runs, since `main()` never got far enough to reach proxy setup either way; that fix alone would still have produced silent 0-item "successful" runs. `[observed]` once the entrypoint was fixed (build 0.3.3), `create_proxy_configuration()` failed for *every* group with `ApifyApiError: Insufficient permissions` (traceback: `apify-client`'s `user().get()` rejected before group selection matters) — an account/token permission gap. `[observed]` the fail-soft fallback to an unproxied request then got a genuine `403 Client Error: Blocked` from Reddit's own Cloudflare, confirmed live.

## System patch

v0.4 (build 0.4.1, deployed via `apify push`): added the missing `asyncio.run(main())` entrypoint; wrapped proxy setup in a try/except with fail-soft fallback and loud logging instead of a silent no-op or an unhandled crash; README and module docstring rewritten to state the actual current-blocked status. Merged with the concurrent session's commit (`020ed25`) rather than overwriting it — same target proxy group, this session's fix is a superset.

## Eval

none — `idea-scraper-actor` deploys via `apify push` by hand, outside this repo's CI/eval reach (same as the rest of its history in this log).

## Next

**Reddit access still does not work end to end.** Fixing it needs the account's Apify Proxy permission granted (Apify Console/support, not something an API token can self-serve) — out of reach from this session. Even once granted, whether the configured group's egress IPs get past Cloudflare is unverified — that's the next open question, not this one. Substack's path is code-reachable now that `main()` executes, but untested — no `substack_publications` URL has appeared in any test call yet. **Reusable lesson: two independent sessions, on the same day, root-caused the same symptom (SUCCEEDED, 0 items) to two different, both-real bugs stacked on top of each other** — the first fix found didn't make the second one less real, and neither should have been assumed to be "the" fix without a live run proving items actually came back.

