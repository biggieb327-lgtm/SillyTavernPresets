# Test audit — `inspect.getsource` tests in `tests/test_pure.py` (2026-10-08)

**Report only. No test was changed.** Each batch below waits for owner approval.

Method borrowed from gstack's `/test-audit` skill (garrytan/gstack, MIT): a mechanical
shortlist first, then one verdict per test with the evidence for it, then approval per batch.

## Why this audit exists

A test that reads a function's source text passes when the text is present. It cannot fail
when the function stops doing the thing — the `/features` `ValueError` (v2026-08-02.14,
`incidents/2026-08-02-features-command-never-flipped.md`) shipped past exactly this kind of
test. `sweep.py source-assertion` already guarantees that every `*_cmd` handler is **called**
by at least one test (it reports 0 today). It does not check that each **behavior** a source
test pins is exercised by a call. That per-behavior gap is what this audit looks for.

## Scope and numbers

- Shortlist: every test function in `tests/test_pure.py` whose body calls
  `inspect.getsource`, or calls a class helper that does (`_src`, `_assembled`,
  `_health_job_source`, `_reasons_returned`, `_reasons_handled`, `_registered_command_names`).
  No other test file uses `inspect.getsource`.
- 108 `inspect.getsource` calls → **137 tests** (of 1,729 in the file): 91 call it directly,
  46 through one of the helpers. Every one of the 137 has exactly one verdict below
  (cross-checked by script against the AST).

