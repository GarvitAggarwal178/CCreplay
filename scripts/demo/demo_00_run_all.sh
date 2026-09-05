#!/bin/bash
# CCReplay professor demo -- run all three deterministic steps in order.
# No network. No UI. No manual edits between steps. Target < 5 min (actually ~5 s).
set -u
HERE="$(dirname "$0")"

FAIL=0
for step in demo_01_negative_control.sh demo_02_first_divergence.sh demo_03_checkpoint_reproducer.sh; do
  echo
  bash "$HERE/$step" || FAIL=1
  echo
done

# Optional historical add-on -- runs only if a qualifying trace was acquired.
# It does not affect the main demo's PASS/FAIL.
if [ -f "$HERE/../../raw/covegas_campaign/rep4.ccr" ]; then
  echo
  bash "$HERE/demo_04_historical_a3.sh" || true
  echo
fi

echo "=============================================================="
if [ "$FAIL" -eq 0 ]; then
  echo " DEMO RUN-ALL: PASS  (negative control clean, first divergence localized, reproduced from suffix)"
else
  echo " DEMO RUN-ALL: FAIL  -- see step output above; do not present demo claims"
fi
echo "=============================================================="
exit "$FAIL"
