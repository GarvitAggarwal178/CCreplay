# Validation, results and limitations

[Project home](../README.md)

## How to read this page

Three kinds of evidence are kept separate: historical gate results preserved in the original experiment artifacts; checks run on this checkout during the 20 October 2026 refresh; and open issues. None of them certifies code changed afterwards.

A replay-fidelity gate compares model outputs with a recorded implementation. A differential test compares two model versions. Browser tests verify interactions. Live-network tests verify actual host execution. One does not replace another.

## Historical correctness evidence

Original reports, predictions and failed attempts are in the evidence archive (`source-snapshot.tar.gz`, indexed in `docs/EVIDENCE_INDEX.json`; see [Provenance](PROVENANCE.md)). They are not rewritten to match this summary.

| Area | Result | Evidence and interpretation |
|---|---|---|
| Reno capture and replay | PASS | Three primary recordings: 112,051 events; event-local replay checked 224,120 fields with zero mismatches, zero drops and gaps. Stateful replay found no first divergence. Reno has no controller-private history; the reference is real kernel functions. |
| CUBIC replay fidelity | PARTIAL | 236,088 events, 4,485,714 field comparisons: 236,042 clock-stable events exact; 46 clock-ambiguous events contained 4 mismatches. The original stateful criterion was not met on every primary trace. Clock diagnosis: ATTRIBUTED_AND_CHARACTERIZED; the instrumentation search is not closed. |
| CUBIC undo callback | Validated on auxiliary trace | 12 undo_cwnd invocations, 75,415 dominant events, no mismatch; absent from primary recordings. The auxiliary trace is archived. This does not upgrade the overall CUBIC verdict. |
| CoVegas replay fidelity | PASS, with reference caveat | Three primary recordings: 190,277 events and 4,982,990 compared fields, zero mismatches, exact stateful replay. No independent kernel-native reference exists; this tests fidelity to the instrumented implementation, not the algorithm. Its undo_cwnd path has zero primary-trace invocations (function-level evidence only). |
| Controlled regression localization | Demonstrated | The CUBIC +1 threshold defect first differs at seq 1705: result 145 versus 146. Identical-model negatives are clean; a dormant undo control is not detected on primary traces where its path is unexercised. One seeded magnitude prediction was only partly met and is not rounded up. |
| Historical CoVegas reconstruction | Demonstrated, separate from fidelity | Fixed/v4 versus reconstructed-v3 first differs at seq 10421 / index 10420 on campaign rep4 after 10,420 matching transitions (clock-stable). Four valid acquisition runs, twelve off-period boundaries; the trigger was one in nine boundaries, not one in nine runs. The v3 candidate is a documented reconstruction, and the ABI-v2 debugger was built in the same session as the result, mitigated by precommitted controls and predictions. |
| Recorder overhead N0 | Loopback diagnostic only | About 7,933 ns/callback baseline versus about 232 ns no-wakeup (about 34x); not a production topology or a non-interference result. |
| Recorder non-interference | FAIL on the tested VM | Instrumentation changed observed behavior on the Kali VM. Zero overhead or behavioral neutrality is not established. The supporting Kali report is absent from this checkout and survives only as the audit's verdict. |
| Native network experiments | Historical measured runs | Fifteen 30-second Reno/CUBIC runs on the Kali testbed. They are real measurements, not outcomes predicted by replay. |

Research novelty remains YELLOW: the local prior-art review did not complete its DETER analysis. Do not claim invention of deterministic TCP replay, userspace congestion control, generic differential debugging or checkpointing.

## Checks run on this checkout (20 October 2026)

Environment: existing `.venv` (Python 3.14.4), Node 22.22.1, WSL2 kernel `6.18.33.2-microsoft-standard-WSL2`, CONFIG_HZ=250. Frontend dependencies were restored with the unchanged lockfile; no versions were upgraded. Branch `presentation/ccreplay-studio`, unchanged HEAD `056acb5`, uncommitted source work preserved. The API and custom sources run as uid 65534 in the accessible prepared copy; the privileged agent runs separately.

