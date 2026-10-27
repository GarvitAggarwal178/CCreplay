# Setup and maintenance

[Project home](../README.md)

## Environment and startup

The replay engine is Python; the interface is React/TypeScript built with Node/npm. This checkout was last verified with Python 3.14.4 and Node 22.22.1 (the source audit used Python 3.12.14 and Node 24.19.0) against the existing lockfile. Use the project requirements and lockfile rather than upgrading dependencies during presentation preparation.

From the repository root, as a normal user:

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements-studio.txt
    cd frontend
    npm ci
    npm run build
    cd ..
    bash run_studio.sh

Default URL: http://127.0.0.1:8000; `run_studio.sh` also accepts `--port`, `--daemon` and `--stop`. Studio refuses to start as root (both `run_studio.sh` and the backend startup hook), because user controller code executes with the server account's permissions and the subprocess timeout is not a hostile-code sandbox. Use a normal home checkout or the numeric-uid prepared runtime copy documented in README for this root-only host. Only `scripts/start_lab_agent.sh` is meant to run under `sudo`.

For development, run `.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000` and, in `frontend/`, `npm run dev -- --host 127.0.0.1` (Vite proxies `/api`).

Install the test tools in the same environment if absent, then run the checks:

    .venv/bin/python -m pip install pytest
    .venv/bin/python -m pytest -q
    .venv/bin/python scripts/studio_smoke.py
    (cd frontend && npm run build && npm run lint)

A first-difference CLI can intentionally exit nonzero when it finds a difference. Inspect its JSON, rather than labeling that expected exit an engine crash.

## Runtime-only folder and rebuilding

`frontend/node_modules` is reproducible from `package-lock.json`. FastAPI serves `frontend/dist`, so a prepared demonstration folder can omit `node_modules`; run `npm ci` again before `npm run build`, `npm run dev` or `npm run lint`. Keep `package.json`, the lockfile and the current `dist/`. The single `.venv` is the environment the backend runs under; it also holds Playwright (about 120 MB of that environment is the Playwright driver) for the browser test.

## Browser verification

`scripts/studio_e2e.py` drives the running app through Playwright. Install its dependencies and Chromium, build and start the server, then use the matching URL. Reconcile route and button assertions when the UI changes, and keep behavioral coverage. A successful build is not browser verification. The maintained e2e drives the current UI against actual API/worker execution. Current screenshots/results are in ignored `runtime/acceptance/browser/`; older `studio_data/screens/` images are historical.

## Recording and the Network Lab

Recording requires BTF/struct_ops/kfunc support, a BPF toolchain, namespace/network tooling and privileged setup. Rebuild with:

    bash scripts/build_bpf.sh

It writes kernel-local headers, skeletons and executables under `build_local/`. Build success is not an attach or model-fidelity PASS: verify the data socket's selected wrapper, finalize the trace, then run the integrity and self-replay checks. CUBIC/CoVegas models assume CONFIG_HZ=250.

`python scripts/lab_preflight.py` reports tools, BTF, HZ, build state and agent connection. The lab agent (`sudo bash scripts/start_lab_agent.sh`, started from a normal-user terminal so the owner uid is known) manages only its own namespaces and processes from a fixed scenario schema and must not be given broad process kills or arbitrary user code as root. Legacy acquisition scripts were tailored to specific paths and kernels and are archived, not rerun blindly.

## Directory map

| Location | Role |
|---|---|
| `backend/` | HTTP routes (experiments, replay sessions, lab), job coordination, history |
| `ccreplay/` | Studio adapters: recordings, revisions, controllers, replay sessions, lab client/agent/runner |
| `user/` | Replay models and parsers, validation CLIs, recorder consumers, controlled variants |
| `bpf/` | Wrapper and event-layout sources |
| `frontend/` | Web interface, lockfile, build configuration and the current `dist/` |
| `tests/` | Correctness and regression tests |
| `scripts/` | Build, smoke, e2e, lab and demo tooling |
| `experiments/` | Retained experiment programs (c2-c6); outputs go to `runtime/experiments/<run-id>/` |
| `examples/` | Recording catalog and sample lab workloads |
| `raw/` | Four curated complete recording families; immutable historical bytes |
| `data/kernel_source_ref/` | CUBIC reference and provenance |
| `docs/` | The six current documents, `EVIDENCE_INDEX.json`, and ignored `session/` notes |

Owner or generated paths are `studio_data/` (SQLite history, parameter variants, old screenshots), `controllers/user/`, `uploads/`, `runtime/` (replay sessions, demo and experiment output, lab recordings) and `build_local/`. Preserve saved experiments and user code. Unknown files are not clutter.

## Storage

