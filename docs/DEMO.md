# Demonstration guide

[Project home](../README.md)

## What to show

Demonstrate an executable debugging task: select a real recording, run compatible controller versions, inspect their first computed difference, then change the candidate and run again. Explain the input and transition while using the software. Graphs support that task.

The replay sequence is verified by the CLI demo and Studio smoke checks. This WSL host also completed actual native Reno/CUBIC runs and Recorded Reno capture → its new recording → computed replay under a normal application uid. See Validation for the current browser and host results. Rehearse the same setup before presenting; kernel changes require fresh qualification.

## Prepare

1. Build and start the app as in the [README](../README.md), as a normal user. Rehearse in the browser: a test log does not verify the visible workflow.
2. Run `PATH="$PWD/.venv/bin:$PATH" bash scripts/demo/demo_00_run_all.sh` once; it needs no network or privileges and no downloads.
3. Confirm the four retained recording families listed in `examples/catalog.json` exist.
4. Keep the reference and candidate sources visible. Explain an actual edit, not just a precomputed result name.
5. Use the light theme for a projector.

## Baseline demonstration

### Introduce the task

"We built a debugger for TCP congestion-control implementations. It records what the controller sees at Linux callback boundaries, then compares code versions on those same inputs. I will show exactly where a small source change first affects a decision."

Define: cwnd limits data in flight, ssthresh is the slow-start boundary, and a callback is a function Linux TCP invokes on the controller.

### Open the input

In Recordings, open `raw/cubic_replay/primary/rep1.ccr` (78,688 events for the selected dominant connection). Show the recorded cwnd and callback mix. This is a previously captured Linux session; opening it starts no traffic.

### Establish a baseline

Compare `cubic` with itself. It reports NO DIVERGENCE. This is model-versus-model agreement, distinct from the model-versus-kernel self-replay verdict (CUBIC remains PARTIAL).

### Investigate a controlled defect

Compare `cubic` against `cubic_bug_ssthresh`:

| Evidence | Computed result |
|---|---|
| Matching events before the difference | 1,704 |
| Recorded sequence / dominant row index | 1705 / 1704 |
| Callback | ssthresh |
| Shared cwnd input | 208 segments |
| Reference / candidate return | 145 / 146 segments |
| Differing field | result |

The return matters because Linux can apply it after the callback returns. Do not describe it as measured alternate throughput or as a simulated next cwnd. In Replay, open the event to see the recorded inputs, both computed outputs and private states, and the neighboring matched events.

### Reproduce from a checkpoint

With a stateful (Mode B) session open, run the checkpoint reproducer (interval 500). It stores each controller's private state **before** event 1500 and replays events 1500 through 1704 inclusive: 205 transitions, including the failing one. The result must match the full run in position, fields, computed values and private state. This is a reproducer, not trace minimization.

### Make a new change

In Controllers, create a parameter variant or edit a supported Python template. A default clone should agree. CUBIC BETA=819 differs at seq 742 in private state on this recording, not in a returned threshold. The editable CUBIC template subtracts OFFSET; OFFSET=1 gives 145 versus 144, unlike the seeded +1 module's 145 versus 146. Save, validate, compare, fix the edit, compare again. Validation checks the interface and a finite sampled execution; it is not a proof of correctness.

### Finish with evidence

Show Runs history and export. A rerun uses the saved immutable source revision and is rejected if a dependency changed. The optional historical CoVegas case (fixed v4 versus reconstructed v3, campaign rep4, first difference seq 10421, DELAY versus COMPETE mode) must always be labeled a reconstruction.

## Network Lab sequence: enable only after verification

A complete live sequence should:

1. Start the lab agent as documented in [Development](DEVELOPMENT.md) and confirm the capabilities report shows it connected.
2. Create the owned sender/router/receiver topology and run real Linux TCP through the configured bottleneck, delay and queue.
3. Show measured socket and queue telemetry during the workload.
4. Confirm the data socket uses the recording wrapper (for example `ccr_reno`) when capture is requested.
5. Finalize the recording and check record, metadata and drop integrity.
6. Open the new recording in Replay and compute a fresh comparison.

A traffic script creates workload bytes; a controller script changes userspace replay computations. Neither is arbitrary Python inside Linux TCP. A short or loss-free recording may not exercise the edited callback; show coverage and a truthful zero-change result rather than silently substituting an older recording. If live recording is unavailable, show a native run separately and label any saved recording you replay as saved.

## Questions to be ready for

| Question | Answer |
|---|---|
| Where is the simulation? | The core replays recorded callbacks. Live emulation is the Network Lab, verified end to end on the identified WSL host; other kernels require fresh qualification. |
| Why compare the same inputs? | It makes code-version differences repeatable and localizes the first changed transition. |
| Why not compare Reno and CUBIC on one trace? | Their Replay ABIs differ. Compare native behavior in separate real runs. |
| Does agreement prove correctness? | Only on the recorded events and declared fields; unexercised paths may hide defects. |
| Why is CUBIC fidelity PARTIAL? | Some callbacks cross a global clock tick that the recorder only brackets. |
| Does recording have zero overhead? | No. Non-interference was not established; a VM study failed. |

A short presentation can use the baseline in 6-8 minutes. Prioritize a coherent investigation over a tour of every page.

## Current workbench rehearsal

