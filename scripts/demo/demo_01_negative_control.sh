#!/bin/bash
# CCReplay professor demo -- step 1: NEGATIVE CONTROL.
# A known-good CUBIC reference implementation replayed against itself over a
# real recorded trace. Two identical implementations must never disagree.
# Deterministic; offline; ~1 s.
set -u
cd "$(dirname "$0")/../.." || exit 2

TRACE=raw/cubic_replay/primary/rep1.ccr
META=raw/cubic_replay/primary/rep1.meta.json

echo "=============================================================="
echo " CCReplay demo 1/3 -- NEGATIVE CONTROL (identical implementations)"
echo "=============================================================="
echo "TRACE:            $TRACE  (Replay ABI v1, CUBIC)"
echo "REFERENCE:        user.cubic_model"
echo "CANDIDATE:        user.cubic_model   (same module)"
echo

python3 user/ccreplay_diff.py "$TRACE" "$META" \
  --reference user.cubic_model --candidate user.cubic_model \
  | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("EVENTS CHECKED:  ", d["n_events_dominant"])
print("MATCHED:         ", d["matched_event_count_before_divergence"])
print("RESULT:          ", d["result"])
sys.exit(0 if d["result"]=="NO DIVERGENCE" else 1)
'
RC=$?
echo
if [ "$RC" -eq 0 ]; then
  echo "PASS -- identical implementations produce NO DIVERGENCE, as they must."
else
  echo "FAIL -- a negative control diverged; demo claims are void."
fi
exit "$RC"
