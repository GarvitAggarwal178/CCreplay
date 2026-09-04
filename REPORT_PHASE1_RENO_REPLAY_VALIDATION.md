# CCReplay — Gates R0/R1/R2 Report

**Scope:** recorder viability (R0), Reno event-local exact semantic self-replay (R1), Reno
stateful-controller exact semantic self-replay (R2). No CUBIC, Vegas, BBR, or case-study work is
included, per `docs/IMPLEMENTATION_HANDOFF.md`.

## A. Environment

- Kernel: `6.18.33.2-microsoft-standard-WSL2` (WSL2 Ubuntu), confirmed via `uname -r` at every
  stage of this task, not assumed.
- Toolchain: `clang` 21.1.8 (Ubuntu), `gcc` 15.2.0, `bpftool` v7.7.0, `libbpf` 1.6.3, `iperf3` 3.20.
- BPF capability findings: see section B below and `data/capability_audit.md` in full (sections
  A–F: kfunc availability, `SK_STORAGE`, callback surface, timebase, empirical field-mutation
  discovery, Mode-A dry-run validation).

## B. Capability audit summary

Full detail: `data/capability_audit.md`. Headline findings:

- `tcp_reno_cong_avoid`/`tcp_reno_ssthresh`/`tcp_reno_undo_cwnd` are callable BPF kfuncs from
  `struct_ops tcp_congestion_ops` context on this kernel — confirmed by independent compile,
  verifier-load, register, and a real 60s loss-bearing transfer (206 retransmits, 9.87 Mbit/s,
  zero verifier issues, zero `dmesg` warnings), not merely by BTF presence.
- `BPF_MAP_TYPE_SK_STORAGE` (`bpf_sk_storage_get`/`bpf_sk_storage_delete`) is usable from this
  program type — confirmed by a live persistence test (273,358 monotonically-incrementing
  per-socket counter values across one real connection). **Not used by the Reno wrapper itself**
  (ADR-014: Reno has no controller-private state), but resolves ADR-010 for a future controller
  that needs it.
- `bpf_get_socket_cookie()` is **not** usable from this program type on this kernel (verifier
  rejection, confirmed by a direct load attempt against the real recorder object) — worked around
  with the raw `sk` pointer value as a within-trace socket-identity discriminator (ADR-016).
- Callback surface (direct BTF inspection): `init, ssthresh, cong_avoid, set_state, cwnd_event,
  in_ack_event, pkts_acked, min_tso_segs, cong_control, undo_cwnd, sndbuf_expand, get_info,
  release` all legal `struct_ops` hook points on this kernel. Reno's manifest uses exactly three:
  `ssthresh, cong_avoid, undo_cwnd` — matching upstream `tcp_reno_ops`, with no invented `.init`.
- `cong_avoid`'s complete mutated-field set — `{snd_cwnd, snd_cwnd_cnt}` — and its gating
  condition — `is_cwnd_limited`/`max_packets_out`, **not** in the Replay ABI doc's original
  example list — were both determined empirically from 24,651 real kernel events, not assumed
  (ADR-015). `ssthresh`'s formula (`max(cwnd>>1, 2)`) and `undo_cwnd`'s formula
  (`max(cwnd, prior_cwnd)`) were each confirmed on real events (5/5 and 8/8 respectively).
- **Before any recorder code was written**, a from-scratch userspace Reno model was run against
  the captured field-audit trace and reproduced **100.0000% of 24,651 real `cong_avoid` events
  exactly** — the R1 gate's central claim, effectively dry-run validated pre-recording.

**Reference implementation:** target-kernel `tcp_reno_*` kfuncs, called directly (Oracle C,
independent of the replay implementation). No fallback was needed.

## C. Replay ABI as actually implemented

- **Trace version:** 0 (`CCR_TRACE_VERSION`). Never bumped during this task — every field
  requirement discovered during the capability audit was folded into v0 before the first trace was
  recorded (ADR-015), so no re-recording cycle was triggered.
- **Callback manifest:** `{ssthresh, cong_avoid, undo_cwnd}` (3-bit mask, `CCR_RENO_MANIFEST`).
- **Shared PRE fields:** `snd_cwnd, snd_ssthresh, snd_cwnd_cnt, snd_cwnd_clamp, prior_cwnd,
  max_packets_out, is_cwnd_limited`.