| Check | Observed outcome |
|---|---|
| `pytest -q` | 131 passed, 0 skipped: 47 original local tests, all 27 restored friend tests, and current workbench/checkpoint/import/packaging regressions. |
| Custom algorithm tests | 28 passed: the existing 19 plus initialized-state history, independent keys, edit/negative controls, invalid finite-JSON state, immutable initialization and recording-offset rejection. |
| Restored friend work | All 27 permanent C6/ablation/Kali tests pass after import/root adaptation. Complete C6 manifest, 511 mutants, 3,982 comparison rows and 25 controls are historical artifacts; no full campaign rerun. |
| Actual source-editor identity | Audit diagnostic reproduced validation success then missing-name failure before fix; after runtime identity normalization it completes replay. Regression covers actual namespace source, full Mode A/B, capsule reload after registry removal, computed rule edit and verified checkpoint. |
| Studio smoke | ALL PASS, including exact values/private state and schema-2 checkpoint suffix length 205. |
| CLI demo run-all | PASS: negative control, actual 145/146 difference, complete checkpoint suffix, historical CoVegas reconstruction at seq 10421. |
| Frontend build / lint | Exit 0; lazy Plotly large-chunk warning and two existing effect lint warnings. |
| Real native WSL runs | 30-second Reno and CUBIC runs completed with actual socket/qdisc telemetry, matching configuration except controller, final receiver throughput; stop/double-stop preserves samples and leaves unavailable final throughput null. |
| Additional host qualification | Fresh 3-second Recorded CUBIC and CoVegas attached the actual corresponding data controller, finalized valid unique recordings, passed self-replay on these executions, and cleaned resources. Historical CUBIC remains PARTIAL; CoVegas retains its weaker-reference caveat. |
| Real capture and custom traffic | Actual attached `ccr_reno` data socket; finalized zero-drop/gap recording, self-replay PASS, unique recording/hash and real worker replay; edited send/pause source runs as uid 65534. Crash, wall-time timeout and preparing cancellation retain evidence and clean owned resources. |
| Forced agent death | A repeat run found the old recovery killed the recorder before live traffic stopped, leaving a registered map. Fixed reverse process shutdown and journaled exact BPF map ID/name/BTF identity. Repeated SIGKILL recovery removed owned processes, namespaces and registration, preserving interrupted/non-replayable evidence. Foreign registrations are refused. |
| Offline agent / native comparison browser | PASS: four actual-measurement comparison plots and final throughput; stopped agent disables live start with setup instructions while cached saved-run telemetry remains available. |
| Server restart | PASS: shutting down during a live algorithm worker kills its process group and marks the job interrupted; after restart, a completed debugger session still opens with its saved seq-1705 computed difference. |
| Recording archive | Archive SHA-256, all 603 original files and all 77 retained recording-family hashes reverified; 604 total archive members including the manifest. |
| Browser follow-up | PASS: two new independent stateful files, accumulated private history, source names/template, equal-source/edit controls, initialization-preserving reload/rerun/export, invalid interface/state and nonzero-offset errors, cancellation; actual built-in source editor no-op/edit/checkpoint/fix; CoVegas capture toggle reset. |
| Browser | PASS against the real normal-user API/workers and agent: independent-algorithm demo/import/edit/equal sources/threshold semantics/errors/120-second timeout/history/export/refresh; 78,688-event no-op, 145/146 debugger/seq/source/checkpoint, parameter and no-op/+1/fix source workflows, 1366×768/125% zoom/1920×1080, native measurements, edited traffic capture → exact new recording → replay; no page errors. |

Follow-up evidence: `/tmp/ccreplay-followup/` contains the before/after editor diagnostic, 131-test results, smoke/demos/build/lint, actual host lifecycle/capture and full browser logs. Earlier `/tmp/ccreplay-build-logs/` contains prior host logs and recovery manifests; ignored `runtime/acceptance/browser/` contains browser screenshots, exported computed result and successful-run IDs. Earlier failed attempts remain in logs and are not counted as passes. No historical fidelity campaign was rerun merely for UI edits.

## Checkpoint save/resume boundary: fixed in this checkout

The audited code saved private state before event K but resumed at K+1, skipping event K. A synthetic stateful counter showed it: the full run first differed at index 5, the checkpoint was at index 4 with pre-event state n=4, and the resumed run found no difference (reproduced here before the fix). The controlled CUBIC example hid it because the checkpoint at 1500 was far from the divergence at 1704.

Now (schema 2): checkpoints store `next_event_index` and the pre-event state, and resume executes K through D inclusive. K=1500, D=1704 is 205 transitions including the failing event; the earlier 204 count was produced by the skip and is not preserved. Reproduction compares position, fields, computed values and post-event private states. Controller equations were not changed. Regression coverage in `tests/test_checkpoint_boundary.py` and the updated CUBIC and Replay-session tests: difference after, exactly on, and before the first checkpoint, last-event difference, every interval from 1 to the trace length, rejection of schema 1, value-level comparison, and an emulated K+1 resume that must miss the difference.

This supports reproduction on the tested cases (synthetic counter, CUBIC rep1, CoVegas rep4). It is not a general guarantee for arbitrary controllers, and checkpoints saved under schema 1 must be regenerated.

## Earlier findings now addressed

