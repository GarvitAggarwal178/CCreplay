# Checkpoint/Reproduce Trade-Off Measurement

## Sanity Checks

✓ **Sanity Check 1 PASSED**: `case='seeded_bug'`, `interval=500`
  - checkpoint_event_index: 1500 (expected: 1500)
  - suffix_length: 204 (expected: 204)
  - identical: true (expected: true)
  - divergence_seq: 1705 (expected: 1705)

✓ **Sanity Check 2 PASSED**: `case='historical'`, all intervals
  - All intervals: identical=true (expected: true)
  - All intervals: divergence_seq=10421 (expected: 10421)

## Trade-Off Summary

The checkpoint/reproduce trade-off exhibits the classic space-time trade-off pattern:

### Seeded Bug Case (cubic_bug_ssthresh vs cubic)

**Small Intervals (50-100 events)**
- Checkpoints: 35-18 (many)
- Checkpoint bytes: 14,988-29,246 (high memory overhead)
- Suffix length: 4 events (minimal re-execution)
- Reproduce time: 5e-5 seconds (negligible)
- Optimal for interactive debugging with storage available

**Medium Intervals (250-500 events)**
- Checkpoints: 7-4 (moderate)
- Checkpoint bytes: 3,258-5,788 (reasonable)
- Suffix length: 204 events (moderate re-execution)
- Reproduce time: 0.0025-0.003 seconds (very fast)
- **Practical sweet spot** -- good balance

**Large Intervals (1000-5000 events)**
- Checkpoints: 2-1 (few)
- Checkpoint bytes: 724-1,570 (minimal storage)
- Suffix length: 704-1,704 events (significant re-execution)
- Reproduce time: 0.006-0.017 seconds (acceptable for fewer checkpoint resources)
- Optimal when checkpoint storage is constrained

### Historical Case (covegas_v3_latch vs covegas)

**Pattern**: This is a 68,424-event trace (`raw/covegas_campaign/rep4.ccr`, corrected here from the
originally-written "10,421 events total" -- 10,421 is the divergence seq, not the trace length) and
follows the same trade-off:
- Interval=50: 209 checkpoints, 387 KB, 20-event suffix, 0.35 ms reproduce
- Interval=500: 21 checkpoints, 39 KB, 420-event suffix, 5.8 ms reproduce
- Interval=5000: 3 checkpoints, 5.4 KB, 420-event suffix, 10.2 ms reproduce

The divergence consistently appears at event 10,421, confirming stable replay semantics across all checkpoint intervals.

## Key Observations

1. **Checkpoint density is interval-dependent**: With N total events and interval I, we get approximately N/I checkpoints plus one.

2. **Suffix length jumps at boundaries**: When divergence falls between checkpoints, suffix length = (divergence_index - checkpoint_index). Intervals that place a checkpoint near the divergence event yield shortest suffixes.

3. **Reproduction time is suffix-dependent**: Reproduce time scales roughly with suffix length. For the seeded_bug case, suffix={4, 204, 704, 1704} -- reproduce_ms≈{0.05, 3, 6, 17} (corrected from "0.005" ms, a 10x scientific-notation slip: 5.36e-5 s = 0.0536 ms).

4. **Identical results across intervals**: All checkpoint-based replays, regardless of interval, find identical divergence events and reproduce the same transition -- validating checkpoint engine correctness.

5. **Storage savings are significant**: Moving from interval=50 to interval=5000 in seeded_bug reduces checkpoint bytes from 29,246 to 724 bytes (97.5% reduction, corrected from "96%") at cost of ~426x longer suffix re-execution (1704/4 events, corrected from "300x").

## Practical Recommendations

- **Interactive debugging / live analysis**: Use interval=50-100 (storage < 400 KB typical, instant feedback)
- **Batch regression analysis**: Use interval=500-1000 (storage < 40 KB, < 20 ms reproduce latency)
- **Extreme resource constraints**: Use interval=2500-5000 (storage < 10 KB, accept 10-20 ms suffix re-execution)

---

**Measurement Environment:**
- Host: WSL2 Ubuntu, kernel 6.18.33.2-microsoft-standard-WSL2
- Python: 3.14.4
- Git: dba91fea (studio branch)
- Execution time: ~130 seconds for 14 measurements (2 cases x 7 intervals)