- **Callback inputs:** `ack, acked` (meaningful for `cong_avoid` only).
- **Callback results:** `result_valid` + `result` scalar (`ssthresh`, `undo_cwnd`); `cong_avoid` is
  void, represented through `ControllerOwnedPostState`.
- **Controller-owned POST state:** `snd_cwnd, snd_cwnd_cnt` (for `cong_avoid` only — `ssthresh`/
  `undo_cwnd` are pure, POST equals PRE).
- **Private-state schema:** NONE (ADR-014) — Reno has no controller-private state under this
  Replay Contract.
- **On-disk format:** one `TraceHeader` (144 bytes, byte layout confirmed via `offsetof()` against
  the real compiled struct, not derived by eye — see `data/audit_src/print_offsets.c`) followed by
  fixed 88-byte `EventRecord`s, one per callback invocation, each holding PRE + inputs + result +
  POST in a single `bpf_ringbuf_reserve` (§8's single-record preference achieved; no split-record
  fallback needed). Full spec: `docs/REPLAY_ABI.md` "v0 concrete instantiation — Reno".
- Complete field-by-field rationale, and all four ADRs generated during this discovery process
  (ADR-013 through ADR-016 in `docs/DECISIONS.md`), are recorded there; none required loosening a
  correctness assertion.

## D. R0 — Recorder viability: **PASS**

Topology: validated Gate-3-R2 (10 Mbit/s bottleneck, 40 ms base RTT, 250,000 B = 5×BDP `bfifo`,
offloads off), copied with provenance from `~/cn-spike` (`docs/PROVENANCE.md`). 3 × 90 s SOLO Reno
transfers, `kernel.bpf_stats_enabled=1` set before every run.

| run | invocations | emitted | drops | seq gaps | trace size | events/s | ssthresh calls | cong_avoid calls | undo_cwnd calls | cong_avoid ns/callback |
|---|---|---|---|---|---|---|---|---|---|---|
| rep1 | 37,260 | 37,260 | 0 | 0 | 3,279,024 B | ~414 | 6 | 37,254 | 0 (†) | 21,768 |
| rep2 | 37,391 | 37,391 | 0 | 0 | 3,290,552 B | ~416 | 6 | 37,385 | 0 (†) | 24,975 |
| rep3 | 37,400 | 37,400 | 0 | 0 | 3,291,344 B | ~416 | 6 | 37,394 | 0 (†) | 19,922 |

(†) `undo_cwnd` did not fire on any real R0 run — real drop-tail loss is rarely spurious, so the
kernel's undo path was never entered. This does not affect R0's PASS (`docs/GATES.md`: "R0
validates every invocation of that declared surface," and the manifest's declared coverage was
fully captured — zero invocations occurred, zero were lost). Closed separately for ABI purposes via
the auxiliary reorder capture, section B above and section G item 7 below.

