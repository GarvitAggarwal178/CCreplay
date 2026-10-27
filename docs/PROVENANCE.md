# Source provenance and evidence access

[Project home](../README.md)

## Documentation basis

This documentation refresh is grounded in the supplied CCreplay(3).zip, SHA-256:

    2bb6448b0ebd242e45bbb25f8d79947a5d68e5ad6cdf79d1f754e548b5148377

Its bundled Git HEAD was `ae7dc74`. The source was audited on 20 October 2026. The text was then reconciled with the owner's newer checkout (branch `presentation/ccreplay-studio`, based on HEAD `056acb5`) and its test runs; see [Validation](VALIDATION.md). Browser and live-host checks subsequently passed on the identified WSL host; the follow-up checks are listed in Validation.

Historical report measurements are labeled historical evidence. Their original bytes, methodology, predictions and unsuccessful attempts remain recoverable after documentation consolidation. A new summary or a source-code comment supplies no new experiment evidence.

## Reference code

| Material | Source identity from the original evidence | Role |
|---|---|---|
| Reno delegation pattern and network setup | Local reference repository cn-spike, commit `022c2e214d4b05012ce379e8b3a14787ee6dff43` | Reused delegation/setup patterns; recording schema/instrumentation is CCReplay work |
| CUBIC kernel reference | Microsoft WSL2-Linux-Kernel, tag `linux-msft-wsl-6.18.33.2`, commit `c21a03b2943d147c280bdf32530d4fe6badfd6bd` | Model/source reference: `net/ipv4/tcp_cubic.c` |
| CoVegas selected BPF source | Local cn-spike/covegas repository HEAD `bab7ab7`; source last touched at `b5bc0be` (v4) | Instrumented selected implementation; no independent kernel-native reference |
| Reconstructed CoVegas v3 candidate | v4 logic with the documented A3 guard reverted | Historical reconstruction, not original committed v3 source |

The historical provenance records this SHA-256 for the LF-form source:

    730015587ab59bc17fa725c5167c8cf4a828d04e630fae7267e7df2c4ee84191

The uploaded source copy has CRLF line endings and byte hash `77f47d1d81ab17b930f88f92cfe95afc5417410becf61063b7c5e0de8cbb2add`; normalizing CRLF to LF reproduces the historical hash above. Preserve the distinction instead of claiming the current bytes have the historical checksum. This is a text-source line-ending observation, not permission to normalize raw recordings or archived evidence.

Keep `data/kernel_source_ref/tcp_cubic.c` and its `CUBIC_SOURCE_PROVENANCE.md`, which records source resolution and cross-checks in more detail. The original evidence does not claim cryptographic identity of the running kernel from a matching version string alone, or a completed vanilla-upstream source diff.

## Generated recorder material

The original `build/` executables, `user/*.skel.h` and `bpf/vmlinux.h` were kernel-specific generated material removed from the active tree; their original bytes and hashes are in the source snapshot below. New builds belong under `build_local/` (written by `scripts/build_bpf.sh`, with `BUILD_INFO.*` recording the kernel and toolchain). Do not relabel old binaries as rebuilt for a new machine. A build is not an attach or fidelity PASS.

Preserve existing source licenses, copyright notices and attribution, including GPL compatibility declarations in BPF sources. Documentation cleanup does not authorize removing legally required material. No project-wide license has been selected by the owner and none is invented here.

## Historical evidence archives

`docs/EVIDENCE_INDEX.json` records the external archives, per-member SHA-256 values, the mapping from each original path to its current location or disposition, and restore notes. The archives sit outside the repository, in `/root/CCReplay_Evidence_20261020T082754Z/`:

| Archive | Contents | SHA-256 |
|---|---|---|
| `source-snapshot.tar.gz` | 603 classified old-local originals (486,423,464 bytes) snapshotted before cleanup: historical reports, specifications, ADRs, raw campaigns, data and generated builds | `8d021e515bfb675c6f31c76afeadbd340918c6674c91a0ce971571d942eee2e5` |
| `docs-current-before-refresh-20261020T090955Z.tar.gz` | The 19 Markdown/JSON documents present immediately before this refresh: the earlier README and six docs, owner agent notes and `docs/session/` | `bef0e4ec618bf414b5262cd4689ea0e631b51d25713f6c163f020d40fb722cee` |

Both were hash-verified after writing, and the second was read back byte-for-byte against the live files. Relative to the audit package, 649 paths were absent from this checkout and are marked absent in the index rather than claimed as archived. That describes the old local checkout only. A separate 25-file recovery from the complete friend archive now supplies the Kali helpers, completed C6 source/evidence, replay-ablation module and three permanent tests; their original hashes and recovery locations are indexed separately below.

Archived subjects include Reno/CUBIC/CoVegas gate validation, clock-boundary characterization, recorder overhead and non-interference, the CoVegas reconstruction and acquisition history, ABI analysis, mutation campaigns and native network runs. A failed study remains failed in the ledger.

