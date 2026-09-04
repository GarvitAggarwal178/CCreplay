#!/bin/bash
# Usage: gate3r2_set_qdiscs.sh <B_BYTES>
set -u
B_BYTES=$1
cd ~/ccreplay

# reset (idempotent)
ip netns exec ns_h1 tc qdisc del dev vh1 root 2>/dev/null || true
ip netns exec ns_h2 tc qdisc del dev vh2 root 2>/dev/null || true
ip netns exec ns_r  tc qdisc del dev vr2 root 2>/dev/null || true

# propagation delay, one qdisc per device, root only
ip netns exec ns_h1 tc qdisc add dev vh1 root netem delay 20ms limit 10000
RC1=$?
ip netns exec ns_h2 tc qdisc add dev vh2 root netem delay 20ms limit 10000
RC2=$?

# bottleneck: htb root with one class, bfifo as that class's queue (not
# nested under another qdisc's inner-queue slot -- this is htb's normal
# classful child mechanism, and bfifo is the only thing claiming to bound
# the queue here)
ip netns exec ns_r tc qdisc add dev vr2 root handle 1: htb default 10
RC3=$?
ip netns exec ns_r tc class add dev vr2 parent 1: classid 1:10 htb rate 10mbit ceil 10mbit
RC4=$?
ip netns exec ns_r tc qdisc add dev vr2 parent 1:10 handle 20: bfifo limit "${B_BYTES}"
RC5=$?

echo "tc add exit codes: netem_h1=${RC1} netem_h2=${RC2} htb_root=${RC3} htb_class=${RC4} bfifo=${RC5}"
if [ "$RC1" -ne 0 ] || [ "$RC2" -ne 0 ] || [ "$RC3" -ne 0 ] || [ "$RC4" -ne 0 ] || [ "$RC5" -ne 0 ]; then
  echo "STOP: a tc command failed."
  exit 2
fi

echo "=== tc -s qdisc show dev vh1 (ns_h1) ==="
ip netns exec ns_h1 tc -s qdisc show dev vh1
echo "=== tc -s qdisc show dev vh2 (ns_h2) ==="
ip netns exec ns_h2 tc -s qdisc show dev vh2
echo "=== tc -s qdisc show dev vr2 (ns_r, bottleneck) ==="
ip netns exec ns_r tc -s qdisc show dev vr2
echo "=== tc class show dev vr2 (ns_r) ==="
ip netns exec ns_r tc -s class show dev vr2
echo "=== tc -s qdisc show dev vr1 (ns_r, should be untouched default) ==="
ip netns exec ns_r tc -s qdisc show dev vr1