All three: real loss present (bfifo dropped 207/208/209 packets), throughput ≈9.87 Mbit/s (within
the topology's validated envelope), `bfifo` limit readback exactly matched 250,000 B every run,
offloads confirmed off every run. `invocations == emitted + drops` held on every run (ADR-013's
integrity identity); global sequence gapless on every run (`user/ccr_trace.py` `validate_run`, all
checks `true` on all three traces — `raw/r0/rep{1,2,3}_validation.json`). `undo_cwnd`: 0 events on
all three real runs, consistent with `data/capability_audit.md`'s finding that real (non-spurious)
drop-tail loss rarely enters the undo path — closed separately via the auxiliary reorder capture
(section B above), not by weakening R0.

**PASS conditions (docs/GATES.md R0) all met:** zero replay-critical drops; zero unexplained
sequence gaps; trace parses; every invocation of every manifest callback captured; callback result
present where required; recorder metadata read successfully at teardown, before unregistering.

## E. R1 — Reno event-local exact semantic self-replay: **PASS**

Mode A (`user/replay_r1.py`): for each event independently, recorded shared PRE + callback inputs
→ `user/reno_model.py` transition → compare declared result / controller-owned POST state exactly.

| trace | events checked | fields compared | mismatches |
|---|---|---|---|
| rep1 | 37,260 | 74,526 | 0 |
| rep2 | 37,391 | 74,788 | 0 |
| rep3 | 37,400 | 74,806 | 0 |
| **total** | **112,051** | **224,120** | **0** |

**First mismatch: none.** Comparison schema: `ssthresh` → `result`, `post_snd_cwnd`,
`post_snd_cwnd_cnt`; `undo_cwnd` → `result`, `post_snd_cwnd`, `post_snd_cwnd_cnt`; `cong_avoid` →
`post_snd_cwnd`, `post_snd_cwnd_cnt`. `ssthresh`/`undo_cwnd`'s POST fields are included, not just
their scalar result — the capability audit's claim that they are pure functions (POST==PRE) is
checked against every real R0 event this way, not merely asserted from the smaller audit captures
that originally established it (5/5 and 8/8 events respectively). All 18 real `ssthresh`
invocations across the three R0 traces confirm purity exactly; `undo_cwnd` had zero R0 invocations
to check (see section D footnote) — its purity remains backed only by the 8-event auxiliary
capture. 100% exact equality on every declared field of every valid event across all three R0
traces — the literal PASS condition, not "close."

## F. R2 — Reno stateful-controller exact semantic self-replay: **PASS**

Mode B (`user/replay_r2.py`): controller-private replay state initialized once per trace, recorded
shared TCP boundary state injected from the trace at every event (never derived from the previous
event's replay output), private state threaded through sequentially.

| trace | events replayed sequentially | first divergence |
|---|---|---|
| rep1 | 37,260 | NONE |
| rep2 | 37,391 | NONE |
| rep3 | 37,400 | NONE |
| **total** | **112,051** | **NONE** |

**State propagation:** Reno has no controller-private state (ADR-014) — `private_state` is
initialized to `NONE` once and threaded unchanged through all 112,051 sequential transitions
(confirmed by `tests/test_reno_model.py::TestPrivateStateThreading`, not merely asserted). This is
Mode B's honest behavior for a stateless controller: initialization is trivial and propagation is
vacuous, not a workaround around the gate. What R2 additionally exercises beyond R1 is genuine
sequential replay — each event is fed the actual state carried out of the previous event's call,
not a fresh reset — so the harness would still catch a future controller's state-threading bug.
No state-propagation issues occurred.

## G. Failures / deviations

Every correction made during this task, in the order discovered:

1. **Documentation location.** `~/CCReplay_Final_Documentation.zip` did not exist at `~`; found
   pre-extracted (by an earlier, unrelated process, not this session) in
   `/mnt/c/Users/Garvit/Downloads/`. Copied from there. (`data/inspection_summary.md`.)
2. **`~/cn` does not contain the described Gate 0 material** — only a copy of the frozen docs.
   Nothing reused from it; documented, not silently ignored.
3. **`~/covegas` does not exist at that path** — actual location `~/cn-spike/covegas/`. Located
   and inspected there instead.
4. **`bpf_get_socket_cookie()` verifier-rejected** from `struct_ops tcp_congestion_ops` context on
   this kernel, discovered by a direct load attempt during recorder development (not predicted by
   the capability audit's generic helper-presence check, which only confirmed the helper *exists*
   in the kernel, not that this program type may call it). Worked around with the raw `sk` pointer
   value (ADR-016); did not weaken any correctness requirement.
5. **Manifest correction:** the capability audit's section C initially declared `.init` as part of
   Reno's manifest ("to set up `SK_STORAGE`"); once section F established Reno needs no
   controller-private state at all, `.init` was removed from the manifest before any trace was
   recorded (ADR-014) — corrected in-document, not silently.
6. **Python `struct` header/event layout** was initially derived by hand from the C struct
   definition and was wrong (padding placement error). Caught before use by comparing against
   `offsetof()`/`sizeof()` output from the real compiled struct (`data/audit_src/print_offsets.c`)
   rather than trusting the by-hand derivation; the parser's format strings assert their sizes
   equal the ground-truth values (144, 88) at import time.
7. **`undo_cwnd` never fired during the primary 60s capability-audit capture** (real drop-tail loss
   is rarely spurious). Closed via a separate, explicitly-labeled auxiliary capture using a
   deliberately modified (non-Gate-3-R2) topology variant with packet reordering — kept fully out
   of the R0/R1/R2 trace set, used only to determine `undo_cwnd`'s field/formula contract for the
   ABI (`data/capability_audit.md` section E addendum).
8. **Multi-socket recording artifact.** Two independent loopback smoke tests showed a second,
   short-lived socket contributing a single stray event alongside the dominant connection
   (plausibly `iperf3` applying `-C` to its control channel). Not fully root-caused, but closed
   structurally: every `EventRecord` carries a socket-identity discriminator, and the parser
   selects/reports the dominant connection explicitly rather than silently pooling sockets
   (ADR-016). Did not recur on any of the three real R0 runs (100% single-socket on all three).
9. **`COMPARISON_FIELDS` initially checked only the scalar `result` for `ssthresh`/`undo_cwnd`**,
   not their (claimed-pure) POST state — so the report's "POST equals PRE" claim for those two
   callbacks was true of the audit captures but had never actually been checked against the R0
   traces reported as gate evidence. Caught before finalizing this report; fixed by adding
   `post_snd_cwnd`/`post_snd_cwnd_cnt` to both callbacks' comparison schema and re-running R1/R2
   against all three real traces (still 0 mismatches, first divergence still NONE — field count
   rose from 224,084 to 224,120). Sections D–F and the terminal summary below reflect the
   corrected numbers.

No compile failure, verifier rejection (beyond item 4, immediately worked around), trace-integrity
failure, or experiment failure occurred beyond what is listed above. No correctness assertion was
weakened at any point; every correction either added a required field before recording (contract
discovery, explicitly permitted by `docs/GATES.md`) or fixed an implementation bug caught by
independent verification (offsets, socket helper) before it could affect a gate result.

## H. R3 readiness

**Ready for CUBIC: partially — a defined next step, not yet started.** `data/capability_audit.md`
and this task's scope explicitly exclude implementing CUBIC; the following is read-only
reconnaissance of `~/cn-spike/bpf_src/bpf_cubic.c` (commit `022c2e2`), permitted by
`CLAUDE.md` §18, to ground next-step planning in evidence rather than guesswork.

**Likely callback manifest (7, not 3):** `init, cwnd_event, cong_avoid, ssthresh(recalc_ssthresh),
set_state, pkts_acked, undo_cwnd` — confirmed directly from `bpf_cubic.c`'s
`struct tcp_congestion_ops cubic` initializer. More than double Reno's manifest; `cwnd_event` and
`pkts_acked` are new callback types Reno's Replay ABI instantiation never had to represent.

**Private-state requirements:** real, non-trivial — `struct bpf_bictcp` (15 fields: `cnt,
last_max_cwnd, last_cwnd, last_time, bic_origin_point, bic_K, delay_min, epoch_start, ack_cnt,
tcp_cwnd, sample_cnt, found, round_start, end_seq, last_ack, curr_rtt`), stored today via
`icsk_ca_priv`, not `SK_STORAGE`. `SK_STORAGE` was validated as usable from this program type
(capability audit section B) and is the natural R3 choice, but this is a design decision to make
explicitly at R3's start, not inherited from Reno (which used neither).

**Clock/time requirements:** real — CUBIC's growth function is time-dependent (`bic_K`,
`epoch_start`, `delay_min` are all time-derived), unlike Reno. `bpf_ktime_get_ns()` is validated
available; whether CUBIC's actual field semantics need jiffies-resolution (`tcp_jiffies32`) instead
of nanosecond `ktime` is an open question requiring the same empirical field-mutation audit R0/R1/R2
used for Reno, repeated against `tcp_cubic_*` — not assumed from Reno's conclusion (Reno
specifically has *no* clock dependency; this does not generalize).

