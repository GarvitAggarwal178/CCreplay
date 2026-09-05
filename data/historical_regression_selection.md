# Historical Regression Selection (D1)

Read-only historical source: `~/cn-spike/covegas` (not modified — verified below). This is the
"likely v3/v4 A3" pair the addendum anticipates.

## Historical symptom

CoVegas v3 exhibits **permanent COMPETE-mode capture**: in every one of 9 intermittent-workload
runs (`REPORT_COVEGAS_V3.md` Part C), covegas correctly enters COMPETE mode on the first on-period,
correctly reverts to DELAY near the end of that on-period, then **spuriously re-enters COMPETE
2–11 seconds into the following off-period — with no competitor present — and never returns to
DELAY for the remainder of the 120s trace.** Final-sample mode was COMPETE in 9/9 v3 runs. This
made the off-period-RTT axis (183–193ms) far worse than v2's (45–140ms), the opposite of the
intended fix's goal.

## Buggy version

**v3** (`REPORT_COVEGAS_V3.md`). Note: v3's `src/covegas.bpf.c` was never itself committed to
`~/cn-spike/covegas` at any tracked path (`git log --all` shows only v4's commit,
`b5bc0be9...`/short `b5bc0be`, ever adding `src/covegas.bpf.c` — confirmed by inspecting every
version commit's tree, `data/historical_trigger_validation.md`-adjacent audit not needed here since
this is a structural git fact, not a runtime one). v3's actual behavior is reconstructed from two
independent, mutually-consistent documentary sources instead of a diffable commit:

1. `REPORT_COVEGAS_V3.md` Part C's mechanism diagnosis (quoted above).
2. The **current (v4) source's own change-log comment**, which describes exactly what v3 did
   before the fix: "(A3) the COMPETE-entry settle-latch is guarded against latching onto a
   'competitor' that isn't really there... if the settle-time rate isn't meaningfully below the
   recent max, covegas backs straight back out to DELAY instead of latching a spuriously-high
   `dlv_rate_compete` that no future rate jump could ever exceed" (`src/covegas.bpf.c` lines 44–52)
   — stated as what v4 *added*, i.e. what v3 lacked.

**Root mechanism (v3):** in `handle_compete_mode()`, once `RATE_SETTLE_MS` has elapsed since
entering COMPETE, `dlv_rate_compete` is latched to the current smoothed delivery rate
**unconditionally** — no check on whether that rate is actually depressed by a competitor. When
COMPETE is entered spuriously (no real competitor, cwnd is just self-elevated from a recent
COMPETE-mode exit that didn't reset it), the settle-time rate is close to covegas's own solo
capacity; latching it there creates a `dlv_rate_compete` reference point that no future "competitor
departed" rate-jump can ever exceed, permanently disabling the revert test.

## Fixed version

**v4** (`REPORT_COVEGAS_V4.md`), specifically its **A3 correction**
(`src/covegas.bpf.c` — this is the only version ever committed at this path, i.e. the "fixed"
source used verbatim below is the actual current file, not a reconstruction). `handle_compete_mode`
(lines 697–716):

```c
static void handle_compete_mode(struct tcp_sock *tp, struct covegas *ca, __u32 acked)
{
	if (ca->dlv_rate_compete == 0) {
		__u32 elapsed_jiffies = tcp_jiffies32 - ca->compete_enter_jiffies;

		if (elapsed_jiffies >= (RATE_SETTLE_MS * HZ) / 1000 && ca->dlv_rate_bps) {
			if (ca->dlv_rate_bps < (ca->dlv_rate_max * 3) / 4) {
				ca->dlv_rate_compete = ca->dlv_rate_bps;
			} else {
				revert_to_delay(tp, ca);
				return;
			}
		}
	} else if (ca->dlv_rate_bps > (RATE_JUMP_NUM * ca->dlv_rate_compete) / RATE_JUMP_DEN) {
		revert_to_delay(tp, ca);
		return;
	}

	cubic_growth(tp, ca, acked);
}
```

The guard (`ca->dlv_rate_bps < (ca->dlv_rate_max * 3) / 4`, i.e. the settle-time rate must be below
75% of the recently observed maximum) is the entire fix: if the rate is *not* meaningfully
depressed, `revert_to_delay()` fires immediately instead of latching. `REPORT_COVEGAS_V4.md` Part A
documents this firing correctly from real telemetry: "a spurious COMPETE entry at t=65.51s (during
an off-period, no competitor) shows `dlv_rate_compete_latched=None` — covegas backed out to DELAY
again at t=66.51s, exactly 1.00s later, matching `RATE_SETTLE_MS`=1000ms precisely." v4's own
"Which of A1/A2/A3 was load-bearing?" section states plainly: "**A3 (guarded settle-latch):
confirmed load-bearing, directly, via telemetry**... A3 is the mechanism that most directly targets
v3's Part C diagnosis, and the evidence supports it working as designed."

