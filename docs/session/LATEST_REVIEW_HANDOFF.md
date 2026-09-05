# CCReplay — Final Integrated Session — Review Handoff

**One-file review packet**, assembled incrementally as the session runs (not reconstructed at the
end). A reviewer who understands CCReplay's architecture should be able to audit the whole session
from this file. Individual reports / data files / scripts / git history remain authoritative for
their evidence.

---

## SESSION IDENTITY

```text
SESSION:                 Final Integrated Session  (docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md, phases 0-18)
DATE:                    2026-09-05
STARTING COMMIT:         263ca60  "audit: re-derive Predicate-H time-origin offset from harness order"
ENDING COMMIT:           <filled at Phase 18>
FORMAL VERDICTS AT START: Reno v0 PASS | CUBIC v1 R3 PARTIAL | CUBIC clock residual ATTRIBUTED_AND_CHARACTERIZED
                          | CoVegas v2 self-replay PASS | Historical CoVegas A3 INCOMPLETE
FORMAL VERDICT CHANGES:   <none unless a qualifying result is obtained; tracked per phase>
NEW NETWORK CAPTURES:     <tracked at Phase 8>
NEW DIFFERENTIAL REPLAY:  <tracked at Phase 10>
```

### Binding claim boundary (verbatim, used in all current-facing docs)

> CCReplay answers what a congestion-control implementation computes at a recorded callback
> boundary. It does not claim what network trajectory or performance that implementation would have
> produced.

### Authorized scope

Offline: ABI compat matrix; CoVegas control-flow audit; reconstructed-v3 A3-only candidate +
positive/negative controls + guard-ratio analysis; deterministic professor-demo package; full
regression suite. Network: ONE capped historical capture campaign (`HOLD_MS=500`, validated
Gate-3-R2 topology, ABI v2, fixed/v4) — `MAX_VALID_RUNS=9`, `MAX_VALID_BOUNDARIES=27`,
`MAX_TOTAL_ATTEMPTS=12`; STOP on first same-episode H+D. Optional: replay performance
characterization (dropped first under time pressure). **Forbidden:** upgrade CUBIC R3; call the
historical case FAIL; claim A3 localization without a qualifying diff; general byte/bit exactness;
claim ~780 ns measured; claim CoVegas `undo_cwnd` ABI-v2 trace validation; change `HOLD_MS`/workload
params; exceed the cap; arbitrary event deletion; weaken an oracle; redefine H/D after results;
rewrite predictions; modify `~/cn-spike` / `~/cn` / `~/cn-spike/covegas`.

### Planned phase order

0 ABI compat matrix → 1 CoVegas control-flow audit → 2 precommit A3 predictions → 3 reconstructed-v3
candidate → 4 positive/negative controls → 5 guard-ratio analysis → 6 professor demo package →
7 precommit capture campaign → 8 capture campaign → 9 outcome matrix → 10 conditional historical
diff → 11 freeze/close → 12 optional historical demo → 13 optional performance → 15 full regression
→ 16 git ordering → 17 handoff assembly + adversarial self-check → 18 terminal summary.

### Commit trail (in order)

```text
263ca60  (start)
<phase commits appended here>
```

---

## PHASE 0 — ABI COMPATIBILITY MATRIX

**Result: `ABI_COMPATIBILITY = CLEAN` — 0 `MISPARSED` cells.** Full report:
`REPORT_ABI_COMPATIBILITY_MATRIX.md`; data: `data/abi_compat_matrix.json`; script:
`data/audit_src/abi_compat_matrix.py`.

| boundary | v0 trace | v1 trace | v2 trace |
| --- | --- | --- | --- |
| `ccr_trace.parse_trace` (v0) | ACCEPTED_CORRECTLY | REJECTED_CLEANLY (`unknown trace_version 1`) | REJECTED_CLEANLY (`unknown trace_version 2`) |
| `ccr_trace_v1.parse_trace_v1` (v1) | REJECTED_CLEANLY (`unknown trace_version 0`) | ACCEPTED_CORRECTLY | REJECTED_CLEANLY (`unknown trace_version 2`) |
| `ccr_trace_v2.parse_trace_v2` (v2) | REJECTED_CLEANLY (`unknown trace_version 0`) | REJECTED_CLEANLY (`unknown trace_version 1`) | ACCEPTED_CORRECTLY |
| `ccreplay_diff._detect_version_and_parse` | ACCEPTED_CORRECTLY | ACCEPTED_CORRECTLY | REJECTED_CLEANLY (`ValueError: unsupported trace_version 2`) |
| `validate_run` / `_v1` / `_v2` (own version) | ACCEPTED_CORRECTLY (`pass=True`) | ACCEPTED_CORRECTLY (`pass=True`) | ACCEPTED_CORRECTLY (`pass=True`) |

Committed-trace re-verification: all 10 committed `.ccr` (3× v0, 4× v1, 3× v2) re-parse and
re-validate; recomputed `pass` == committed `pass` for every one. `unittest` 40/40 OK.

Design note: there is no single auto-dispatching parser — each replay entrypoint hardcodes the
parser for its ABI version; `ccreplay_diff` peeks the header and dispatches v0/v1 (v2 rejected
cleanly). No `MISPARSED` path exists at any official boundary.

`ABI_COMPATIBILITY = CLEAN → continue.`

---

## PHASE 1 — COVEGAS CONTROL-FLOW AUDIT

_(appended after Phase 1)_

## PHASE 2 — A3 PRECOMMIT

_(appended after Phase 2)_

## PHASE 3 — RECONSTRUCTED-v3 CANDIDATE

_(appended after Phase 3)_

## PHASE 4 — CANDIDATE CONTROLS

_(appended after Phase 4)_

## PHASE 5 — GUARD-RATIO ANALYSIS

_(appended after Phase 5)_

## PHASE 6 — PROFESSOR DEMO PACKAGE

_(appended after Phase 6)_

## PHASE 7–11 — HISTORICAL CAPTURE CAMPAIGN + OUTCOME

_(appended per attempt / per phase)_

## PHASE 13 — PERFORMANCE

_(appended or SKIPPED)_

## PHASE 15 — FULL REGRESSION SUITE

_(appended)_

## PHASE 17 — ADVERSARIAL SELF-CHECK

_(appended)_

## PHASE 18 — TERMINAL SUMMARY

_(appended)_
