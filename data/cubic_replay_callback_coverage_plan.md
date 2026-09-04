# CUBIC Callback Coverage Plan (N1.6)

Pipeline mapping: `data/r3_callback_coverage_plan.md`. See
`data/cubic_replay_capability_audit.md`'s naming table.

Written before any primary R3 recording exists, per pipeline instruction: "predict likely thin
callbacks before looking at final coverage." Predictions below are falsifiable and will be checked
against actual per-callback event counts once primary traces exist (N2/N3); this file will be
updated with an "Actual coverage" section at that point, not silently replaced.

The validated Gate-3-R2 topology (3 netns, veth, htb+bfifo bottleneck, 10 Mbit/s, 40ms base RTT,
5×BDP queue = 250000B, offloads disabled) is a **sustained bulk transfer over a lightly-loaded,
non-lossy, non-idle path** — the same topology and workload shape Phase-1 used for Reno. That
workload shape drives every prediction below.

| callback | expected in primary Gate-3-R2 workload? | likely rare? | auxiliary scenario likely required? | why |
| --- | --- | --- | --- | --- |
| `init` | yes, exactly once per recorded connection | not "rare" but inherently low-N (1 per socket) | no — structurally guaranteed once per trace, no variation to exercise | fires once at CC selection; nothing about the workload increases or decreases this count |
| `cong_avoid` | yes, dominant callback | no — expected highest-frequency event in the trace, same role as Reno's `cong_avoid` | no | fires on every cwnd-limited ACK; a 90s bulk transfer at 10 Mbit/s over 40ms RTT is the same shape that gave Reno 37k+ events per rep in Phase 1 |
| `ssthresh` (`recalc_ssthresh`) | only if a cwnd reduction event occurs | **likely rare** — the queue is 5×BDP and the path is not deliberately lossy; a single sustained bulk flow with no competing traffic and no induced loss may complete with zero or very few cwnd reductions | **likely yes** | Phase-1's Reno traces did exercise `ssthresh` under the same topology (needs confirmation from Phase-1 per-callback counts before treating this as settled — noted as an open check, not assumed), but CUBIC's multiplicative-decrease trigger conditions are not identical to Reno's; do not assume Reno's coverage transfers unchanged |
| `set_state` (`TCP_CA_Loss` branch) | only on loss-triggered state transition | **likely very rare / possibly zero** | **likely yes** | same reasoning as `ssthresh` — a single flow with no induced loss on a 5×BDP-queued bottleneck may never enter `TCP_CA_Loss`. `set_state` may still fire for other `new_state` values (e.g. `TCP_CA_Open`↔`TCP_CA_CWR` transitions), but the reference's `TCP_CA_Loss` branch — the only branch with any logic — is the one that needs exercising, and it is the one predicted thin |
| `cwnd_event` (`CA_EVENT_TX_START` branch) | only on resumption from an idle (no-data-in-flight) period | **likely very rare or zero** | **likely yes** | a *sustained* bulk transfer is, by construction, the opposite of the idle→resume pattern this event detects; predict zero or near-zero occurrences in the primary workload |
| `pkts_acked` | yes, dominant callback (same cadence class as `cong_avoid`) | no | no | fires on essentially every ACK carrying an RTT sample; a sustained bulk flow guarantees a continuous ACK stream |
| `undo_cwnd` | only on spurious-retransmission recovery | **likely rare/zero**, same as Phase-1 Reno's `undo_cwnd` | **likely yes**, if not already covered by Phase-1's own Reno auxiliary evidence (architecturally identical logic, `tcp_reno_undo_cwnd`, shared code path — a CUBIC-specific auxiliary trace may be unnecessary if Reno's Phase-1 coverage of this exact kfunc is treated as still valid; open design question for N2/N3, not resolved here) | undo requires a spurious-loss detection, which a clean low-loss path does not naturally produce |

## Summary prediction

Two callbacks are predicted to dominate primary-trace event counts (`cong_avoid`, `pkts_acked`);
one is structurally fixed at exactly 1/connection (`init`); and four are predicted thin-to-absent
under the primary workload (`ssthresh`, `set_state`'s `TCP_CA_Loss` branch, `cwnd_event`'s
`CA_EVENT_TX_START` branch, `undo_cwnd`) and will likely require an explicitly-flagged auxiliary
scenario (e.g. deliberate loss injection or an idle/resume pattern) to reach semantic coverage —
consistent with pipeline N1.6's instruction that any such auxiliary trace:

* is used only for callback semantic coverage;
* never contributes to primary R3A/R3B pass counts;
* must explicitly document its topology deviation from validated Gate-3-R2.

This is a direct structural echo of Phase-1's own coverage shape (Reno's `ssthresh`/`undo_cwnd` were
also loss-dependent and thinner than `cong_avoid`), but is stated here as an independent CUBIC-
specific prediction, not inherited from Phase 1 without re-justification — CUBIC's specific trigger
conditions (multiplicative decrease on loss, HyStart exit, idle-resume epoch shift) are distinct
mechanisms from Reno's, even where the qualitative "rare because no loss" reasoning rhymes.

**No actual coverage data exists yet as of this file's commit** — no primary R3 trace has been
recorded. This section will be replaced with an "Actual coverage" comparison once N2/N3 traces
exist.
