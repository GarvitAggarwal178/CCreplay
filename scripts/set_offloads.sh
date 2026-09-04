#!/bin/bash
# Disable offloads on all 4 veth devices, including tx-gso-list (missed in
# Gate 3-R). Usage: gate3r2_set_offloads.sh <log_file>
set -u
LOG=$1
cd ~/ccreplay

{
for pair in "ns_h1 vh1" "ns_r vr1" "ns_r vr2" "ns_h2 vh2"; do
  set -- $pair
  ns=$1
  dev=$2
  echo "=== ethtool -k $dev ($ns) BEFORE ==="
  ip netns exec "$ns" ethtool -k "$dev" 2>&1
  echo "=== applying offload disable on $dev ($ns) ==="
  ip netns exec "$ns" ethtool -K "$dev" gso off tso off gro off tx-gso-list off sg off tx off 2>&1
  echo "=== ethtool -k $dev ($ns) AFTER ==="
  ip netns exec "$ns" ethtool -k "$dev" 2>&1
  echo ""
done
} > "$LOG" 2>&1

echo "offloads applied to vh1/vr1/vr2/vh2, log at $LOG"
