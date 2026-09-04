# Inspection Summary

Performed before any CCReplay implementation code was written, per `CLAUDE.md` §3.

## Environment note

The task brief pointed to `~/CCReplay_Final_Documentation.zip`. On this machine that file did
not exist at `~` (`/root`); the archive was found already extracted (not by this session — file
timestamps are Sep 4 17:38, prior to this session) at
`/mnt/c/Users/Garvit/Downloads/CCReplay_Final_Documentation/ccreplay_docs_final/`. It was copied
from there into `~/ccreplay/`. No zip file itself was ever located; only the pre-extracted
directory. This is recorded here rather than silently treated as "found the zip as instructed."

A second anomaly: `~/cn` (one of the three nominally read-only source repos) contains *only*
`CLAUDE.md`, `README.md`, `docs/` — apparently the same frozen documentation set, not a git
repository, and not the "Gate 0 methodology / environment notes / run logging discipline"
material the task brief describes for `~/cn`. It was not modified by this session (verified
read-only; see `docs/PROVENANCE.md` and the baseline checksum in
`data/readonly_repo_baseline.txt`). Nothing reusable was found there. This is flagged, not
resolved — resolving it would mean writing to a nominally read-only path, which this session will
not do.

## `~/cn-spike` (read-only, git repo, HEAD at inspection time: `022c2e214d4b05012ce379e8b3a14787ee6dff43`)

Pre-existing uncommitted local state at inspection time (not caused by this session): modified
`CLAUDE.md`, and untracked `REPORT_GATE9.md` / `covegas/` / `data/gate9/` / `plots/gate9/` /
`raw/gate9/` / `scripts/gate9_*`. Recorded as baseline in `data/readonly_repo_baseline.txt`.

### Reusable infrastructure found

1. **Validated Reno kfunc delegation pattern** — `bpf_src/spike_min.bpf.c`, `spike_probe.bpf.c`,
   `spike_ctrl.bpf.c` all declare and call:
   ```c
   extern void tcp_reno_cong_avoid(struct sock *sk, __u32 ack, __u32 acked) __ksym;
   extern __u32 tcp_reno_ssthresh(struct sock *sk) __ksym;
   extern __u32 tcp_reno_undo_cwnd(struct sock *sk) __ksym;
   ```
   `REPORT_GATES5R8.md` Gate 8a/8b documents these compiling, verifying, and registering cleanly
   on **this exact kernel** (`6.18.33.2-microsoft-standard-WSL2` — confirmed unchanged by
   `uname -r` this session), and Gate 8b cross-validates `spike_probe`'s live behavior against
   `ss -tinm` ground truth (RTT p50/p95/min within 0.0004–0.42% of `ss`) and against Gate 6's
   native-Reno row (mean RTT/cwnd/throughput within 0.0–2.7%). This is strong prior evidence the
   three Reno kfuncs are legitimately callable from `struct_ops` CC context here, not merely
   present in BTF — but CCReplay's own capability audit (`data/capability_audit.md`) re-verifies
   this directly rather than taking the prior gate's word for it, since the wrapper shape differs
   (recorder + ringbuf emission on every declared callback, not just `pkts_acked`).
   **Decision: copy this delegation pattern into `bpf/reno_wrapper.bpf.c`, adapted with recorder
   instrumentation.** See `docs/PROVENANCE.md`.

2. **`bpf_src/bpf_tracing_net.h`** — standard kernel-selftest-derived CO-RE compatibility header
   (`inet_csk`, `tcp_sk`, `tcp_is_cwnd_limited`, socket field remaps). No CCReplay-specific logic.
   **Decision: copy verbatim into `bpf/bpf_tracing_net.h`.**

3. **Ringbuf + userspace consumer pattern** — `bpf_src/spike_probe.bpf.c` (`BPF_MAP_TYPE_RINGBUF`,
   `bpf_ringbuf_reserve`/`submit`, `BPF_CORE_READ` for `tcp_sock` fields) and
   `scripts/ringbuf_consumer.c` (libbpf `ring_buffer__new`/`__poll`, drains to CSV, one map-fd
   argument obtained via `bpf_map_get_fd_by_id`). **Decision: adapt the BPF-side ringbuf idiom
   for `EventRecord` emission; do not copy `ringbuf_consumer.c` verbatim** — it polls by
   externally-supplied map ID against an already-`bpftool`-registered object and has no drop-map
   readback, no sequence validation, and no versioned trace writer, none of which R0 can do
   without. CCReplay's consumer is a new libbpf skeleton-based loader (see `docs/RECORDER.md`
   drop-counter requirement) that owns load/attach/teardown and reads the drop map directly.

4. **Compile/register commands** — `scripts/gate4a_compile.sh` / `gate4a_register.sh`:
   ```
   clang -target bpf -D__TARGET_ARCH_x86 -g -O2 -I <repo> -I /usr/include/x86_64-linux-gnu \
       -c foo.bpf.c -o foo.bpf.o
   bpftool struct_ops register foo.bpf.o
   ```
   **Decision: reuse this compile invocation as the base for `scripts/build_bpf.sh`.** Load
   itself moves to a libbpf skeleton loader for R0 (need programmatic map-fd access and clean
   teardown/re-register across repeated 90s runs; raw `bpftool struct_ops register` from a shell
   script is fine for a one-shot smoke test but not for a batch of 3 runs needing reliable
   teardown between them).

