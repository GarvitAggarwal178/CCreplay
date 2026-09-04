#!/usr/bin/env python3
"""Verify bfifo's configured limit (bytes) matches expected B, read back
directly from `tc -j qdisc show dev vr2` (unlike tbf, bfifo's limit is
reported as-is, no derivation needed).
Usage: gate3r2_verify_bfifo_limit.py <json_file> <expected_B_bytes>
"""
import json
import sys

path = sys.argv[1]
expected = int(sys.argv[2])

with open(path) as f:
    data = json.load(f)

bfifo = None
for q in data:
    if q.get("kind") == "bfifo":
        bfifo = q
        break

if bfifo is None:
    print(f"FAIL: no bfifo qdisc found in {path}")
    sys.exit(1)

limit = bfifo["options"]["limit"]
print(f"bfifo limit (readback) = {limit}B, expected = {expected}B")

if limit == expected:
    print("OK")
    sys.exit(0)
else:
    print(f"FAIL: readback {limit} != expected {expected}")
    sys.exit(1)
