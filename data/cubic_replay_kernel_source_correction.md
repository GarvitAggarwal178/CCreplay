# Correction: real kernel `tcp_cubic.c` obtained — supersedes `bpf_cubic.c` as the N2/N3 reference

This is a correction to `data/cubic_replay_capability_audit.md`, `data/cubic_replay_contract_predictions.md`,
and `data/cubic_replay_callback_manifest.md`, written the same session, before those files' commit
had aged and before any recorder was built or empirical trace captured. Per `INSTRUCTIONS.md`
("never rewrite evidence history" / preserve first-pass reasoning), the three files above are left
as originally committed and are not edited in place beyond a short pointer to this file; this
document is the correction of record. Nothing here comes from a recorded trace — it comes from
obtaining a strictly better source than was available when those files were written.

## What changed

N1.1 chose to prefer real kernel kfunc delegation (Oracle C) for **recording**, which remains
correct and unaffected by this correction — `cubictcp_acked` was additionally load-tested after the
original N1.1 pass (advisor-flagged gap: the original probe tested 6 of 7 kfuncs, omitting the
pointer-argument `pkts_acked` callback) and is also verifier-load-confirmed callable (real program
ID 276 assigned, `bpftool prog loadall`, `LOAD_EXIT=0`).

But N1.1/N1.3/N1.5's *field-level and callback-level claims* (which fields each callback reads,
which clocks it consults, structural relationships between callbacks) were built from
`~/cn-spike/bpf_src/bpf_cubic.c`, a **BPF port** whose own header explicitly warns it is "not
necessarily the same as tcp_cubic.c." That warning is no longer a hedge to note and move past — it
is now confirmed to matter. This session located and fetched the actual kernel source for the
**exact running kernel**:

* Source: `https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.18.33.2/net/ipv4/tcp_cubic.c`
* Tag `linux-msft-wsl-6.18.33.2` confirmed to match `uname -r` = `6.18.33.2-microsoft-standard-WSL2`
  exactly (via the repo's GitHub Releases API, not guessed)
* Fetched: 2026-09-04 23:07 UTC
* Saved to `data/kernel_source_ref/tcp_cubic.c`, sha256
  `730015587ab59bc17fa725c5167c8cf4a828d04e630fae7267e7df2c4ee84191`
* Cross-check: `BUILD_BUG_ON(sizeof(struct bictcp) > ICSK_CA_PRIV_SIZE)` (line 508) and the field
  list (lines 86–105) match N1.3's BTF/`offsetof` ground truth exactly (17 fields, 60 bytes) —
  confirms this is the right file, not a mismatched variant.
* Direct confirmation this file's kfunc registration matches N1.1's empirical result exactly: lines
  490–497 register precisely `cubictcp_init`, `cubictcp_recalc_ssthresh`, `cubictcp_cong_avoid`,
  `cubictcp_state`, `cubictcp_cwnd_event`, `cubictcp_acked` via
  `register_btf_kfunc_id_set(BPF_PROG_TYPE_STRUCT_OPS, ...)` — the same six, plus shared
  `tcp_reno_undo_cwnd` used directly (line 483, not wrapped) for `undo_cwnd`. This is the strongest
  possible confirmation of N1.1's verifier-load findings — it's not just that the load succeeded,
  it's that the kernel source shows it was *designed* to be called this way.

**This file (`data/kernel_source_ref/tcp_cubic.c`) is now the sole authoritative reference for the
N2/N3 userspace replay model.** `bpf_cubic.c` is downgraded to a secondary/illustrative
cross-reference only — it remains useful for spotting *possible* areas of algorithmic subtlety, but
where the two disagree, the real kernel source governs, and any such disagreement is documented
below rather than silently resolved in the model's favor.

## Verified differences between `bpf_cubic.c` and the real kernel source

1. **`bictcp_update`'s time-unit rounding order (real lines 267–271 vs. port lines 325–329) — the
   single most load-bearing difference.** Real kernel computes the jiffies delta first, converts
   `delay_min` from usec to jiffies via `usecs_to_jiffies()` (losing sub-jiffy precision at
   `HZ=250`, i.e. 4ms granularity) and adds it *before* shifting to `bictcp_HZ` units and dividing
   by `HZ`. The port instead converts the jiffies delta to usec first, adds `delay_min` directly (no
   precision loss at that step), and divides by `USEC_PER_SEC` at the very end. Both are intended to
   compute the same physical quantity, but integer truncation happens at different points and can
   produce different results for `delay_min` values that aren't exact multiples of 4000 usec. This
   is exactly the kind of thing pipeline's INTEGER-SEMANTICS TEST step exists to catch, and is now
   the single highest-priority case for that test in N2/N3 — not a hypothetical, a *found*
   discrepancy between the two sources.
2. **`hystart_update`'s round-reset trigger relocated (real lines 392–393 vs. port line 395 inside
   `cong_avoid`).** In `bpf_cubic.c`, the HyStart round is reset from `cong_avoid`:
   `if (hystart && after(ack, ca->end_seq)) bictcp_hystart_reset(sk);`, keyed on `cong_avoid`'s
   `ack` argument. In the real kernel, this check does not exist in `cong_avoid` at all — `cong_avoid`
   (real lines 324–339) never references its `ack` parameter. Instead, the check moved to the *top*
   of `hystart_update()` (called from `pkts_acked`, real line 392): `if (after(tp->snd_una,
   ca->end_seq)) bictcp_hystart_reset(sk);`, keyed on `tp->snd_una`. This directly reverses this
   session's Prediction #1.
