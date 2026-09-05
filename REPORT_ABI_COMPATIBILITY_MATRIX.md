# Replay ABI Compatibility Matrix

Two audits, both preserved: the **initial Phase-0 matrix** (code state where `ccreplay_diff.py`
supported v0/v1 and rejected v2 cleanly) and the **final post-v2-extension matrix** (final
repository state, after Phase 3 added Replay-ABI-v2 support to the differential debugger and Phase
10 to the checkpoint reproducer).

Script: `data/audit_src/abi_compat_matrix.py`. Data: `data/abi_compat_matrix.json` (both sections).

---

## Named evidence limitation — v2 differential path implemented in the result-producing session

> The Replay-ABI-v2 differential-debugger path (`user/ccreplay_diff.py` and
> `user/ccreplay_checkpoint.py`, `trace_version == 2` dispatch + the mode-dependent
> `comparison_fields(callback_id, pre_mode, post_mode)` schema, ADR-023) was **implemented during
> the same integrated session that produced the CoVegas historical differential result**. Its
> correctness therefore does not have the same prior independent validation history as the older
> v0/v1 path. The main mitigations are: the precommitted synthetic Predicate-D positive control
> (`data/a3_reconstructed_candidate_predictions.md` §2.2, `b8af8c1`); the `fixed-v4`/`fixed-v4` hard
> negatives; the `fixed-v4`/`reconstructed-v3` negatives on the three Predicate-D-absent original
> traces; the **final ABI/version-dispatch regression** below; **7 permanent automated tests**
> (`tests/test_ccreplay_diff_v2.py`, suite 40 → 47); and exact agreement with the precommitted
> historical first-divergence prediction (first divergence at `seq=10421`, `cong_avoid`).

This is a provenance caveat, **not** an invalidation of the result.

---

## INITIAL PHASE-0 MATRIX (frozen — code state at Phase 0)

At Phase 0, `user/ccreplay_diff.py` supported v0/v1 and returned `ValueError("unsupported
trace_version 2")` for v2.

| boundary | v0 trace | v1 trace | v2 trace |
| --- | --- | --- | --- |
| `ccr_trace.parse_trace` (v0) | ACCEPTED_CORRECTLY | REJECTED_CLEANLY | REJECTED_CLEANLY |
| `ccr_trace_v1.parse_trace_v1` (v1) | REJECTED_CLEANLY | ACCEPTED_CORRECTLY | REJECTED_CLEANLY |
| `ccr_trace_v2.parse_trace_v2` (v2) | REJECTED_CLEANLY | REJECTED_CLEANLY | ACCEPTED_CORRECTLY |
| `ccreplay_diff._detect_version_and_parse` | ACCEPTED_CORRECTLY | ACCEPTED_CORRECTLY | **REJECTED_CLEANLY** (`ValueError: unsupported trace_version 2`) |
| `validate_run` / `_v1` / `_v2` (own version) | ACCEPTED_CORRECTLY | ACCEPTED_CORRECTLY | ACCEPTED_CORRECTLY |

```text
PHASE-0 MISPARSED CELLS: 0   (v2-through-diff was a clean rejection, by design at that point)
```

This result is historically correct for that code state and is **not erased**.

---

## FINAL POST-v2-EXTENSION MATRIX (final repository state)

Traces: `raw/r0/rep1.ccr` (v0), `raw/cubic_replay/primary/rep1.ccr` (v1),
`raw/covegas_replay/primary/rep1.ccr` (v2).

| boundary | v0 trace | v1 trace | v2 trace |
| --- | --- | --- | --- |
| `ccr_trace.parse_trace` (v0) | **ACCEPTED_CORRECTLY** | REJECTED_CLEANLY (`unknown trace_version 1`) | REJECTED_CLEANLY (`unknown trace_version 2`) |
| `ccr_trace_v1.parse_trace_v1` (v1) | REJECTED_CLEANLY | **ACCEPTED_CORRECTLY** | REJECTED_CLEANLY |
| `ccr_trace_v2.parse_trace_v2` (v2) | REJECTED_CLEANLY | REJECTED_CLEANLY | **ACCEPTED_CORRECTLY** |
| `ccreplay_diff._detect_version_and_parse` | **ACCEPTED_CORRECTLY** | **ACCEPTED_CORRECTLY** | **ACCEPTED_CORRECTLY** |
| `validate_run` / `_v1` / `_v2` (own version) | **ACCEPTED_CORRECTLY** (`pass=True`) | **ACCEPTED_CORRECTLY** (`pass=True`) | **ACCEPTED_CORRECTLY** (`pass=True`) |

```text
FINAL_MISPARSED_CELLS = 0
```

### v2 differential regression checks (run as part of this audit)

| check | result |
| --- | --- |
| `fixed-v4` vs `fixed-v4` on `raw/covegas_replay/primary/rep1.ccr` | **NO DIVERGENCE** |
| `fixed-v4` vs `reconstructed-v3` on `raw/covegas_replay/primary/rep1.ccr` | **NO DIVERGENCE** |
| `fixed-v4` vs `reconstructed-v3` on `raw/covegas_replay/primary/rep2.ccr` | **NO DIVERGENCE** |
| `fixed-v4` vs `reconstructed-v3` on `raw/covegas_replay/primary/rep3.ccr` | **NO DIVERGENCE** |
| `fixed-v4` vs `reconstructed-v3` on `raw/covegas_campaign/rep4.ccr` | **DIVERGENCE — first divergence `seq=10421`, `cong_avoid`** |

### Committed-trace re-verification

All committed `*.ccr` with a committed `*_validation.json` re-parse and re-validate; recomputed
`pass` == committed `pass` for every one (3× v0, 4× v1 (incl. `undo_cwnd` aux), 3× v2 primary, 4× v2
campaign). (`raw/r0/rep_validation.json` — a pre-existing zero-byte-name artifact with no matching
`.ccr` — is skipped, not an error; not created by any session.)

Automated regression: `python3 -m unittest discover -s tests` → **47/47 OK** (was 40; +7
`tests/test_ccreplay_diff_v2.py`).

## Gate

```text
FINAL ABI_COMPATIBILITY = CLEAN
FINAL_MISPARSED_CELLS   = 0
v2 differential regression = OK
```