Use the exact normal-user/API and separate root-agent commands in [README](../README.md). Start with a 30-second native Reno run, point out real rate/cwnd/RTT/FIFO samples and final receiver throughput, then create a Recorded Reno run. Wait for finalization/integrity/self-replay and use **Open this recording in Replay**. Run Reno against itself. The recording and source hashes travel with the saved investigation.

For a reliable code-change lesson, explicitly open the previously captured CUBIC example. Run reference against itself, then choose **Loss threshold +1**. Open the first actual difference (seq1705/index1704), inspect recorded cwnd208 and computed145/146, step back/forward and read the actual source. Open the controller editor, save an edited/fixed revision and compare again. These are computations at fixed callback boundaries, not alternate live trajectories.

For checkpoint reproduction, the corrected schema-2 convention resumes **205 transitions**, indices1500..1704 inclusive, from state before index1500. It verifies computed values/private state as well as the event identity.

In Network Lab, expand the trusted traffic editor, change send/pause periods, save the revision and execute it. Observe actual uid/phase annotations and measured activity. Its own finalized capture can open in Replay. Controller scripts change replay computations; traffic scripts generate live bytes using the selected kernel controller.

In Runs, open two separately executed native Reno/CUBIC runs and compare actual receiver throughput, sampled cwnd/RTT/ACKed rate and FIFO backlog. Config and instrumentation differences remain visible. Do not present a significance/universal-winner claim or compare native against an instrumented wrapper as if recording were free.

## Independent teaching algorithms: five-minute extension

From Controllers or Replay open **Compare two independent algorithms**. Show the two source editors (StepGrowth and BatchGrowth are separate Python policies, not Linux controllers). Run the synthetic defaults: 12 callbacks, 5 disagreements, first index 1 / seq 2. Jump there: shared cwnd 12 and ACKed 3 produce computed cwnd 13 and 15. Step to application-limited index 3 (both 18), then clamp index 5 (both 20).

Select index 6 / seq 7: input cwnd 24; returned thresholds 16 and 20; both post-cwnd values stay 24. The threshold return does not assign cwnd. Import either supplied `.py` file or trusted code implementing the displayed event-local v0 contract. Change BatchGrowth's `increment = min(4, acked)` to `increment = 2`, rerun and select seq 2: B becomes 14. Export the computed result or the saved run with both sources and inputs. Equal source on both sides produces zero disagreements.

For real inputs select Captured recording, `raw__r0__rep1`, start 0, count 100. This retained file computes 29 disagreements over window [0,100) of 37,260 dominant-connection events. Each callback receives its independent recorded PRE state; this is no alternate network trajectory or performance ranking. Runs opens the saved computed rows; refresh does not execute again. Rerun saved inputs creates a new ID. Algorithm explanations are source-authored plain text, not verified Python line execution. The importer also offers initialized stateful v0 history with visible private PRE/POST; ABI-v1/v2 registered models use the separate Replay debugger.

## Follow-up professor rehearsal

1. Start the normal-uid application and separate agent with the exact README commands. Run native Reno and identify measured cwnd/RTT/ACKed-data rate.
2. Start → Compare two imported algorithms. Show the existing stateless 13/15 example and threshold returns 16/20 with post-cwnd 24. Import the independent `packet_credit.py` and `callback_credit.py` examples, select initialized stateful mode, and inspect each implementation's different private-history keys. Use controlled inputs to see a difference that appears only after history accumulates; edit, rerun, export and reopen.
3. Open the retained CUBIC recording. Select a computed event → actual source → Open controller editor. Save unchanged; full Mode B must agree. Edit the actual transition's threshold rule by +1, save and compare: seq1705/index1704 yields 145/146. Step matched neighbors, reproduce from checkpoint (205 transitions), fix the source and obtain agreement again.
4. Enable callback recording on a fresh Reno run. Wait for finalized validation, open exactly that new recording and run reference against itself. Saved examples remain separately labeled. Runs/export retain identities; no replay result is presented as a throughput prediction.

Imported stateful recorded windows must start at index zero; the precise rejection at a later offset is intentional until prefix warmup exists. The complete recovered C6 campaign is supporting historical evidence (511 mutants, 3,982 rows, 25 controls), not something to execute before class.

## Final review journeys (27 October 2026)

1. Native algorithms: on a qualified owner-started agent, run native Reno with capture off. Open “Run the other algorithm with these settings”, inspect the matching CUBIC draft and start explicitly. “Compare these runs” opens the exact pair. Check conditions, instrumentation, receiver outcomes, coverage and all four chart selectors. With no agent, open only genuine saved completed native runs; an absent pair is an actionable empty state. One execution per controller supports descriptive differences only.
2. Replay investigation: select an available recording, create/validate a compatible parameter or Python revision, then “Compare this revision”. Run explicitly. Review callback breadth, numeric magnitude, computed timeline and source/input inspection. Use differences-only navigation beyond 25 changes; refresh the session/event URL; export; reproduce a Mode-B difference from checkpoint. Mode A disables checkpoints. Use a seeded threshold bug only as the optional exact-localization control. CUBIC fidelity remains PARTIAL; CoVegas has a non-independent reference; historical recorder non-interference remains FAIL.

Browser gate: `.venv/bin/python scripts/studio_e2e.py http://127.0.0.1:8000` (add `--sandbox` for the retained independent-policy rehearsal). This gate never starts live networking. Native pair/capture review requires real saved evidence or separately authorized host execution.