3. **`hystart_low_window` gating relocated.** The port gates the entire `hystart_update()` call from
   `pkts_acked` on `tp->snd_cwnd >= hystart_low_window` (i.e. skips the round-reset too, below that
   window). The real kernel calls `hystart_update()` unconditionally (subject only to
   `!found && slow_start && hystart`) and moves the `hystart_low_window` check *inside*
   `hystart_update`, *after* the round-reset (real lines 396–397) — meaning the real kernel resets
   the HyStart round even below `hystart_low_window`, where the port would not.
4. **`hystart_ack_delay` reads a real per-socket field, not a compile-time constant.** Real line 379:
   `rate = READ_ONCE(sk->sk_pacing_rate)`; real line 383 uses `sk->sk_gso_max_size` (an actual,
   possibly-non-default per-socket field). The port hardcodes `#define GSO_MAX_SIZE 65536` instead
   of reading the field. **`sk_gso_max_size` is therefore a newly-required shared-state field**, not
   previously identified — the port's hardcoding masked this dependency entirely.
5. **`bictcp_update`'s TCP-friendliness blend**: real kernel uses a `while (ca->ack_cnt > delta) {
   ca->ack_cnt -= delta; ca->tcp_cwnd++; }` loop (real lines 305–308); the port replaces it with a
   closed-form `n = ca->ack_cnt / delta; ...` (port's own header comment #3 states this substitution
   is deliberate and claims equivalence). Believed equivalent for well-formed positive `delta`, but
   not independently re-verified here — flagged as a secondary integer-semantics check, lower
   priority than item 1.
6. **`cubic_root`'s verifier-satisfying bounds check** (port's `if (shift >= 64) return 0;`, absent
   from the real kernel) is BPF-verifier-only scaffolding, not an algorithmic difference — within
   the function's valid domain this branch is never taken by either version. No action needed.

## Corrections to precommitted predictions and the manifest

* **Prediction #1 (`snd_una`) revised from NOT REQUIRED to REQUIRED.** The original prediction was
  reasoned honestly from the only source available at the time (`bpf_cubic.c`, which never
  references `snd_una`) and explicitly flagged the risk that "the real kernel `tcp_cubic.c` could
  reference `snd_una` in a way the BPF port elides" — that flagged risk is now confirmed to have
  materialized. Against real kernel ground truth, the original NOT REQUIRED prediction classifies as
  **WRONG**; the corrected, real-source-grounded prediction is **REQUIRED** (`pkts_acked`'s
  `hystart_update`, line 392, per item 2 above).
* **`data/cubic_replay_callback_manifest.md`'s `cong_avoid` row is corrected**: `ack` is not read by
  the real kernel's `cong_avoid` at all (contradicts the manifest's "observation inputs: `ack`
  (input)" note, which was port-derived); the HyStart round-reset logic attributed to `cong_avoid`
  in that row belongs instead to `pkts_acked`.
* **`data/cubic_replay_callback_manifest.md`'s `pkts_acked` row is corrected**: add `tp->snd_una`
  (read, hystart round-reset trigger) and `sk->sk_gso_max_size` (read, via `hystart_ack_delay`) to
  its shared-field-read list; the `hystart_low_window` gate moves from being a precondition for
  calling `hystart_update` at all (port's structure) to an internal early-return inside it (real
  kernel's structure, after the round-reset already ran) — Mode A/B replay of `pkts_acked` must
  reproduce this exact ordering, not the port's ordering, or a divergence will appear that is
  actually a modeling error (category B in `data/cubic_replay_model_changes.md`'s taxonomy), not a
  genuine algorithmic mismatch.

## What is unaffected

N1.2 (private-state architecture: `icsk_ca_priv`, no `SK_STORAGE`), N1.3's private-state layout
table (field names/offsets/sizes, cross-checked directly against the real struct definition, lines
86–105 — identical), the two-clock finding (`tcp_jiffies32`, `tp->tcp_mstamp` — both still directly
confirmed present in the real source), and the `pkts_acked`→`snd_ssthresh` direct-mutation finding
(real lines 426, 446 — confirmed, via `WRITE_ONCE` rather than the port's plain assignment, same
semantic effect) all stand unchanged and are, if anything, more strongly confirmed by having the
real source in hand.

## Provenance record addition

This addition to `docs/PROVENANCE.md`'s convention (external, not `~/cn-spike`/`~/covegas`/`~/cn`
read-only-repo provenance, so tracked here rather than muddying that table's existing schema): the
file was fetched read-only from a public GitHub tag, used only as a documentation/model-design
reference, never executed, never linked into the build. No modification to CCReplay's build process
or dependencies results from adding it.
