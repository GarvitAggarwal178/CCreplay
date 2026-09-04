# CUBIC Capability + Reference Audit (N1.1 / N1.2 / N1.3 / clock-window hazard)

**Naming note:** this file is `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`'s `data/r3_cubic_capability_audit.md`,
renamed to match `docs/REPO_WORKFLOW.md`'s public-facing naming convention. The other three N1
deliverables follow the same mapping:

| Pipeline doc name | Actual committed name |
| --- | --- |
| `data/r3_cubic_capability_audit.md` | `data/cubic_replay_capability_audit.md` (this file) |
| `data/r3_contract_predictions.md` | `data/cubic_replay_contract_predictions.md` |
| `data/r3_callback_coverage_plan.md` | `data/cubic_replay_callback_coverage_plan.md` |
| `data/r3_model_changes.md` | `data/cubic_replay_model_changes.md` |

Kernel under audit: `6.18.33.2-microsoft-standard-WSL2`, x86_64. All findings below are from direct
inspection of the live running kernel (`/sys/kernel/btf/vmlinux`, `/proc/config.gz`) and real
compile+verifier-load smoke tests, per `INSTRUCTIONS.md` §6 (documentation precedes semantic
implementation) and the "not assumed from upstream" instruction in pipeline N1.1. Nothing here is
carried over from Phase-1 reconnaissance or from memory of upstream Linux source.

---

## N1.1 — Reference implementation determination

### BTF presence (kernel CUBIC internals)

`bpftool btf dump file /sys/kernel/btf/vmlinux format raw` shows the kernel's own CUBIC
implementation compiled in, all `linkage=static`:

```
[137277] STRUCT 'bictcp' size=60 vlen=17
[138746] FUNC 'cubictcp_acked' type_id=90051 linkage=static
[138747] FUNC 'cubictcp_cong_avoid' type_id=90036 linkage=static
[138749] FUNC 'cubictcp_cwnd_event' type_id=138748 linkage=static
[138750] FUNC 'cubictcp_init' type_id=21766 linkage=static
[138751] FUNC 'cubictcp_recalc_ssthresh' type_id=53527 linkage=static
[138752] FUNC 'cubictcp_register' type_id=124 linkage=static
[138753] FUNC 'cubictcp_state' type_id=90055 linkage=static
[138754] FUNC 'cubictcp_unregister' type_id=126 linkage=static
```

No `cubictcp_undo*` symbol exists anywhere in BTF (`grep -iE "cubictcp_undo|cubic.*undo"` against a
full raw BTF dump: zero matches) — the kernel's CUBIC shares `tcp_reno_undo_cwnd` for `undo_cwnd`,
same as Phase-1's Reno wrapper and same as the read-only `bpf_cubic.c` port (line 532/537).

`tcp_slow_start` and `tcp_cong_avoid_ai` (used by `bpf_cubic.c` during slow start) are also present:

```
[111546] FUNC 'tcp_cong_avoid_ai' type_id=111545 linkage=static
[111567] FUNC 'tcp_slow_start' type_id=111566 linkage=static
```

`CONFIG_X86_64=y` and `CONFIG_DYNAMIC_FTRACE=y` (`/proc/config.gz`) — upstream Linux
(`net/ipv4/bpf_tcp_ca.c`) gates CUBIC kfunc registration behind exactly this pair, so BTF presence
plus this config combination is consistent with (but, per the rule below, not proof of) kfunc
registration.

### Callability — actual verifier result, not inferred from BTF/config alone

BTF presence and plausible kconfig gating were **not** treated as sufficient (Phase 1 already found
one case — `bpf_get_socket_cookie()` — that was BTF-present and config-plausible but
verifier-rejected on this program type). A disposable probe,
`data/audit_src/audit_cubic_kfuncs.bpf.c`, declares `cubictcp_init`, `cubictcp_cong_avoid`,
`cubictcp_recalc_ssthresh`, `cubictcp_state`, `cubictcp_cwnd_event`, and `tcp_reno_undo_cwnd` as
`__ksym` externs inside six `struct_ops` programs and was compiled (`clang -target bpf`, exit 0) and
loaded (`bpftool prog loadall ... type struct_ops`, exit 0):

