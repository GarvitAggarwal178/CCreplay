# CCReplay Fidelity Check Results

All checks passed. Every measured value matches the documented expected numbers from CURRENT_STATE.md section 14.

| Check | Expected | Observed | Match |
|-------|----------|----------|-------|
| R1 | 112,051 events, 224,120 field comparisons, 0 mismatches | 112,051 events, 224,120 field comparisons, 0 mismatches | YES |
| R2 | 112,051 events replayed sequentially, first divergence = NONE | 112,051 events, first divergence = NONE | YES |
| R3A | 236,088 events, 4,485,714 field comparisons; CLOCK_STABLE 236,042/0; CLOCK_AMBIGUOUS 46/4 | 236,088 events, 4,485,714 field comparisons; CLOCK_STABLE 236,042/0; CLOCK_AMBIGUOUS 46/4 | YES |
| R3B | rep1 51,323/78,688; rep2 75,603/78,768; rep3 61,729/78,632; all CLOCK_AMBIGUOUS cong_avoid | rep1 51,323/78,688; rep2 75,603/78,768; rep3 61,729/78,632; all CLOCK_AMBIGUOUS cong_avoid | YES |
| E2 | 190,277 events, 4,982,990 field comparisons, 0 mismatches | 190,277 events, 4,982,990 field comparisons, 0 mismatches | YES |
| E3 | First divergence = NONE across all 3 traces | First divergence = NONE | YES |

## Summary

All six fidelity checks (R1/R2/R3A/R3B/E2/E3) completed successfully. Every single measured value matches the documented canonical numbers exactly. No discrepancies found.

- **Reno self-replay (R1/R2):** PASS — 112,051 events checked and replayed with zero mismatches and zero divergence.
- **CUBIC self-replay (R3A/R3B):** PARTIAL (as documented) — 236,088 events with 236,042 CLOCK_STABLE events at 0 mismatches; 46 CLOCK_AMBIGUOUS events with 4 mismatches (fully characterized); first divergence in each trace lands on CLOCK_AMBIGUOUS cong_avoid events.
- **CoVegas self-replay (E2/E3):** PASS — 190,277 events checked with zero mismatches; stateful replay shows zero divergence across all three traces.

Executed on git commit dba91fea6486ad622e99503add6599f1464c7728 (studio branch) using Python 3.14.4 on WSL2 kernel 6.18.33.2-microsoft-standard.