**Recorder changes anticipated:**
1. `EventRecord` grows to carry private-state PRE/POST (currently entirely absent for Reno) —
   `trace_version` bump to v1 required the moment CUBIC work begins, before any CUBIC trace is
   recorded (per `docs/REPLAY_ABI.md`'s versioning rule).
2. A `SharedTcpPreState`/`Observations` audit repeating this task's section E/F methodology against
   real `tcp_cubic_*` calls — do not assume Reno's field list transfers; CUBIC likely needs RTT
   samples (`pkts_acked`'s `ack_sample.rtt_us`) as a genuine replay input, not merely diagnostic.
3. Reference-strategy decision: first check whether `tcp_cubic_cong_avoid` etc. are callable kfuncs
   the same way `tcp_reno_*` were (Oracle C, strong); if not, the previously-validated
   `bpf_cubic.bpf.o` becomes the live reference, which `docs/CORRECTNESS_ORACLES.md` explicitly
   marks as a weaker oracle than an independent kernel reference — must be stated, not glossed
   over, in the R3 report.

**Biggest remaining blocker:** none discovered yet, because R3 capability work has not started.
The largest known unknown is whether one-record-per-callback (§8's preference, achieved cleanly
for Reno's 88-byte record) remains verifier-feasible once the record must also carry CUBIC's
~60-byte private-state PRE+POST — if not, `docs/REPLAY_ABI.md`'s split-record pairing-protocol
fallback (never needed for Reno) must be designed before R3 can proceed.

## Source repository safety check

`~/cn-spike`, `~/covegas` (nonexistent — see section G item 3), `~/cn` all verified unmodified:
tree checksums (`find | md5sum` over all tracked+untracked files, `.git` excluded) taken before any
work began (`data/readonly_repo_baseline.txt`) and re-taken after all R0/R1/R2 work completed
(`data/readonly_repo_final_check.txt`) are byte-for-byte identical. `~/cn-spike`'s pre-existing
uncommitted local changes (modified `CLAUDE.md`, untracked Gate 9/covegas material) are unchanged
from before this task and were never touched by it.

---

```text
CCReplay Phase 1

R0 RECORDER VIABILITY:                 PASS
R1 RENO EVENT-LOCAL REPLAY:            PASS
R2 RENO STATEFUL-CONTROLLER REPLAY:    PASS

KERNEL:                                6.18.33.2-microsoft-standard-WSL2
RENO KFUNCS AVAILABLE:                 YES (tcp_reno_cong_avoid/ssthresh/undo_cwnd, independent kernel reference)
SK_STORAGE FROM STRUCT_OPS:            YES (validated; not used by Reno wrapper -- no private state, ADR-014)
REFERENCE RENO STRATEGY:               target-kernel tcp_reno_* kfuncs (Oracle C)

TRACE VERSION:                         0
CALLBACK MANIFEST:                     ssthresh, cong_avoid, undo_cwnd
SEMANTIC COMPARISON FIELDS:            ssthresh->result; undo_cwnd->result; cong_avoid->{snd_cwnd, snd_cwnd_cnt}

R0 EVENTS:                             112,051 (37260 + 37391 + 37400)
R0 DROPS:                              0
R0 SEQUENCE GAPS:                      0
TRACE SIZE / 90s:                      ~3.28-3.29 MB
RECORDER NS/CALLBACK:                  cong_avoid ~20-25us; ssthresh ~17-31us (bpf_stats_enabled=1, all 3 runs)

R1 EVENTS CHECKED:                     112,051 (224,120 fields)
R1 FIRST MISMATCH:                     NONE

R2 FIRST DIVERGENCE:                   NONE

REPLAY ABI CHANGES DURING GATES:       is_cwnd_limited + max_packets_out added as required cong_avoid inputs
                                        (ADR-015, pre-recording -- no trace_version bump needed); manifest
                                        corrected to drop invented .init (ADR-014); sock_cookie uses raw sk
                                        pointer, not bpf_get_socket_cookie (unavailable, ADR-016)
SOURCE REPOS VERIFIED UNMODIFIED:      YES (checksums identical before/after)

READY FOR R3: NO (not started; see section H for concrete next steps)

MAIN BLOCKER:                          none yet -- CUBIC capability audit (kfunc availability, private-state
                                        field-mutation discovery, clock semantics) has not been attempted
REPORT PATH:                           ~/ccreplay/REPORT_GATES_R0_R1_R2.md
```