```
LOADALL_EXIT=0
258: struct_ops  name audit_cubic_init         tag 8fecf63761024bc3  gpl
259: struct_ops  name audit_cubic_cong_avoid    tag 096c4f299e4c2ce8  gpl
260: struct_ops  name audit_cubic_ssthresh      tag 9b4bdc871812229f  gpl
261: struct_ops  name audit_cubic_state         tag b44cc0062f438bb3  gpl
262: struct_ops  name audit_cubic_cwnd_event    tag 4d7cdd6e6f635654  gpl
263: struct_ops  name audit_cubic_undo          tag 1b2f2b81ffbcbc68  gpl
```

Real kernel program IDs were assigned to all six programs; pinned `.bpf` files were present under
`/sys/fs/bpf/audit_cubic_dir/`; `dmesg` showed no verifier warnings. This is the same load-level
proof standard used for the Reno kfuncs in Phase 1. **Verdict: all six real kernel CUBIC/shared
functions are BTF-present, config-consistent, and independently verifier-load-confirmed callable
from `struct_ops` on this kernel.**

`bpf_jiffies64()` and a direct read of `tcp_sk(sk)->tcp_mstamp` from a `struct_ops/cong_avoid`
program were also compiled and verifier-loaded successfully (`data/audit_src` inline probe,
`LOAD_EXIT=0`) — both of CUBIC's two internal clock sources (see clock-window hazard section below)
are readable from our program type.

### Chosen reference strategy

**Prefer the real kernel functions (Oracle C, same architecture as Phase-1 Reno) for recording.**
`cubictcp_init` / `cubictcp_cong_avoid` / `cubictcp_recalc_ssthresh` / `cubictcp_state` /
`cubictcp_cwnd_event` / `cubictcp_acked` / `tcp_reno_undo_cwnd` will be called directly as kfuncs
from the CUBIC recorder wrapper's `struct_ops` programs, exactly as `tcp_reno_cong_avoid` etc. were
for Reno. This is a **stronger** oracle than delegating to the read-only `bpf_cubic.c` port, which
deliberately reimplements the CUBIC math itself (`cubic_root`, `bictcp_update` — confirmed by
reading `~/cn-spike/bpf_src/bpf_cubic.c` lines 239–383) rather than calling the kernel's own
`cubictcp_*` functions, and which its own header comment (lines 3–14) states is "not necessarily
the same as tcp_cubic.c."

The read-only `bpf_cubic.c` source is still used in this audit as the **structural reference** for
which fields each real callback reads/writes and which two clocks it depends on (Sections N1.3/N1.5
below and the clock-window hazard section) — its algorithm is a line-for-line port of
`net/ipv4/tcp_cubic.c`'s callback structure and field usage (per its own header comment), even
though its arithmetic is not literally the compiled kernel code invoked at record time. Field-level
and callback-level claims in this document (which fields are read/written by which callback, which
clocks are consulted) are therefore **inferred from a structurally faithful port**, not from
disassembly of the real compiled kernel functions — this is weaker than the private-state layout
ground truth in N1.3 below (which comes directly from this kernel's own BTF and `offsetof`/`sizeof`)
and is stated as a limitation. Per pipeline N1.1's required framing:

> This oracle validates CCReplay's replay architecture — Replay Contract sufficiency, ordering,
> time semantics, and private-state propagation. It does not independently prove the correctness of
> the CUBIC implementation itself.

That statement applies twice over here: once for the usual "record vs. replay-model" split (as in
Phase 1), and a second time for "which fields/clocks the real kernel functions consult," which is
inferred from a structural port rather than ground-truthed against kernel object code.

---

## N1.2 — Preserve CUBIC's real state architecture

CUBIC's private state (`struct bictcp`, kernel-internal name; `struct bpf_bictcp` in the read-only
port) lives in `icsk_ca_priv` (`struct inet_connection_sock`), confirmed via BTF:
`u64 icsk_ca_priv[13]` — 104 bytes, `struct bictcp` is 60 bytes (N1.3), fits with room to spare. The
CUBIC recorder wrapper will call the real kernel functions against the real socket's real
`icsk_ca_priv` — **no `SK_STORAGE` migration of CUBIC's algorithm state.** `SK_STORAGE` remains
available only for recorder-owned bookkeeping (e.g. a per-socket "have we recorded `init` for this
socket yet" flag), matching Phase-1's precedent (validated in R0 capability audit, unused by the
Reno wrapper since Reno has no `.init`).

