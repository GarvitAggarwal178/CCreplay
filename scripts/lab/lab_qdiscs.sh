#!/bin/bash
# Usage: lab_qdiscs.sh [RATE_MBIT] [DELAY_MS_EACH_WAY] [LOSS_PCT] [BUF_BYTES] [--dry-run]
#
# Parameterized version of scripts/set_qdiscs.sh (which is frozen/read-only --
# see CLAUDE.md). Mirrors its structure exactly:
#   - netem on vh1 (ns_h1) and vh2 (ns_h2) for propagation delay, one qdisc
#     per device, root only.
#   - htb (root, one class) + bfifo (that class's queue) on vr2 (ns_r) for
#     the bottleneck, same classful-child pattern as set_qdiscs.sh -- not
#     nested under another qdisc's inner-queue slot.
#   - LOSS is applied on vh1's netem qdisc only (the ns_h1 -> ns_r direction,
#     i.e. the sender/h1 uplink). It is NOT applied on vh2, so the return
#     path (ACKs from h2 back toward h1) stays loss-free in this script.
#     Document any change to this choice here if it is ever revisited.
#
# Defaults equal the validated Gate 3-R2 topology values read from
# scripts/set_qdiscs.sh, scripts/setup_topology.sh, and
# docs/archive/PHASE1_R0_R2_IMPLEMENTATION_BRIEF.md:
#   RATE_MBIT=10, DELAY_MS_EACH_WAY=20, LOSS_PCT=0, BUF_BYTES=250000 (5xBDP).
#
# HARD SAFETY RULE (see CLAUDE.md / task instructions for this environment):
# this script NEVER executes tc/ip itself in this sandbox. Only --dry-run is
# supported here: it PRINTS every tc/ip command it would run, one per line,
# and exits 0 without running any of them. Without --dry-run it refuses and
# exits nonzero -- it does not fall back to actually running privileged
# commands.
set -u

DRY_RUN=0
POSITIONAL=()
for arg in "$@"; do
  if [ "$arg" = "--dry-run" ]; then
    DRY_RUN=1
  else
    POSITIONAL+=("$arg")
  fi
done

RATE_MBIT="${POSITIONAL[0]:-10}"
DELAY_MS_EACH_WAY="${POSITIONAL[1]:-20}"
LOSS_PCT="${POSITIONAL[2]:-0}"
BUF_BYTES="${POSITIONAL[3]:-250000}"

if [ "$DRY_RUN" -ne 1 ]; then
  echo "refusing to run without --dry-run in this environment"
  echo "(privileged tc/ip network operations are disabled here -- see .autorun/SUDO_RUNBOOK.md)"
  exit 1
fi

VH1_NETEM="tc qdisc add dev vh1 root netem delay ${DELAY_MS_EACH_WAY}ms limit 10000"
if [ "$LOSS_PCT" != "0" ]; then
  VH1_NETEM="${VH1_NETEM} loss ${LOSS_PCT}%"
fi

echo "=== lab_qdiscs.sh --dry-run: RATE_MBIT=${RATE_MBIT} DELAY_MS_EACH_WAY=${DELAY_MS_EACH_WAY} LOSS_PCT=${LOSS_PCT} BUF_BYTES=${BUF_BYTES} ==="
echo "ip netns exec ns_h1 tc qdisc del dev vh1 root"
echo "ip netns exec ns_h2 tc qdisc del dev vh2 root"
echo "ip netns exec ns_r  tc qdisc del dev vr2 root"
echo "ip netns exec ns_h1 ${VH1_NETEM}"
echo "ip netns exec ns_h2 tc qdisc add dev vh2 root netem delay ${DELAY_MS_EACH_WAY}ms limit 10000"
echo "ip netns exec ns_r tc qdisc add dev vr2 root handle 1: htb default 10"
echo "ip netns exec ns_r tc class add dev vr2 parent 1: classid 1:10 htb rate ${RATE_MBIT}mbit ceil ${RATE_MBIT}mbit"
echo "ip netns exec ns_r tc qdisc add dev vr2 parent 1:10 handle 20: bfifo limit ${BUF_BYTES}"
echo "ip netns exec ns_h1 tc -s qdisc show dev vh1"
echo "ip netns exec ns_h2 tc -s qdisc show dev vh2"
echo "ip netns exec ns_r tc -s qdisc show dev vr2"
echo "ip netns exec ns_r tc -s class show dev vr2"
echo "ip netns exec ns_r tc -s qdisc show dev vr1"
echo "=== end dry-run: no command above was executed ==="
exit 0