5. **Validated Gate 3-R2 topology** — `scripts/gate3r2_setup_topology.sh` (3-netns
   `ns_h1`–`ns_r`–`ns_h2`, veth pairs, no nested qdiscs), `gate3r2_set_qdiscs.sh` (`netem delay
   20ms` on each host leg = 40ms base RTT, `htb rate 10mbit` + `bfifo limit <B_BYTES>` bottleneck
   on the router's egress to h2), `gate3r2_set_offloads.sh` (disables gso/tso/gro/tx-gso-list/
   sg/tx on all 4 veths), `gate3r2_verify_bfifo_limit.py` (readback verification),
   `gate3r2_teardown.sh`. `REPORT_GATE3R2.md`: VERDICT PASS, this exact topology/params
   previously validated (correct 3-hop path, bfifo limit readback matches requested B exactly at
   all tested sizes, offloads confirmed off, real loss/sawtooth/backlog behavior recorded).
   **Decision: copy these scripts into `scripts/`, parameterized for the task's target operating
   point (10 Mbit/s, 40 ms base RTT, `B = 250000` bytes = 5×BDP), not re-derive the topology.**
   `iperf3 -C <cc-name>` sets the per-connection congestion control via `TCP_CONGESTION`
   sockopt — this is how the recorder's wrapper CC gets attached to the test transfer
   (`scripts/gate3r2_run_one.sh` line: `iperf3 -c ... -C cubic ...`).

6. **`vmlinux.h`** (3.6 MB, this exact kernel's BTF dump) — contains
   `struct tcp_congestion_ops { ssthresh, cong_avoid, set_state, cwnd_event, in_ack_event,
   pkts_acked, min_tso_segs, cong_control, undo_cwnd, sndbuf_expand, get_info, name, ..., init,
   release }` (full field list confirmed by direct `grep -A40` this session — this is the
   ground-truth callback surface for §5C of the capability audit, not inferred from upstream
   Linux). **Decision: copy `vmlinux.h` into `ccreplay/bpf/` rather than regenerate — it is a
   kernel-BTF dump, not project logic, and regenerating would just reproduce the same bytes on
   the same kernel.**

### What will NOT be reused

- `covegas.bpf.c`'s private-state layout (own `icsk_ca_priv`-resident struct) — CUBIC/Vegas-class
  design, out of scope for R0–R2 (Reno only). Read only as prior art for "controller-private-state
  usage," per task §3; not copied.
- `bpf_src/bpf_cubic.c`, `bpf_src/bpf_cubic.bpf.o` — out of scope until R3.
- Gate 5–9 differential/regression-oracle scripts (`gate9_regression_check.py` etc.) — adjacent in
  spirit to CCReplay's eventual differential debugger, but built for network-performance
  regression detection (throughput/RTT/retrans deltas across runs), not callback-boundary replay.
  Not reused; CCReplay's differential debugger (out of scope for this task) will be a new design
  per `docs/DIFFERENTIAL_DEBUGGER.md`.

## `~/covegas`

Does not exist at this path. The actual location is `~/cn-spike/covegas/` (a nested git repo with
its own `.git`, built up by `~/build_covegas_repo.sh`). Inspected there instead; see notes under
`~/cn-spike` item "What will NOT be reused" above — covegas's structure (struct_ops org, ringbuf
telemetry, `icsk_ca_priv`-based private state) was read for pattern familiarity but nothing was
copied, since CCReplay's own Reno wrapper is simpler and the validated `spike_*` files already
cover the same patterns without CUBIC-specific complexity.

## `~/cn`

See "Environment note" above. Contains no Gate 0 methodology, environment notes, or run-logging
material distinct from the frozen docs already obtained from the Downloads archive. Nothing
reused from here.

## Assumptions requiring verification (deferred to `data/capability_audit.md`)

- `BPF_MAP_TYPE_SK_STORAGE` usability from `struct_ops` CC context: **not** validated anywhere in
  `~/cn-spike` or `~/covegas` (`grep` for `sk_storage`/`SK_STORAGE` across both trees found no
  usage, only the symbol's presence in `vmlinux.h` and in the unrelated upstream
  `bpf_tcp_ca.c`/`bpf_tracing_net.h` reference copies). This session tests it directly rather than
  assuming success by analogy to the Reno-kfunc precedent.
- Whether one-record-per-callback (PRE+inputs+result+POST in a single `bpf_ringbuf_reserve`) is
  verifier-feasible for the full Reno manifest (`init`, `ssthresh`, `cong_avoid`, `undo_cwnd`) —
  prior gates only ever emitted one narrow fixed-shape struct per `pkts_acked` call, not a
  per-callback-type variant record. Verified in the capability audit / R0 build, not assumed.
- Exact Reno `cong_avoid` POST-state sufficiency (`snd_cwnd`, `snd_cwnd_cnt` vs. other mutated
  fields) — no prior gate inspected `tcp_reno_cong_avoid`'s actual field writes; determined from
  kernel source/BTF directly during ABI design, not assumed from the doc's example list.