The four recording families are about 124.3 MB of fixtures and set a floor under this checkout. Git history, dependencies and generated output are separate from source size. Replay sessions are the main runaway item: each stores a full computed stream in `runtime/replay/<id>/events.sqlite`, 40-72 MB for the large CUBIC and CoVegas recordings, and every Replay run in the UI creates another. They are regenerable derived data; delete a session folder only when no history row needs its detail view.

Run `python3 <package>/tools/audit_project_size.py --repo <root>` (read-only, standard library) before pruning, and keep evidence archives outside the measured folder. A release ZIP is an allowlist: source, selected recordings and sidecars, current docs, lockfiles and these instructions, excluding `.git`, `.venv`, `node_modules`, caches, `runtime/`, archives and handoff files. A small ZIP says nothing about the installed size. Never delete all environments, `studio_data/` or user code to hit a size target, and do not rewrite or prune Git history.

## Change discipline

Preserve trace bytes and source provenance. Change replay math only from controller/source evidence, never to force a match. Keep configured, measured and replay-computed values distinguishable in APIs, UI and docs. A semantic contract change needs a version bump and re-recorded traces. Use immutable revisions and trace hashes in experiment records. Test the changed behavior first, then run the baseline checks once; do not rerun research campaigns after a UI change.

## Workbench implementation and verified startup

The ordered delivery added the full computed-event debugger, immutable revisions/dependency checks, atomic recording imports, the native/capture Linux agent, editable controller and traffic scripts, persistent runs, native comparison and Advanced tools. Normal API/controller/custom-workload execution is enforced separately from the root agent. New generated data lives under ignored `runtime/`; legacy owner storage is preserved. The local source baseline was 47 tests, rather than the newer package's unavailable 74-test suite.

The machine has `ip`, `tc`, `ss`, `ethtool`, `iperf3`, clang, bpftool, BTF and CONFIG_HZ=250. The recorders rebuilt successfully. Real Reno capture attached and used an observed `ccr_reno` data socket, finalized with zero drops/gaps, and passed event-local/stateful self-replay. This does not establish zero recording overhead or support for arbitrary kernels. CUBIC/CoVegas additionally require the known model kernel/HZ assumptions; each capture stores its own self-replay outcome and the historical CUBIC verdict remains PARTIAL.

The checkout is root-owned under `/root`; there is no normal login account. Use the prepared copy and exact numeric-uid launch commands in [README](../README.md). The server explicitly refuses root startup. The owner-started agent uses `/tmp/ccreplay-lab-<uid>/agent.sock`; completed sessions remain under that owner's private directory, with separate protected recovery journals under `/run/ccreplay-lab-<uid>/`. No host routing, firewall or default-CCA sysctls are changed. Only run-owned process groups, namespaces and veth/qdiscs are cleaned.

A custom recorded workload cannot select a restricted BPF CCA as an ordinary uid on this kernel. The fixed launcher preconfigures its one unconnected socket before dropping uid/gid; all owner source runs after the drop. Its startup log reports the actual uid. The traffic editor's annotations are owner log messages, not measured network facts.