## Exact code/mechanism difference selected for this case study

**Only the A3 guard** — the `if (ca->dlv_rate_bps < (ca->dlv_rate_max * 3) / 4) { latch } else {
revert }` conditional, replaced by an unconditional `ca->dlv_rate_compete = ca->dlv_rate_bps;` (v3's
documented behavior). **A1 (targeted cwnd-on-revert) and A2 (detection hold) are deliberately left
in the "buggy" build unchanged from v4** — reverting all three at once would reconstruct a
different, less-documented historical state (closer to v2, not v3) and would conflate the isolated
A3 regression this case study targets with A1's own *separate, still-open* regression that v4's own
report documents in Part B1 ("a genuine regression, reported prominently... not papered over") —
that is a distinct, real, but different bug, explicitly not the subject of this case study. Isolating
A3 alone matches D1's "reasonably isolated code/mechanism difference" requirement precisely.

The CCReplay "buggy" build therefore is **v4's real, committed source with exactly this one
conditional reverted** — not a byte-for-byte historical v3 reconstruction (impossible: v3's own
source was never committed), but a source-code-and-report-justified isolation of the one mechanism
v3 lacked and v4 added, built on the same Replay Contract as the "fixed" (real v4) build so the two
can be diffed against the same recorded trace. This is disclosed here explicitly, not presented as
literal v3 source.

## Existing prior evidence

* `~/cn-spike/covegas/REPORT_COVEGAS_V3.md` Part C (mechanism diagnosis, all 9 mode traces
  inspected directly).
* `~/cn-spike/covegas/REPORT_COVEGAS_V4.md` Part A ("A3's guard, confirmed firing from telemetry")
  and "Which of A1/A2/A3 was load-bearing?" (A3 confirmed load-bearing).
* `~/cn-spike/covegas/plots/v3_mode_timeline.png` (visual: COMPETE for nearly the entire 120s v3
  trace) and `~/cn-spike/covegas/plots/v4_mode_timeline.png` (visual: DELAY correctly resumed each
  off-period in v4).

## Why this pair is suitable

* Known buggy state: v3, documented failure (permanent COMPETE capture, 9/9 runs).
* Known corrected state: v4's real committed source, documented fix (A3 guard, load-bearing per
  v4's own report).
* Reasonably isolated mechanism: one conditional in one function (`handle_compete_mode`), not
  entangled with A1's separate regression.
* Existing historical evidence of the failure: two independent detailed reports with real telemetry
  and mode-timeline plots, not merely a changelog line.
* Realistic trigger in the existing testbed: the intermittent cross-traffic workload
  (`partC_run_intermittent.sh`, addendum item 7) that both v3 and v4's Part C/B2 already used to
  surface exactly this behavior — not manufactured for CCReplay.

**Explicitly not selected:** CoVegas-vs-Vegas (forbidden by the pipeline — disagreement between
different algorithms is not a regression); A1's cwnd-target-formula regression (real, but it is a
*new* regression introduced by v4 relative to its own goals, not a "buggy vs fixed" pair with a
clean before/after — v4 is not "fixed" with respect to A1, it is where A1's problem was first
found); any hypothetical bug not backed by an existing report.

## Source repo integrity

`~/cn-spike` untouched during this investigation (read-only `git log`/`git diff`/`git ls-tree`/file
reads only, no writes). Verified via mtime sweep before commit (below).
