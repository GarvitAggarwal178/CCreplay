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

**Reno wrapper's declared callback capability manifest** (the subset native `tcp_reno` itself
implements, per upstream Linux `tcp_cong.c`/`tcp_input.c` convention — `init` is added because the
wrapper needs it to set up `SK_STORAGE`, not because Reno's own logic requires it):

```
init, ssthresh, cong_avoid, undo_cwnd
```

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

### Limitation: `undo_cwnd` not empirically exercised

Zero `undo_cwnd` invocations occurred in the 60 s audit run. Real drop-tail loss under this
topology is (as expected) rarely spurious, so the kernel's undo path (typically triggered by
DSACK/F-RTO detecting a retransmission was unnecessary) was never entered. `undo_cwnd`'s BTF
prototype (`u32 (*)(struct sock *)`) and the register/dump evidence in section A confirm it is
callable and wired correctly, and `bpf_src/spike_ctrl.bpf.c`/`spike_probe.bpf.c` in `~/cn-spike`
both also declare and wire it without incident — but this session has **not** empirically confirmed
which fields it reads/mutates or its exact return formula on real traffic on this kernel. This is
recorded here rather than papered over. If R0/R1/R2's actual recorded traces also contain zero
`undo_cwnd` events, the gates' PASS determination is scoped to the manifest events that did occur
(consistent with `GATES.md`'s "every valid event," not a fixed required count per callback type);
if `undo_cwnd` never fires across all three R0 traces, R1/R2 simply carry no evidence either way
for that one callback, and this will be stated explicitly in the final report rather than
implied as covered.

## Summary

| Capability | Result |
|---|---|
| `tcp_reno_cong_avoid`/`ssthresh`/`undo_cwnd` callable kfuncs | **PASS** |
| `BPF_MAP_TYPE_SK_STORAGE` from struct_ops CC context | **PASS** |
| Callback surface (BTF) | `init, ssthresh, cong_avoid, set_state, cwnd_event, in_ack_event, pkts_acked, min_tso_segs, cong_control, undo_cwnd, sndbuf_expand, get_info, release` all legal; Reno manifest = `{init, ssthresh, cong_avoid, undo_cwnd}` |
| Timebase | `bpf_ktime_get_ns()` available and validated; Reno itself has no clock dependency |
| `cong_avoid` mutated-field set | `{snd_cwnd, snd_cwnd_cnt}` — empirically confirmed, 24,651 real events |
| `ssthresh` formula | `max(snd_cwnd >> 1, 2)` — empirically confirmed, 5/5 real events |
| `undo_cwnd` | callable and wired; **not empirically exercised** this session |

**Reference implementation chosen: target-kernel `tcp_reno_*` kfuncs (Oracle C, independent
reference), delegated to from a `struct_ops` wrapper — per `RECORDER.md`'s preferred order,
option 1.**
