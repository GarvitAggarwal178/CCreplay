#!/bin/bash
# Usage: lab_run.sh CCA DURATION REP [CCA2] [--dry-run]
#
# Prints (never executes, except in the --dry-run-only sense below) the
# iperf3 and ss sampling commands for one Network Lab experiment over the
# validated Gate 3-R2 topology (ns_h1 -- ns_r -- ns_h2). Command-construction
# conventions (set -u, cd ~/ccreplay, PREFIX=.../rep<REP>, pidfile handling,
# server start/kill) follow scripts/covegas_run_intermittent.sh and
# scripts/r3_run_one.sh (both frozen/read-only per CLAUDE.md).
#
#   CCA       congestion-control name for the primary flow (port 5201).
#   DURATION  primary flow duration in seconds.
#   REP       repetition number; results land under results/lab/rep<REP>_*.
#   CCA2      optional -- when given, a second concurrent competing flow
#             (port 5301, same DURATION) uses this CCA, mirroring the
#             competing-flow shape in scripts/covegas_run_intermittent.sh.
#
# HARD SAFETY RULE: this script never itself runs iperf3/ss/ip netns exec in
# this sandbox. Only --dry-run is supported here: it PRINTS every command it
# would run, one per line, and exits 0 without running any of them. Without
# --dry-run it refuses and exits nonzero.
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

CCA="${POSITIONAL[0]:-}"
DURATION="${POSITIONAL[1]:-}"
REP="${POSITIONAL[2]:-}"
CCA2="${POSITIONAL[3]:-}"

if [ "$DRY_RUN" -ne 1 ]; then
  echo "refusing to run without --dry-run in this environment"
  echo "(privileged network operations are disabled here -- see .autorun/SUDO_RUNBOOK.md)"
  exit 1
fi

if [ -z "$CCA" ] || [ -z "$DURATION" ] || [ -z "$REP" ]; then
  echo "usage: lab_run.sh CCA DURATION REP [CCA2] --dry-run"
  exit 1
fi

PREFIX="results/lab/rep${REP}"

echo "=== lab_run.sh --dry-run: CCA=${CCA} DURATION=${DURATION} REP=${REP} CCA2=${CCA2:-<none>} ==="
echo "cd ~/ccreplay"
echo "mkdir -p results/lab"
echo "rm -f /root/ccreplay/${PREFIX}_server1.pid"
echo "ip netns exec ns_h2 iperf3 -s -p 5201 -D --pidfile /root/ccreplay/${PREFIX}_server1.pid > ${PREFIX}_server1_start.txt 2>&1"
if [ -n "$CCA2" ]; then
  echo "rm -f /root/ccreplay/${PREFIX}_server2.pid"
  echo "ip netns exec ns_h2 iperf3 -s -p 5301 -D --pidfile /root/ccreplay/${PREFIX}_server2.pid > ${PREFIX}_server2_start.txt 2>&1"
fi
echo "sleep 1"
echo "ip netns exec ns_h1 ss -tin dport = 5201 dst 10.0.1.1 > ${PREFIX}_ss_sample_0.txt  # dport filter: ss otherwise also matches iperf3's control-channel and (with CCA2) the competing-flow socket"
echo "( while sleep 0.1; do ip netns exec ns_h1 ss -tin dport = 5201 dst 10.0.1.1 >> ${PREFIX}_ss.log; done ) & SS_SAMPLER_PID=\$!"
echo "ip netns exec ns_h1 iperf3 -c 10.0.1.1 -p 5201 -C ${CCA} -t ${DURATION} -i 0.1 -J > ${PREFIX}_iperf3.json 2> ${PREFIX}_iperf3.err & PRIMARY_PID=\$!"
if [ -n "$CCA2" ]; then
  echo "ip netns exec ns_h1 iperf3 -c 10.0.1.1 -p 5301 -C ${CCA2} -t ${DURATION} -i 0.1 -J > ${PREFIX}_competing_iperf3.json 2> ${PREFIX}_competing_iperf3.err & COMPETING_PID=\$!"
fi
echo "wait \$PRIMARY_PID"
if [ -n "$CCA2" ]; then
  echo "wait \$COMPETING_PID"
fi
echo "kill \$SS_SAMPLER_PID 2>/dev/null || true"
echo "kill \$(cat /root/ccreplay/${PREFIX}_server1.pid) 2>/dev/null || true"
if [ -n "$CCA2" ]; then
  echo "kill \$(cat /root/ccreplay/${PREFIX}_server2.pid) 2>/dev/null || true"
fi
echo "=== end dry-run: no command above was executed ==="
echo "NOTE: the PID-capturing lines above (SS_SAMPLER_PID=\$!, PRIMARY_PID=\$!, COMPETING_PID=\$!)"
echo "must be run as real shell statements, not stripped as comments -- without them, 'wait \$PRIMARY_PID'"
echo "becomes a bare 'wait' that blocks on the infinite ss sampler loop forever, and the final kill"
echo "commands kill nothing."
exit 0
