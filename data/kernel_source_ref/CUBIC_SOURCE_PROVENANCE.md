# Provenance: `data/kernel_source_ref/tcp_cubic.c`

Written per `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md` Part A6. Supersedes the brief note in
`docs/PROVENANCE.md`'s "External (non-read-only-repo) source reference" section for detail (that
section is retained and now points here).

## Repository

`https://github.com/microsoft/WSL2-Linux-Kernel` — Microsoft's WSL2 kernel fork.

## Tag

`linux-msft-wsl-6.18.33.2`

Selected by matching this machine's exact `uname -r` (`6.18.33.2-microsoft-standard-WSL2`) against
the repository's GitHub Releases API tag list — an exact string match on the version component, not
a nearest-version guess. Confirmed 2026-09-04 (N1, this session's earlier work).

## Commit hash

`c21a03b2943d147c280bdf32530d4fe6badfd6bd`

Resolved via `GET /repos/microsoft/WSL2-Linux-Kernel/git/ref/tags/linux-msft-wsl-6.18.33.2`
(2026-09-05, this correction). The tag is a lightweight ref pointing directly at this commit (`"type":
"commit"`, not an annotated tag object requiring a second dereference).

Commit message (first line): `Merge tag 'rolling-lts/wsl/6.18.33.2' into linux-msft-wsl-6.18.y` —
a merge of Microsoft's WSL-specific rolling-LTS integration branch into the release branch, which is
Microsoft's standard WSL2 kernel release process (not an ad hoc or unofficial build). Commit author
date `2026-06-18T23:44:56Z`.

**Cross-check against the running kernel's own build timestamp:** `uname -a` on this machine reports
a build date of `Thu Jun 18 21:54:43 UTC 2026` — approximately 1h50m *before* the resolved commit's
author timestamp. This is consistent with (build packaged from a commit shortly after this merge, or
clock/timezone rounding in one of the two timestamps) but is not, by itself, cryptographic proof of
identity; it is corroborating evidence, stated as such.

## Source file path (within that repository/commit)

`net/ipv4/tcp_cubic.c`

## Local copy and hash

`data/kernel_source_ref/tcp_cubic.c`, fetched 2026-09-04 (N1) via
`https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.18.33.2/net/ipv4/tcp_cubic.c`,
sha256 `730015587ab59bc17fa725c5167c8cf4a828d04e630fae7267e7df2c4ee84191`.

## Independent cross-checks performed (not merely trusting the fetch)

* `BUILD_BUG_ON(sizeof(struct bictcp) > ICSK_CA_PRIV_SIZE)` (line 508) and the `struct bictcp` field
  list (lines 86–105) match this session's independently BTF/`offsetof`-derived ground truth for
  the *live running kernel* exactly (17 fields, 60 bytes, `data/cubic_replay_capability_audit.md`
  N1.3) — this is the strongest available check, since it compares the fetched *source* against the
  *actually running compiled kernel's* own type layout, not against another copy of the same source.
* The file's own `BTF_KFUNCS_START(tcp_cubic_check_kfunc_ids)` list (lines 490–497) names exactly
  the six kfuncs this session independently verifier-load-confirmed callable on the live kernel
  (`data/cubic_replay_capability_audit.md` N1.1, `data/cubic_replay_kernel_source_correction.md`) —
  a second independent point of agreement between the fetched source and the live kernel's actual
  registered behavior.

## Known Microsoft/WSL patch relationship, and what remains uncertain

Microsoft's WSL2 kernel is a fork of upstream Linux with WSL-specific integration work (Hyper-V
enlightenment, 9p/virtio drivers, WSL-specific defaults) layered on via their own rolling-LTS merge
process (evidenced directly by this commit's own merge message, above). TCP congestion-control code
is not an area WSL-specific integration would ordinarily need to touch, and the two independent
cross-checks above (struct layout, kfunc registration list) both agree with the live running
kernel — but **this session did not perform a line-by-line diff of this file against a vanilla
upstream Linux `net/ipv4/tcp_cubic.c` at a matching base version** to positively rule out a
WSL-specific patch to this exact file. Absence of a known patch is not the same as a confirmed
absence of any patch. Stated as an open, disclosed uncertainty rather than an unstated assumption,
per this task's "do not claim exact source identity beyond what the evidence supports" instruction.

## Usage

Read-only reference material for the `user/cubic_model.py` replay model design (ADR-017). Never
executed, never linked into the CCReplay build. Not one of the `~/cn-spike`/`~/covegas`/`~/cn`
read-only repos (external), held to the same "record source, do not silently alter" standard per
`docs/PROVENANCE.md`.
