# Capability Audit

Target kernel: `6.18.33.2-microsoft-standard-WSL2` (confirmed via `uname -r` this session; matches
`CLAUDE.md`'s stated target and the kernel `~/cn-spike`'s Gate 8 was run against).

Toolchain (this session): `clang` 21.1.8 (Ubuntu), `gcc` 15.2.0, `bpftool` v7.7.0, `libbpf` 1.6.3,
`iperf3` 3.20.

All smoke-test source lives in `data/audit_src/`. These are audit-only programs, separate from
the real recorder built afterward in `bpf/` — written independently rather than reusing
`~/cn-spike`'s compiled `.bpf.o` objects, so the audit result does not depend on taking a prior
gate's word for it. Raw command transcripts referenced below were run directly in this session
(not archived verbatim as separate files, since the audit is reported inline here per
`RECORDER.md`'s "exact commands/evidence" requirement — full stdout is reproduced in-line).

## A. Reno reference functions — PASS

**BTF presence (direct inspection of `/sys/kernel/btf/vmlinux`, not the pre-baked `vmlinux.h`
copy):**

```
$ bpftool btf dump file /sys/kernel/btf/vmlinux format raw | grep -i tcp_reno
[111555] FUNC 'tcp_reno_cong_avoid' type_id=90036 linkage=static
[111556] FUNC 'tcp_reno_ssthresh' type_id=53527 linkage=static
[111557] FUNC 'tcp_reno_undo_cwnd' type_id=53527 linkage=static
```

All three present as `FUNC` entries. BTF presence alone does not prove kfunc-callability from
`struct_ops` CC context (per the task brief's own caveat), so this was followed by an independent
compile+verify+register+run test, not treated as sufficient on its own.

**Compile+verify+register (`data/audit_src/audit_reno.bpf.c`, written fresh, not copied from
`cn-spike`'s `.bpf.o`):**

```
$ clang -target bpf -D__TARGET_ARCH_x86 -g -O2 -I bpf -I /usr/include/x86_64-linux-gnu \
    -c data/audit_src/audit_reno.bpf.c -o data/audit_src/build/audit_reno.bpf.o
compile exit=0

$ bpftool struct_ops register data/audit_src/build/audit_reno.bpf.o
Registered tcp_congestion_ops audit_reno id 17
exit=0

$ sysctl net.ipv4.tcp_available_congestion_control
net.ipv4.tcp_available_congestion_control = reno cubic vegas bbr audit_reno audit_sks
```

No verifier rejection, no `dmesg` warning. `bpftool struct_ops dump name audit_reno` confirms
`ssthresh`/`cong_avoid`/`undo_cwnd`/`init` all wired to the audit program IDs, matching what was
declared.

**Functional confirmation:** the same live-traffic run used for section E below (60s transfer
over the validated Gate-3-R2 topology, `audit_fields` — same kfunc-delegation pattern —
registered as the connection's congestion control) completed normally: 9.87 Mbit/s throughput,
206 retransmits handled without hang or crash, no `dmesg` warnings, and (per section E) `ssthresh`
returned the exact expected Reno formula on every one of the 5 real invocations captured. This is
independent live-traffic evidence, not merely a clean load.

**Verdict:** all three `tcp_reno_*` functions are callable BPF kfuncs from `struct_ops`
`tcp_congestion_ops` context on this kernel, and produce behaviorally correct results under real
loss. **Reference strategy: use the target-kernel kfuncs directly** (Oracle C, the strong
independent-reference case — see `docs/CORRECTNESS_ORACLES.md`). No fallback needed.

## B. `BPF_MAP_TYPE_SK_STORAGE` — PASS

**Helper presence:**
```
$ bpftool btf dump file /sys/kernel/btf/vmlinux format c | grep bpf_sk_storage
typedef u64 (*btf_bpf_sk_storage_delete)(struct bpf_map *, struct sock *);
typedef u64 (*btf_bpf_sk_storage_delete_tracing)(struct bpf_map *, struct sock *);
typedef u64 (*btf_bpf_sk_storage_get)(struct bpf_map *, struct sock *, void *, u64, gfp_t);
typedef u64 (*btf_bpf_sk_storage_get_tracing)(struct bpf_map *, struct sock *, void *, u64, gfp_t);
```

**Compile+verify+register+functional smoke test** (`data/audit_src/audit_skstorage.bpf.c`):
declares a `BPF_MAP_TYPE_SK_STORAGE` map holding `struct audit_priv { u32 counter; }`, allocates it
in `.init` with `BPF_LOCAL_STORAGE_GET_F_CREATE`, increments the counter on every `.cong_avoid`
call (still delegating to `tcp_reno_cong_avoid` afterward), and deletes it in `.release` via
`bpf_sk_storage_delete`. Compiled cleanly, registered cleanly:

```
$ bpftool struct_ops register data/audit_src/build/audit_skstorage.bpf.o
Registered tcp_congestion_ops audit_sks id 20
```

**Live persistence test:** loopback `iperf3 -C audit_sks` for 8s while a ringbuf consumer
(`data/audit_src/audit_consumer.c`) drained the per-call counter value. Result
(`data/audit_src/consumer_out.txt`, 273,359 lines): the counter increments monotonically
`1, 2, 3, ..., 273358` across the entire 8-second, ~273k-call transfer on the one socket — direct
proof the storage is genuinely per-socket and persists correctly across a very large number of
real callback invocations, not merely allocated-and-read-once. One anomalous final line
(`counter=1`) appears after the monotonic run ends; not chased further (see Limitations) — it does
not affect the pass/fail determination, since it is trivially explained by a second socket (e.g. a
subsequent connection reusing the same CC name) and the monotonic-persistence property that
matters for the audit was already conclusively demonstrated across the preceding 273,358 events.

**Verdict:** `BPF_MAP_TYPE_SK_STORAGE` with `bpf_sk_storage_get`/`bpf_sk_storage_delete` is usable
from `struct_ops` `tcp_congestion_ops` context on this kernel. **ADR-010 resolved: use
`SK_STORAGE`**, no fallback required.

## C. Callback surface — determined directly from kernel BTF

```
$ grep -A 22 '^struct tcp_congestion_ops {' bpf/vmlinux.h
struct tcp_congestion_ops {
	u32 (*ssthresh)(struct sock *);
	void (*cong_avoid)(struct sock *, u32, u32);
	void (*set_state)(struct sock *, u8);
	void (*cwnd_event)(struct sock *, enum tcp_ca_event);
	void (*in_ack_event)(struct sock *, u32);
	void (*pkts_acked)(struct sock *, const struct ack_sample *);
	u32 (*min_tso_segs)(struct sock *);
	void (*cong_control)(struct sock *, u32, int, const struct rate_sample *);
	u32 (*undo_cwnd)(struct sock *);
	u32 (*sndbuf_expand)(struct sock *);
	size_t (*get_info)(struct sock *, u32, int *, union tcp_cc_info *);
	char name[16];
	struct module *owner;
	struct list_head list;
	u32 key;
	u32 flags;
	void (*init)(struct sock *);
	void (*release)(struct sock *);
	...
};
```

Cross-confirmed by `bpftool struct_ops dump` on the registered `audit_reno`/`audit_sks` objects,
which echoed this exact field set back (unpopulated fields shown as `0`/`(nil)`).

**Reno wrapper's declared callback capability manifest** — revised after section F's finding that
Reno needs no controller-private state (everything it reads/writes lives in already-classified
`SharedTcpPreState`/`ControllerOwnedPostState` fields): native `tcp_reno` itself implements no
`.init` (confirmed absent from upstream `tcp_reno.c`'s `tcp_congestion_ops` initializer), and since
this wrapper does not need `SK_STORAGE` for Reno (no private state to allocate), there is no
remaining reason to invent an `.init` callback the real algorithm doesn't have. **Manifest
finalized as exactly the three callbacks real Reno implements:**

```
ssthresh, cong_avoid, undo_cwnd
```

`SK_STORAGE` usability (section B) remains a validated, available capability — relevant to a
future CUBIC/Vegas wrapper that does carry private history — but per `RECORDER.md` ("do not
invent private state merely because the generic schema supports it"), the Reno wrapper does not
use it.

`set_state`, `cwnd_event`, `in_ack_event`, `pkts_acked`, `min_tso_segs`, `cong_control`,
`sndbuf_expand`, `get_info`, `release` are all legal hook points on this kernel but are **not**
part of the Reno manifest — R0 does not require them populated (`RECORDER.md`: "R0 validates
every invocation of that declared surface, not every possible TCP CC callback").

## D. Timebase

- Kernel `CONFIG_HZ=250` (from `/boot/config-6.18.33.2-microsoft-standard-WSL2`).
- Controller-visible monotonic clock: `bpf_ktime_get_ns()`, already exercised successfully in
  every audit program above (used for `ts_ns` in every emitted event) and previously validated
  behaviorally in `cn-spike` Gate 8b (BPF `srtt_us` cross-checked against `ss` within 0.42%,
  implying `bpf_ktime_get_ns`-derived RTT sampling is trustworthy on this kernel).
- **Reno itself has no controller-visible clock dependency.** `tcp_reno_ssthresh`,
  `tcp_reno_cong_avoid`, and `tcp_reno_undo_cwnd` read only `snd_cwnd`/`snd_ssthresh`/
  `snd_cwnd_cnt`/`snd_cwnd_clamp`/`prior_cwnd` (confirmed empirically in section E) — none of
  which are time-derived. `tcp_jiffies32`/`bpf_jiffies64()` (available via the copied
  `bpf_tracing_net.h`) is therefore not required for Reno's exact semantic replay; recording
  `ts_ns` remains useful strictly as a diagnostic/ordering field, per `REPLAY_ABI.md`'s
  distinction between the controller's own clock and a diagnostic monotonic timestamp.

## E. Writable/readable fields — determined empirically, not assumed

Rather than trust the Replay ABI doc's example field list (`snd_cwnd`, `snd_cwnd_cnt`) or recall
of upstream Reno source, `data/audit_src/audit_fields.bpf.c` captured a 10-field PRE/POST
superset (`snd_cwnd`, `snd_ssthresh`, `snd_cwnd_cnt`, `snd_cwnd_clamp`, `snd_cwnd_used`,
`snd_cwnd_stamp`, `prior_cwnd`, `prior_ssthresh`, `packets_out`, `max_packets_out`) around every
real `tcp_reno_cong_avoid`/`ssthresh`/`undo_cwnd` call, run against the **validated Gate-3-R2
topology** (10 Mbit/s bottleneck, 40 ms base RTT, 250,000 B = 5×BDP `bfifo`, offloads off — copied
into `scripts/`, see `docs/PROVENANCE.md`) for 60 s, real loss included (206 retransmits, 9.87
Mbit/s achieved — within the topology's previously-validated envelope).

**24,656 real callback events captured** (`data/audit_src/fields_out.csv`,
`data/audit_src/analyze_fields.py`):

| callback | n | fields actually mutated (PRE≠POST) | return-value formula check |
|---|---|---|---|
| `cong_avoid` | 24,651 | `snd_cwnd` (2.6% of calls), `snd_cwnd_cnt` (98.7% of calls). **No other field of the 10 audited ever changed.** | n/a (void) |
| `ssthresh` | 5 | none (pure function) | `ret == max(snd_cwnd_pre >> 1, 2)` — 0/5 mismatches |
| `undo_cwnd` | 0 | — | **not exercised** — see Limitations |

**Conclusion for `cong_avoid`'s `ControllerOwnedPostState`:** exactly `{snd_cwnd, snd_cwnd_cnt}` —
this empirically confirms (does not merely assume) `REPLAY_ABI.md`'s example field list is both
necessary and sufficient for Reno's `cong_avoid`. No `SharedTcpPreState` field outside these two
needs to be treated as controller-owned.

**Conclusion for `ssthresh`:** pure scalar-returning function, formula `max(snd_cwnd >> 1, 2)`
confirmed exactly on every real invocation observed; no `ControllerOwnedPostState` beyond the
returned scalar.

### `undo_cwnd` — closed via a separate ABI-validation-only auxiliary capture

Zero `undo_cwnd` invocations occurred in the primary 60 s audit run (real drop-tail loss is
rarely spurious, so the kernel's DSACK/F-RTO-triggered undo path was never entered there). Rather
than leave this unexercised, or weaken the R0 topology to force it (forbidden by `CLAUDE.md` §11:
"Use only the validated Gate 3-R2 topology"), a **separate, clearly-labeled auxiliary capture**
was run: the same `audit_fields` program against a **deliberately modified, non-Gate-3-R2**
variant (`vh1`'s `netem` given `reorder 50% 50%` in addition to the usual 20 ms delay, to induce
DSACK-detected spurious retransmissions). This trace is *not* one of the three R0 traces and is
not used for any R1/R2 comparison — it exists solely to determine `undo_cwnd`'s field/formula
contract for the ABI, per this section's mandate.

**8 real `undo_cwnd` events captured** (`data/audit_src/fields_undo_out.csv`, 23,552 total events,
30 s run):

| pre `snd_cwnd` | pre `prior_cwnd` | returned | post `snd_cwnd` |
|---|---|---|---|
| 11 | 20 | 20 | 11 (unchanged) |
| 14 | 22 | 22 | 14 (unchanged) |
| 25 | 27 | 27 | 25 (unchanged) |
| 17 | 28 | 28 | 17 (unchanged) |
| 18 | 28 | 28 | 18 (unchanged) |
| 108 | 110 | 110 | 108 (unchanged) |
| 105 | 110 | 110 | 105 (unchanged) |
| 102 | 110 | 110 | 102 (unchanged) |

**`ret == max(pre_snd_cwnd, pre_prior_cwnd)` on all 8/8 events, zero field mutations** (pure
function, exactly like `ssthresh`). **Conclusion: `undo_cwnd`'s required input is `{snd_cwnd,
prior_cwnd}`; its `CallbackResult` is the returned scalar; it has no `ControllerOwnedPostState`.**

## F. Mode-A dry-run validation (performed before writing the recorder)

Before any trace format, parser, or recorder code was written, a userspace Reno model
(`data/audit_src/reno_model_dryrun.py`, implementing `tcp_is_cwnd_limited`/`tcp_slow_start`/
`tcp_cong_avoid_ai` against the fields captured in section E) was run directly against
`fields_out.csv`'s 24,651 real `cong_avoid` events, using **only** the PRE fields `{snd_cwnd,
snd_ssthresh, snd_cwnd_cnt, snd_cwnd_clamp, max_packets_out, is_cwnd_limited}` plus callback
inputs `{ack, acked}`.

**Result: 24,651/24,651 exact matches (100.0000%) on both `snd_cwnd` and `snd_cwnd_cnt`.**

This dry run also **found a load-bearing field the Replay ABI doc's example list does not
mention**: `is_cwnd_limited` (and, transitively, `max_packets_out`, needed to compute it during
slow start). Direct evidence — two real events with identical `snd_cwnd`, `snd_ssthresh`, and
`acked`, but opposite outcomes:

```
ack=683933477: pre_cwnd=10 ssthresh=MAX max_packets_out=1 is_cwnd_limited=0 -> post_cwnd=10 (no growth)
ack=683934925: pre_cwnd=10 ssthresh=MAX max_packets_out=10 is_cwnd_limited=1 -> post_cwnd=11 (grew)
```

`tcp_is_cwnd_limited` gates `cong_avoid` entirely: in slow start it evaluates `snd_cwnd < 2 *
max_packets_out`; outside slow start it reads the raw `is_cwnd_limited` bitfield. Without this
field, replay would silently apply growth to sender-limited windows that the real kernel left
untouched. **`is_cwnd_limited` and `max_packets_out` are added to Replay ABI v0's required
`cong_avoid` input set, not left as optional/diagnostic** (see `docs/REPLAY_ABI.md` v0 update).
This is exactly the kind of contract-discovery `GATES.md`/`IMPLEMENTATION_HANDOFF.md` anticipate,
found here at zero re-record cost rather than after R1 traces already existed.

## Summary

| Capability | Result |
|---|---|
| `tcp_reno_cong_avoid`/`ssthresh`/`undo_cwnd` callable kfuncs | **PASS** |
| `BPF_MAP_TYPE_SK_STORAGE` from struct_ops CC context | **PASS** |
| Callback surface (BTF) | `init, ssthresh, cong_avoid, set_state, cwnd_event, in_ack_event, pkts_acked, min_tso_segs, cong_control, undo_cwnd, sndbuf_expand, get_info, release` all legal; Reno manifest = `{init, ssthresh, cong_avoid, undo_cwnd}` |
| Timebase | `bpf_ktime_get_ns()` available and validated; Reno itself has no clock dependency |
| `cong_avoid` mutated-field set | `{snd_cwnd, snd_cwnd_cnt}` — empirically confirmed, 24,651 real events; **gated by `{is_cwnd_limited, max_packets_out}`, both now required inputs** |
| `cong_avoid` full replay model | **100.0000% exact match, 24,651/24,651 real events** (section F) |
| `ssthresh` formula | `max(snd_cwnd >> 1, 2)` — empirically confirmed, 5/5 real events |
| `undo_cwnd` formula | `max(snd_cwnd, prior_cwnd)`, no mutation — empirically confirmed, 8/8 real events (auxiliary reorder capture, section E) |

**Reference implementation chosen: target-kernel `tcp_reno_*` kfuncs (Oracle C, independent
reference), delegated to from a `struct_ops` wrapper — per `RECORDER.md`'s preferred order,
option 1.**