The following issues from the audit are covered by unit tests in this checkout (`tests/test_controller_validation.py`, `tests/test_recording_registry.py`, `tests/test_replay_session.py`):

- Determinism validation compares complete output and next-private-state streams across fresh and reset executions, and requires per-event fields; a hidden counter fails it. It remains a finite sample, not a proof.
- Saving a controller never overwrites an earlier revision, and parameter edits reject unknown keys and coerced types. Legacy history rows that stored only mutable controller IDs remain legacy where original code bytes are unavailable.
- Uploads are staged and published atomically; a corrupt recording or wrong sidecar leaves no file, and a missing sidecar is recorded as integrity unknown.

## Open issues and blockers

1. The optional PDF handbook is omitted: its generator needs the absent `reportlab` dependency; the old supplied PDF predates these features. Current documentation is the maintained Markdown set.
2. The earlier local C6 stage-one program is preserved separately from the completed friend AST campaign, now recovered from the review subset with all 18 original C6 files externally archived. The 25-file recovery is independently hashed; it does not turn the 603-file local snapshot into a complete friend-archive snapshot. Historical results were not rerun. Full C6 and C2/C3 repetition require explicitly restored recordings/datasets.
3. Historical CUBIC fidelity remains PARTIAL (clock ambiguity), and recorder non-interference remains FAIL on the tested VM. New per-run qualification never upgrades those historical verdicts.
4. A normal-user application and separately privileged agent are required. This host's exact numeric-uid prepared-copy startup is documented; privileges are not needed for recorded or teaching-algorithm debugging.

## What can be claimed

- Compatible implementations can be executed on the same recorded callback inputs.
- Exact declared-field differences can be localized to a recorded event and callback, and reproduced from a checkpoint.
- The retained controlled examples are executable and repeatable in this checkout.
- Live Reno capture and native Reno/CUBIC execution work on this tested WSL kernel. Other hosts require fresh build/attachment/model checks.

## Limits that remain visible

1. Shared TCP state is injected from the recording at every event; there is no alternate TCP-core evolution.
2. Different Replay ABIs cannot be mixed as one trace contract.
3. Agreement covers the selected recording, connection and compared fields, not every possible input.
4. Clock ambiguity limits the historical CUBIC fidelity claim.
5. CoVegas lacks the independent kernel reference available for Reno and CUBIC.
6. Empty controls, missing metadata or dropped critical records must not produce an unqualified agreement claim.
7. The live wrapper is the active controller; recorder instrumentation is not assumed behaviorally free.
8. A recorded cwnd plot is not a computed candidate trajectory.
9. Host and browser acceptance is specific to the tested checkout, viewports and kernel; no inherited universal-support claim.

## Final review pass — 27 October 2026

This pass implements the six-route review workflow, same-ABI whole-recording behavior summaries, bounded comparison_profile_v1 aggregates, anchored event investigation, complete cursor-paged native-run charts and prominent condition/readback checks. Historical verdicts above are unchanged.

- Frontend production build: PASS; existing lazy Plotly size warning. Lint: exit 0, three state-in-effect warnings.
- `.venv/bin/python -m pytest -q`: **136 passed**, seven dependency/lifespan deprecation warnings (30.37 s outside the sandbox). The sandboxed attempt stalled in async TestClient; it is not counted as a pass.
- `.venv/bin/python scripts/studio_smoke.py`: ALL PASS on the retained recordings.
- `PATH="$PWD/.venv/bin:$PATH" bash scripts/demo/demo_00_run_all.sh`: PASS, including historical CoVegas reconstruction and 205-transition checkpoint.
- `node scripts/frontend_contracts.mjs`: PASS: complete 1,201-sample pagination test, cursor guard, native eligibility, condition matching and actual tc readback unit/mismatch/unknown checks. Test samples are explicitly unit-test inputs, never presented as measurements.
- Source release packaging: PASS, 250 allowlisted files; dependencies, owner state and local notes excluded.
- Browser for this pass: NOT VERIFIED pending explicit permission. Automatic approval review rejected both broad and narrowed non-root test copies because they expose source/recordings to another local account. Chromium is installed in the temporary test folder; the full current browser gate is maintained but has not executed.
- Privileged live-network qualification for this pass: NOT VERIFIED. No privileged experiments were initiated. No saved complete native pair was present in this checkout.
- Seven confirmed unrouted legacy frontend pages/components removed. Pre-existing missing tracked traces/evidence/build files are excluded from staging; their deletions are not part of this change. Owner runtime/controllers, dependency trees, local archives and implementation instructions remain local.

Command logs and recovery patch/untracked snapshot: `/tmp/ccreplay-final-review/`. Those local artifacts are not project deliverables. Earlier dated browser/host entries above are historical and are not inherited by this pass.