Comments in `user/*.py` still cite earlier documents (`SEMANTICS.md`, `REPLAY_ABI.md`, `GATES.md`, ADR numbers). Those documents are in the source snapshot. The comments were left unchanged on purpose: editing them would alter hashed engine files, which saved revision capsules and the integrity checks rely on.

To restore historical work, extract into a new empty directory with path-traversal checks, verify members against the index and inspect the old environment and commands. Do not extract over the current checkout or overwrite `raw/` or `runtime/`. Restored files are not added to the recording library. The C2/C3 campaigns fail explicitly until their archived datasets are restored.

## Current documentation set

README and the six linked Markdown documents are the maintained project documentation. Local owner and agent notes (`CLAUDE.md`, `instructions.md`, `STUDIO_*.md`, `CCREPLAY_STUDIO_PLAN.md`, `.autorun/`, `docs/session/`) are git-ignored working notes. They are preserved in place and in the second archive, and are not part of the maintained set. In a conflict, inspect current source, tests and the identified original evidence, then correct the documents.

## Complete friend work recovered in the follow-up

The review subset contains 25 original files from `CCreplay(3).zip`, whose reported SHA-256 is `2bb6448b0ebd242e45bbb25f8d79947a5d68e5ad6cdf79d1f754e548b5148377`. The complete ZIP was not located on this host; its hash is a provenance assertion, not a new whole-ZIP verification. Each supplied member was independently hashed, archived and read back against `friend_original/PROVENANCE.json`.

External recovery directory: `/root/CCReplay_Followup_20261020T101411Z`. Portable archive: `friend-recovered-originals.tar.gz`; SHA-256 `63545edbaf4478e9821949190935885d0bfe4c0e219031ff2f86ae3360f06b41`. Its adjacent `friend-recovery-index.json` records original names, sizes and hashes. This archive preserves all 18 completed-C6 files together, including source, SPEC, PREDICTIONS, COMPLETE manifest, 511 mutants, 3,982 stored comparison rows, 25 controls, coverage, analysis and original summary wording. These are historical results, not a newly repeated campaign; original caveats and failed predictions are unchanged. The before-follow-up snapshot preserves conflicting current source, including stage one, separately.

Reusable complete-C6 source is adapted under `experiments/c6_mutation_campaign/complete/`; the parent's earlier stage-one `run.py` is unchanged. Kali helpers moved to `experiments/kali/`; three missing permanent tests and `user/replay_ablation.py` are restored. Only package imports, root resolution and generated-output locations were adapted. Existing model and recorder equations remain unchanged. The 27 restored tests passed on retained inputs; no full mutation or ablation campaign was run.

To restore missing full-C6 inputs, obtain the complete friend ZIP with the hash above and run the following into a **new external directory**. This copies only the five missing recording families; the two rep1 families remain in the canonical checkout. Inspect/verify the resulting manifest before copying any family into `raw/` (never overwrite current files). Restoring files does not automatically add them to the curated recording picker.

```sh
python3 - '/path/CCreplay(3).zip' /external/c6-restored-inputs <<'PYRESTORE'
import hashlib, json, pathlib, sys, zipfile
archive, dest = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
assert hashlib.sha256(archive.read_bytes()).hexdigest() == '2bb6448b0ebd242e45bbb25f8d79947a5d68e5ad6cdf79d1f754e548b5148377'
assert not dest.exists(), 'Use a new external directory'
families = ['raw/r0/rep2', 'raw/r0/rep3',
            'raw/cubic_replay/primary/rep2', 'raw/cubic_replay/primary/rep3',
            'raw/cubic_replay/auxiliary/undo_cwnd/aux1']
manifest = {}
with zipfile.ZipFile(archive) as z:
    for info in z.infolist():
        name = '/' + info.filename.replace('\\', '/').lstrip('/')
        if '/raw/' not in name or info.is_dir(): continue
        rel = 'raw/' + name.split('/raw/', 1)[1]
        if not any(rel.startswith(f + '.') or rel.startswith(f + '_') for f in families): continue
        assert '..' not in pathlib.PurePosixPath(rel).parts and rel not in manifest
        data = z.read(info); target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        manifest[rel] = hashlib.sha256(data).hexdigest()
for f in families: assert f + '.ccr' in manifest, f
(dest / 'RESTORED_SHA256.json').write_text(json.dumps(manifest, indent=2))
PYRESTORE
```

Run a deliberately requested future full campaign only after placing those verified inputs at the exact relative paths in `complete/c6_common.py`; use a fresh `--out` directory under `runtime/experiments/`. Never regenerate into the immutable friend-evidence directory.

## Evidence availability in the 27 October 2026 checkout

The external archive paths recorded above were not present on this host during this pass; their earlier reported verification is historical. Many original tracked evidence paths were already absent from the working tree at session start. No such deletion is included in the review implementation commit: those original bytes remain in Git. The four retained example recordings, owner data and local limitations ZIP were not removed or rewritten.