---

## N1.3 — Ground-truth private-state layout

**Correction to prior reconnaissance:** an earlier (pre-Phase-1) pass reportedly said "15 fields"
while listing 16 names. Ground truth, derived below via compiled `offsetof`/`sizeof` against a
struct whose field list/types/order were read verbatim from this kernel's own live BTF (not
retyped from memory, not from upstream source): **17 total struct members, 16 semantically
meaningful, 1 explicit compiler-visible-but-algorithmically-dead field (`unused`, a `u16` literally
named "unused" in the struct definition — not compiler-inserted alignment padding; there is no
compiler-inserted padding anywhere in this struct, see below).**

Tool: `data/audit_src/print_offsets_cubic.c`. It deliberately does not include `vmlinux.h` (which
collides with libc's `wchar_t` under a native compile target); instead it defines a standalone
`struct bictcp` with the exact field list, types, and order `bpftool btf dump ... format c` reported
for the live kernel's `struct bictcp`, then lets the compiler compute `offsetof`/`sizeof` — i.e. the
offsets below are compiler-derived from BTF-sourced ground truth, never hand-computed. Cross-check:
computed `sizeof(struct bictcp) == 60`, matching BTF's independently-reported `STRUCT size=60` —
`PASS`.

| field | offset | size | type | read by | written by | purpose |
| --- | ---: | ---: | --- | --- | --- | --- |
| `cnt` | 0 | 4 | `u32` | `cong_avoid` (via `tcp_cong_avoid_ai(tp, ca->cnt, acked)`) | `cong_avoid` (`bictcp_update`) | cwnd increase divisor computed by the cubic curve; consumed once per `cong_avoid` call |
| `last_max_cwnd` | 4 | 4 | `u32` | `cong_avoid` (`bictcp_update`) | `ssthresh` (`cubictcp_recalc_ssthresh`), `cong_avoid` (`bictcp_update`, when `epoch_start==0`) | last `Wmax` before the most recent reduction; anchors the cubic curve's origin |
| `last_cwnd` | 8 | 4 | `u32` | `cong_avoid` (early-return de-dup check) | `cong_avoid` | last observed `snd_cwnd`; used to skip redundant recompute within the same jiffy |
| `last_time` | 12 | 4 | `u32` | `cong_avoid` (de-dup / epoch checks) | `cong_avoid` | jiffies value at the last `bictcp_update` recompute |
| `bic_origin_point` | 16 | 4 | `u32` | `cong_avoid` (`bic_target` calc) | `cong_avoid` (start of new epoch) | cubic function's origin cwnd for the current epoch |
| `bic_K` | 20 | 4 | `u32` | `cong_avoid` (`offs` calc) | `cong_avoid` (start of new epoch, via `cubic_root`) | time-to-origin-point in `2^bictcp_HZ` units |
| `delay_min` | 24 | 4 | `u32` | `cong_avoid` (`bictcp_update`'s `t` calc), `pkts_acked` (HyStart threshold) | `pkts_acked` (min RTT sample tracking) | minimum observed RTT sample (usec); the primary cross-callback (`pkts_acked` → `cong_avoid`) private-state dependency |
| `epoch_start` | 28 | 4 | `u32` | `cong_avoid`, `pkts_acked` (freshness gate), `cwnd_event` (idle-shift) | `cong_avoid`, `ssthresh` (reset to 0), `cwnd_event` (idle shift) | jiffies at start of current cubic epoch; `0` is a sentinel meaning "recompute needed" |
| `ack_cnt` | 32 | 4 | `u32` | `cong_avoid` (tcp-friendliness blend) | `cong_avoid` | running ACKed-packet counter for the Reno-friendliness blend |
| `tcp_cwnd` | 36 | 4 | `u32` | `cong_avoid` (tcp-friendliness blend) | `cong_avoid` | shadow "what Reno would have done" cwnd estimate |
| `unused` | 40 | 2 | `u16` | — | — | dead field; never read or written anywhere in the reference port. Excluded from the Mode-B private-state comparison schema (semantic, not padding, but load-bearing-nothing) |
| `sample_cnt` | 42 | 1 | `u8` | `pkts_acked` (HyStart delay-sample gate) | `pkts_acked`, `cong_avoid`→`bictcp_hystart_reset` (reset to 0) | count of HyStart delay samples collected this round |
| `found` | 43 | 1 | `u8` | `pkts_acked` (HyStart gate) | `cong_avoid`/`set_state`→`bictcp_reset` (reset to 0), `pkts_acked`→`hystart_update` (set to 1) | HyStart "exit point found" flag |
| `round_start` | 44 | 4 | `u32` | `pkts_acked`→`hystart_update` (ack-train check) | `cong_avoid`/`init`/`set_state`→`bictcp_hystart_reset` | `tcp_mstamp` at the start of the current HyStart round |
| `end_seq` | 48 | 4 | `u32` | `cong_avoid` (hystart-reset trigger: `after(ack, ca->end_seq)`) | `init`/`cong_avoid`/`set_state`→`bictcp_hystart_reset` | `snd_nxt` snapshot marking the end of the current HyStart round |
| `last_ack` | 52 | 4 | `u32` | `pkts_acked`→`hystart_update` (ack-train spacing) | `init`/`cong_avoid`/`set_state`→`bictcp_hystart_reset`, `pkts_acked`→`hystart_update` | `tcp_mstamp` at the last closely-spaced ACK, for ack-train detection |
| `curr_rtt` | 56 | 4 | `u32` | `pkts_acked`→`hystart_update` (delay-increase check) | `init`/`cong_avoid`/`set_state`→`bictcp_hystart_reset` (`~0U`), `pkts_acked`→`hystart_update` | minimum RTT observed in the current HyStart round |

"read by" / "written by" above are inferred from the structurally faithful `bpf_cubic.c` port (see
N1.1's caveat), not from kernel disassembly. No field in this table is compiler-inserted padding —
the struct's declared field sizes already sum to 60 bytes with natural x86_64 alignment and no
gaps, matching the BTF-reported size exactly.

---

## Clock-window hazard investigation

Per pipeline instruction, `tcp_jiffies32` was **not** assumed; the reference source was read first.
Two distinct, independent clock sources are consulted, not one:

1. **`tcp_jiffies32`** (`bpf_cubic.c` lines 199, 280, 287, 291, 293–294, 325, 515) — a **global**
   kernel jiffies counter (`(u32)jiffies`, `CONFIG_HZ=250` ground-truthed from `/proc/config.gz`,
   i.e. ~4ms resolution), *not* a per-socket field. Used throughout `bictcp_update`'s epoch/delta
   math and in `cwnd_event`'s idle-shift logic and `pkts_acked`'s post-fast-recovery discard gate.
   This is the hazardous one: it is a bare global read, not stored on `struct tcp_sock`, so it
   cannot be captured as an ordinary per-socket shared-state field the way `snd_cwnd` etc. are.
2. **`tp->tcp_mstamp`** (via `bictcp_clock_us()`, `bpf_cubic.c` lines 164–166, used at 174, 461) — a
   microsecond-resolution timestamp **already stored on `struct tcp_sock`**, updated by TCP core
   independently of the CC callback. This one fits CLAUDE.md's class-1 "recorded shared TCP input
   state" cleanly (same treatment as `snd_cwnd`/`snd_ssthresh`): it is read-only from the
   controller's perspective and can be snapshotted as an ordinary PRE-state field.

Both are confirmed **readable** from our `struct_ops` program type (verifier-load-tested,
`LOAD_EXIT=0`, see N1.1). Neither is currently present in Replay ABI v0 (Reno's math has no time
dependency at all — the Phase-1 wrapper never called `bpf_ktime_get_ns()` for any *algorithmic*
purpose, only for the trace's diagnostic `ts_ns` field).

**Recording-time plan for Replay ABI v1** (design only — not implemented in N1): the CUBIC wrapper
will read `bpf_jiffies64()` (truncated to 32 bits, matching `tcp_jiffies32`'s own truncation) and
`tp->tcp_mstamp` immediately before and immediately after each real kfunc call, and classify the
event `CLOCK_STABLE` if the before/after jiffies32 reading is unchanged, `CLOCK_AMBIGUOUS`
otherwise. Given kfunc call durations are sub-microsecond (Phase-1 N0: production recorder
`cong_avoid` cost ≈ 7,933 ns/callback including ring-buffer wakeup, and the wakeup-free path ≈ 232
ns) against a 4ms (`HZ=250`) jiffies tick, `CLOCK_STABLE` is expected to dominate overwhelmingly;
this is a prediction to be checked empirically in N2/N3, not assumed. `tp->tcp_mstamp` cannot change
during a synchronous kfunc call (only TCP core writes it, never the CC callback), so it needs no
before/after pair — one PRE snapshot suffices, same treatment as any other shared-state field.
Per the pipeline's explicit prohibition, no *other* nearby clock (e.g. the trace's existing
diagnostic `ts_ns` / `bpf_ktime_get_ns()`) is substituted for either of these two — both real
internally-read clocks will be recorded directly.

---

## Architecturally significant finding: cross-callback shared-state mutation

`bpf_cubic.c`'s `hystart_update()` (called from `pkts_acked`) directly writes
`tp->snd_ssthresh = tp->snd_cwnd` (lines 479, 494) as a **side effect of the `pkts_acked`
callback**, not through `pkts_acked`'s return value (`pkts_acked` is `void`). This differs
structurally from Reno, where `snd_ssthresh` is only ever mutated by the kernel core applying the
`.ssthresh` callback's *return value* — a class-4 "callback result" in the Phase-1 ABI. Under
CUBIC, `snd_ssthresh` is class-4 "controller-owned mutation" written directly by a *different*
callback than the one nominally responsible for ssthresh. Replay ABI v1's `pkts_acked` EventRecord
must therefore capture `post_snd_ssthresh` explicitly (not just a scalar `result`), or this mutation
is invisible to Mode A/B comparison. Also newly required as shared PRE-state, confirmed by the same
read: `tp->lsndtime` (`cwnd_event`'s idle-shift calc) and `tp->snd_nxt` (`bictcp_hystart_reset`'s
`end_seq` assignment, called from `init`/`cong_avoid`/`set_state`).

---

## Summary for N1.4/N1.5

This audit's findings feed directly into `data/cubic_replay_contract_predictions.md` (predictions
precommitted before any empirical field-mutation discovery) and
`data/cubic_replay_callback_coverage_plan.md`. No empirical recording or field-mutation capture has
been performed yet as of this file's commit — everything above is source reading, BTF inspection,
and verifier-load smoke tests, not trace-derived.