Run checks from the source checkout:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/studio_smoke.py
(cd frontend && npm run build && npm run lint)
bash scripts/build_bpf.sh
```

Browser development requires Playwright/Chromium (already present here); for another dev machine install `pytest playwright` in its development environment and run `.venv/bin/python -m playwright install chromium`. With the normal-user app and root agent running:

```sh
.venv/bin/python scripts/studio_e2e.py http://127.0.0.1:8000
```

That test drives real browser/API/workers: baseline, seeded result, source, event/seq stepping, checkpoint equality, beta edit, custom source/no-op/fix, saved identity, projector layouts, native run, edited traffic capture and exact new-recording replay. An unavailable agent is explicitly BLOCKED for the browser live path, never passed. A separate host acceptance exercised full 30-second native Reno/CUBIC runs, comparison, stop/double-stop, capture handoff, non-root scripts, crash/timeout/cancel and cleanup.

The frontend dependencies disappeared during this session and were restored with `npm ci --ignore-scripts` using the unchanged lockfile; no package versions were upgraded. The large Plotly chunk is lazy loaded and still produces Vite's size warning. Remaining lint warnings are the existing effect warnings in the retained recording detail/divergence component.

## Checkpoint boundary correction

A concurrent, preserved workspace fix added schema 2 and eight boundary regressions. A checkpoint stores private state immediately **before** `next_event_index`; suffix execution includes that event. The old schema skipped it. The seeded example at index 1704 with next index 1500 therefore resumes 205 transitions (1500..1704 inclusive). Earlier cleanup notes and archived reports describing 204 are historical evidence of the old behavior, not current instructions. Schema 1 checkpoints are rejected, and reproduced computed values/private POST state are checked in addition to position/field names. No controller equations or trace bytes changed.

## Independent-algorithm integration

The custom-algorithm package was merged manually because its guarded installer correctly rejected the redesigned worker anchor. The eight small source/example/test files are integrated without replacing the app shell, engine, lab or checkpoint fix. `backend/algorithm_workbench.py` validates requests; `ccreplay/teaching_workbench.py` executes source only in the existing bounded worker. Demo mode rejects both submission and rerun at routes and execution in the worker. The default event-local v0 contract requires None private state; explicit initialized stateful mode carries separately initialized JSON private state with the same numeric output contract.

Saved jobs contain both source texts and synthetic inputs, or an immutable copy of only the compared recording window (maximum 1,000 callbacks), its input hash and original recording hash/scope. No complete recording is duplicated. Runs opens computed inspection through the same algorithm page, including agreeing rows, and provides export and explicit rerun. Editing source/input clears old visible evidence. Browser acceptance includes file imports, keyboard stepping, threshold-return semantics, errors, recorded scope, refresh/unmount and the actual 120-second worker timeout.

Review tooling flags the intentional snapshot-backed deletions, substantial whole-workbench scope, new requested source/tests and CLI verification output. These are expected for the authorized cleanup/implementation, rather than stray personal files. `git diff --check` is clean. Source control remains uncommitted.

The forced-agent-death acceptance exposed a legacy struct_ops lifecycle detail: SIGKILL can leave a registered map after its process dies. Recovery now stops traffic/receiver before the recorder and persists the recorder's actual open-FD struct_ops map ID, name and BTF identity in the protected journal. If graceful detachment fails, only that exact identity may be unregistered; changed/foreign identities are refused. A second forced crash verified no owned registered CCA or namespaces remained and a fresh capture could attach.

## Follow-up recovery, packaging and source authority

`/root/ccreplay` is canonical source. `/var/tmp/ccreplay-studio` is a prepared normal-uid runtime copy; never edit it as a source checkout. Its `controllers/user/`, `studio_data/`, `runtime/` and `uploads/` hold new owner data. Agent artifacts remain in `/tmp/ccreplay-lab-65534/session-*`; protected recovery journals are under `/run/ccreplay-lab-65534/`. Refresh the copy only while Studio is stopped, using README's helper and preserving all those locations.

The restored complete C6 generator/harness is `experiments/c6_mutation_campaign/complete/`; the earlier stage-one `run.py` remains unchanged in its parent. Kali analysis helpers are in `experiments/kali/`, with explicit imports. `user/replay_ablation.py` and the three permanent tests are restored. Historical original bytes, including C6 specs/predictions/results, remain in the external hash-indexed friend-recovery archive (Provenance). No full campaign was launched. Complete C6 inputs include missing primary rep2/rep3 and CUBIC auxiliary recording families; the runner fails explicitly until they are restored. New output defaults to `runtime/experiments/`, and `CCREPLAY_C6_OUTPUT` selects a separate helper/analysis output directory.

Create portable exports outside the source tree, with Studio stopped:

```sh
.venv/bin/python scripts/package_release.py \
  --out /external/new-studio-source.zip --with-dist \
  --owner-export /external/new-studio-owner-data.tar.gz \
  --owner-root /root/ccreplay --owner-root /var/tmp/ccreplay-studio \
  --lab-root /tmp/ccreplay-lab-65534
```

The source ZIP contains source, lockfiles, tests, current docs and the exact curated families. It excludes installed dependencies, Python caches, Zone.Identifier files, credentials, owner stores and host builds. `--with-host-build` explicitly opts into kernel-specific `build_local/` artifacts. The separate owner export contains both identified owners' runtime/history/controllers/uploads and lab artifacts, plus evidence identities. Keep the external evidence archives with their portable indexes; their filenames/hashes are recorded separately from the source release. The packager never deletes dependencies or owner data and refuses to overwrite an existing export.

## Comparison implementation checks

`tests/test_comparison_profile.py` covers separated magnitude units, private/return/POST categories, absent/nonfinite values and native-run eligibility. `tests/test_replay_session.py` checks persisted aggregates against the real retained CUBIC callback stream. `scripts/studio_e2e.py` checks the active review workflow, immutable saved inputs, source edits, checkpoint, anchored differences, empty catalog, offline agent and both viewport sizes without initiating privileged experiments. Saved native-pair browser checks run only when genuine complete runs exist.

The root-owned checkout must be copied to an accessible normal-user location before launching: `python3 scripts/prepare_unprivileged_workspace.py --uid 65534 --gid 65534 --dest /tmp/ccreplay-review-runtime`, then `cd /tmp/ccreplay-review-runtime` and `setpriv --reuid=65534 --regid=65534 --clear-groups .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`. Use an actual normal-user checkout and `bash run_studio.sh` for ordinary use.
