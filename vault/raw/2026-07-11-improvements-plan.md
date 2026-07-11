# Raw capture: IMPROVEMENTS_PLAN.md

Source: `telegram-companion-bot/IMPROVEMENTS_PLAN.md` @ commit `d76dcdf`.
Release-by-release handoff spec for the 2026-07-10 audit backlog. All six releases
(R1–R6) SHIPPED as v2026-07-11.1 through .6 (git log), though the plan/roadmap
still show them pending — known doc drift at capture time.

Ground rules, verbatim highlights:

> 4. **One release per phase below.** Small diffs deploy safely over `/update`; a
>    mega-release risks the whole 6-bot fleet at once.

> 5. **Phone constraints:** NO new per-message LLM calls [...] No new processes
>    (phantom-process killer). `/tmp` is not writable on Termux.

> 8. **Commit real work before break-testing evals** [...] this exact mistake
>    destroyed 700 lines once — operational-log 2026-07-10.

Standing verification block (every release):

> python3 -m py_compile telegram-companion-bot/bot.py
> python -m pytest telegram-companion-bot/tests/ -q
> bash .claude/evals/run-evals.sh

> design every feature so unset = today's behavior.
