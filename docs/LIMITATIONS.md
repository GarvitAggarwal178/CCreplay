# Limitations

These limitations are part of the design and should be stated before evaluation.

## 1. Cross-implementation replay is not an alternate network trajectory

The trace was produced by the live reference controller. A different controller would have altered future observations.

CCReplay compares controller logic under a fixed recorded contract; it does not predict alternate throughput, RTT, or queue state.

## 2. CCReplay replays the controller boundary, not Linux TCP as a whole

Linux TCP may mutate shared state between callbacks. Mode B therefore injects recorded shared boundary state at every event.

## 3. Initial recording requires a wrapper/reference implementation

The initial design does not assume a passive independent `struct_ops` observer beside native CUBIC.

This constrains initial recordability to callable/validated reference implementations.

## 4. Replay Contracts are implementation-specific

Reno, CUBIC, Vegas, BBR, and CoVegas may require different state schemas.

There is no universal-minimality claim.

## 5. Exactness is semantic, not raw-byte equality

Correctness compares declared semantic callback results/state. Raw private bytes may contain padding or unused data.

## 6. Trace completeness is load-bearing

Dropped replay-critical events invalidate fidelity claims. CCReplay detects loss; it does not reconstruct lost events.

## 7. Controller-visible time may be load-bearing

Algorithms such as CUBIC may depend on a specific kernel timebase. High-resolution diagnostic timestamps are not automatically substitutes.

## 8. Callback coverage is controller-specific

A trace promises only the callback surface declared by its capability manifest.

## 9. No arbitrary event minimization

The base reproducer is checkpoint + suffix.

## 10. First divergence is a software result

It does not by itself prove the cause of a later performance outcome.

## 11. Initial evaluation is testbed-specific

Do not claim production-Internet portability or overhead without evidence.

## 12. Kernel portability is not guaranteed

BTF, kfunc availability, verifier behavior, and instrumentation capabilities can vary by kernel.