| Verdict | Count | Meaning |
|---|---|---|
| keep | 100 | The source text **is** the contract (a static invariant, a code ordering, an LLM prompt's wording, an import-time constant), or a call cannot observe it cheaply. |
| rewrite | 29 | The test claims a runtime behavior. A test that calls the function can prove it, and the harness to do so already exists. |
| retire | 6 | A calling test or a sibling test already proves the same thing. |
| trim | 2 | Keep the test; delete one redundant line that reads `main`'s source. |

## One blocker, found during the audit

`_CmdMsg.reply_text` (`tests/test_pure.py`, the `TestEveryCommandHandlerActuallyRuns`
harness) drops its `**kwargs`. So no calling test can see `parse_mode`, and every "this
command replies in plain text" test has to read the source instead. **Recording the kwargs
in `_CmdMsg` is a prerequisite for batch B** — a three-line change to the stub, not to bot.py.

## Batch A — `/audit` renders a key (rewrite, 6 tests → 1 table-driven test)

Each test greps `audit_cmd`'s source for a key name. A key that is gathered but never printed
would still pass. Rewrite: one test that calls `audit_cmd` (the pattern is already in
`test_audit_renders_the_qualifier_beside_the_count`) and asserts each label is in the output.

| Line | Test | Verdict |
|---|---|---|
| 1119 | `TestGatherAuditData.test_intent_stats_rendered_in_audit` | rewrite |
| 8438 | `TestAuditReportsSelfieBase.test_it_reaches_the_rendered_audit_text` | rewrite |
| 8577 | `TestAuditReportsSelfieProvider.test_provider_is_gathered_and_rendered` (2nd assert) | rewrite |
| 8794 | `TestMediaOfferChances.test_audit_reports_feature_readiness` (last assert) | rewrite |
| 8953 | `TestFeatureDetailAndLocation.test_location_is_reported` (last assert) | rewrite |
| 6282 | `TestAuditIsPlainText.test_header_has_no_markdown_emphasis` | rewrite |

## Batch B — commands reply in plain text (rewrite, 3 tests; needs the `_CmdMsg` change)

| Line | Test | Verdict |
|---|---|---|
| 6276 | `TestAuditIsPlainText.test_audit_does_not_use_parse_mode` | rewrite: call `audit_cmd`, assert no `parse_mode` kwarg |
| 6109 | `TestPresetCommandInvariants.test_command_is_plain_text` | rewrite: same, `preset_cmd` |
| 6672 | `TestNoUnescapedMarkdownInterpolation.test_content_rendering_commands_are_plain_text` (7 handlers) | rewrite: all 7 are already called in `TestEveryCommandHandlerActuallyRuns`; assert on the recorded kwargs there |

## Batch C — command gates and failure replies (rewrite, 11 tests)

| Line | Test | Verdict and how |
|---|---|---|
| 6103 | `TestPresetCommandInvariants.test_command_is_admin_gated` | rewrite: outsider gets silence (copy `test_audit_cmd_is_admin_gated`) |
| 6115 | `TestPresetCommandInvariants.test_command_refuses_an_empty_stack` | rewrite: call with args that drop every layer, assert the refusal text |
| 8494 | `TestSetBaseCommand.test_admin_gated` | rewrite: outsider gets silence |
| 8505 | `TestSetBaseCommand.test_rejects_non_image_bytes` | rewrite: reuse `TestSetbaseBackupClaim._run` with non-image bytes |
| 8527 | `TestSetBaseCommand.test_warns_when_telegram_compressed_the_image` | rewrite: same harness, `photo=` instead of `document=` |
| 8743 | `TestGifCommandAndRedaction.test_gif_command_announces_errors` | rewrite: call `gif_cmd` with a query and no key, assert a reply |
| 8748 | `TestGifCommandAndRedaction.test_gif_command_is_admin_gated_registered_and_in_menu` | rewrite the gate assert; drop the `main` source assert (see batch E) |
| 8904 | `TestFeatureSwitches.test_command_registered_gated_and_in_menu` | rewrite the gate assert; drop the `main` source assert |
| 6590 | `TestUpdateCmdNeverRepliesSilently.test_every_failure_reason_gets_a_reply` | rewrite: parametrize over the reasons with `perform_self_update` monkeypatched (pattern at the `repo_not_readable` calling test) |
| 6346 | `TestBadRequestNotNetwork.test_ordering_is_explicit_in_source` | rewrite: call `on_error` with a `BadRequest`, assert it is handled as BadRequest. This is the strongest candidate: in PTB, `BadRequest` subclasses `NetworkError`, so the call proves the ordering; the source index does not prove the branch runs |
| 6353 | `TestBadRequestNotNetwork.test_bad_request_surfaces_at_error_level` | rewrite: same call, assert an ERROR record in `caplog` |

## Batch D — helper behaviors (rewrite, 9 tests)

| Line | Test | Verdict and how |
|---|---|---|
| 8730 | `TestGifCommandAndRedaction.test_user_facing_errors_carry_no_exception_text` | rewrite: `_giphy_search` raises an exception with a marker, assert the marker is not in any reply |
| 8754 | `TestGifCommandAndRedaction.test_distinguishes_no_key_from_no_results` | rewrite: call `send_gif` twice (no key; `[]` results), assert the two replies differ |
| 8725 | `TestGifCommandAndRedaction.test_both_failure_paths_redact` | rewrite: an exception carrying a fake key on each path, assert the key is not in `caplog` |
| 9940 | `TestOffVersusNeverConfigured.test_selfie_and_meme_report_the_switch_not_a_missing_file` | rewrite: capable=False, call `send_selfie` / `send_meme`, assert "switched off" |
| 5837 | `TestUsageCaptureWiring.test_saved_calibration_is_validated` | rewrite: a `state.json` with a nonsense ratio, call `load_state`, assert it is rejected |
| 8993 | `TestLifeArcRotation.test_cadence_uses_a_stamp_not_a_weekday` | rewrite with the four below: `call_nanogpt` stubbed, tmp `LIFE_ARC_FILE` / `LIFE_STAMP_FILE` |
| 8999 | `TestLifeArcRotation.test_first_run_stamps_and_waits` | rewrite: no stamp → stamp written, arc unchanged |
| 9003 | `TestLifeArcRotation.test_a_short_or_empty_result_keeps_the_existing_arc` | rewrite: stub returns 10 chars → arc unchanged |
| 9008 | `TestLifeArcRotation.test_the_old_arc_is_archived` | rewrite: after a rotation, `life_<stamp>.txt` exists |

## Batch E — retire (6 tests)

| Line | Test | Why it can go |
|---|---|---|
| 15338 | `TestRecastPipeline.test_recast_pipeline_called_in_deliver` | The ordering test below it calls `src.index("_recast_pipeline")`, which raises if the call is absent. Strict subset. |
| 8515 | `TestSetBaseCommand.test_backs_up_the_previous_photo` | `TestSetbaseBackupClaim.test_a_real_replacement_still_reports_the_backup` calls the handler and checks the `.prev` file's bytes. |
| 8524 | `TestSetBaseCommand.test_targets_selfie_base_so_no_env_edit_is_needed` | The same `TestSetbaseBackupClaim` tests assert the write lands at `BASE_DIR / SELFIE_BASE`. |
| 6862 | `TestUpdateReasonsAllHaveBranches.test_repo_not_readable_is_one_of_them` | Its `vps-sync.sh` half is proven by `test_update_cmd_is_retired_and_points_to_vps_sync` (calls the handler); its other half is a member of the set `test_every_returned_reason_has_an_explicit_branch` already checks. |
| 15286 | `TestLifeProject.test_project_registered_as_command` | `'"project"' in main` matches any string literal "project". Replace with `any(c.command == "project" for c in bot._build_command_menu(...))`; `TestCommandMenuMirrorsHandlers` already proves every menu entry has a handler. |
| 6494 | `TestRestartStormAdviceIsCorrect.test_graceful_line_asymmetry_documented_where_the_logic_lives` | Asserts a docstring contains the word "absence". Pins documentation wording, guards no behavior. |

**Trim (2 tests).** These assert `CommandHandler("x"` in `main`'s source **and** that `x` is in
`_build_command_menu`. The menu assert plus `TestCommandMenuMirrorsHandlers` (every menu entry
has a handler) already proves registration, so the source line adds nothing. Keep the test,
delete that line. The same line inside 8748 and 8904 goes when batch C rewrites them.

| Line | Test |
|---|---|
| 8498 | `TestSetBaseCommand.test_registered_as_a_handler_and_in_the_menu` |
| 8691 | `TestGifTagAndFiltering.test_command_is_registered_and_in_the_menu` |

## Keep (100 tests) — and why the source is the right thing to read

| Group | Tests (line) | Why keep |
|---|---|---|
| No new LLM call (bot-code-invariants #3) | 5013, 6125, 8696, 7279 | Absence of a call cannot be observed by calling. |
| No raw exception text in a log (key-leak class) | 4987, 5267, 6425, 6433, 11744 | Static scan of every log line; a call covers one path. |
| Off the event loop | 4972, 8703, 9018 | `asyncio.to_thread` placement is a static property. |
| Health-alert gate wiring | 4998, 5002, 5006, 9873, 9880, 9902 | Class scans across five jobs; the gates are wiring, not output. |
| Group privacy | 4978 | `GROUP_CHAT_DESIGN.md` §5 boundary; one token is the whole contract. |
| Choke-point placement | 6923, 6932, 8861 | Proves *where* a guard lives, which a call cannot. |
| Code ordering | 5813, 5824, 6724, 6741, 6747, 8556, 15343 | Order of statements is the fix. |
| Streaming usage capture | 5808, 5820, 5833 | Needs an HTTP stream fake to call; low value for the cost. |
| Token units | 5743, 5898, 5903, 5919 | Unit choice inside a computation. 5903 also calls `gather_audit_data`. |
| Prompt assembly structure | 5541, 5545, 5550, 5554, 5559, 5597, 5952, 8788, 4758 | Which blocks are optional / gated / filled. See note 1. |
| LLM prompt wording | 4676, 4682, 4740, 4743, 4746, 4749, 4752, 4755, 7295, 7301, 8974, 8981, 8985, 8989, 15281 | The prompt text is the contract. See note 1. |
| Import-time config | 6690, 6697, 6703, 6716, 6605, 6613, 8865, 8805 | Module-scope constants; a call would need a re-import. |
| Static class scans | 7844, 8394, 9947, 6964, 6977, 7894, 8765 | Scan many sites at once; a call covers one. |
| Registry extraction | 7081, 7093, 7102 (via `_registered_command_names`), 7182 | Reads `main` on purpose: the handler set only exists there. |
| Caption dispatch | 8541 (reads PTB's own source), 8551, 8562 | Handler registration order and filters in `main`. |
| Operator advice wording | 6475, 6480, 6485, 6490, 6768, 6771, 6776, 6781 | Pins strings an operator acts on; same strength as a call. |
| Misc | 5943, 6440, 6571, 6854, 8510, 8519, 9011, 9015, 9023, 15276 | 8519 (atomic write) and 9011 (cache invalidation) are unobservable from outside without timing tricks. 6571 / 6854 are on the retired `/update` path — retire them when that code is deleted, not before. 15276 is weak (three OR'd strings); tighten it to one token when touched. |

**Note 1.** The prompt-structure and prompt-wording tests would be stronger against a
rendered prompt than against source: a string can sit in `assemble_messages` behind a
branch that never runs. `tools/render_prompt.py` already renders every instance's prompt
offline (the `prompt-render` eval). Moving those checks onto the rendered text is a
reasonable later batch. It is not in this audit's rewrite count because the source checks
are not wrong, only weaker.

## Proposed order

1. The `_CmdMsg` kwargs change, then batch B.
2. Batch C (gates and failure replies — closest in shape to the `/features` bug).
3. Batch A, then batch D.
4. Batch E (retire + trim).

Each batch: run `.claude/tools/verify.sh` before and after; no bot.py change is expected.
For each rewrite, break-test the new test once: comment out the guarded line in a scratch
copy and confirm the new test fails.
