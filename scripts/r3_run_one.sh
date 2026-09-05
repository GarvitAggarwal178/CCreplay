#!/bin/bash
# Usage: r3_run_one.sh <rep>
# One primary R3 run: 90s SOLO CUBIC transfer over the validated Gate-3-R2
# topology (10 Mbit/s, 40ms base RTT, 250000B = 5xBDP bfifo), recorded by
# ccr_cubic. Mirrors scripts/r0_run_one.sh exactly (Reno, v0) with the
# controller/recorder/manifest names substituted; storage path is
# raw/cubic_replay/primary/ (docs/REPO_WORKFLOW.md public-facing naming;
# the pipeline doc's own literal path is raw/r3/primary/ -- see the mapping
# note in data/cubic_replay_capability_audit.md's naming table, extended
# here to raw/ paths).
set -u
REP=$1
cd ~/ccreplay

PREFIX="raw/cubic_replay/primary/rep${REP}"
B_BYTES=250000

echo "=== R3 (CUBIC) primary run rep=${REP} ==="

bash scripts/set_qdiscs.sh "${B_BYTES}" > "${PREFIX}_qdisc_setup.txt" 2>&1
QDISC_RC=$?
if [ "$QDISC_RC" -ne 0 ]; then
  echo "STOP: qdisc setup failed for rep=${REP}."
  exit 2
fi

ip netns exec ns_r tc -j qdisc show dev vr2 > "${PREFIX}_bfifo_verify.json"
python3 scripts/verify_bfifo_limit.py "${PREFIX}_bfifo_verify.json" "${B_BYTES}" > "${PREFIX}_bfifo_verify.txt" 2>&1
VERIFY_RC=$?
cat "${PREFIX}_bfifo_verify.txt"
if [ "$VERIFY_RC" -ne 0 ]; then
  echo "STOP: bfifo limit verification FAILED for rep=${REP}."
  exit 3
fi

bash scripts/set_offloads.sh "${PREFIX}_offloads.txt"

bpftool struct_ops unregister name ccr_cubic 2>/dev/null || true

build/ccr_recorder_cubic "${PREFIX}.ccr" "${PREFIX}.meta.json" 95 > "${PREFIX}_recorder_stdout.txt" 2> "${PREFIX}_recorder_stderr.txt" &
REC_PID=$!

ATTACHED=0
for i in $(seq 1 100); do
  if sysctl net.ipv4.tcp_available_congestion_control 2>/dev/null | grep -q ccr_cubic; then
    ATTACHED=1
    break
  fi
  sleep 0.1
done
if [ "$ATTACHED" -ne 1 ]; then
  echo "STOP: recorder failed to attach within 10s for rep=${REP}."
  kill "$REC_PID" 2>/dev/null || true
  exit 4
fi
echo "recorder attached"

rm -f "/root/ccreplay/${PREFIX}_iperf3_server.pid"
ip netns exec ns_h2 iperf3 -s -D --pidfile "/root/ccreplay/${PREFIX}_iperf3_server.pid" > "${PREFIX}_server_start.txt" 2>&1
sleep 1

ip netns exec ns_h1 iperf3 -c 10.0.1.1 -C ccr_cubic -t 90 -i 5 -J > "${PREFIX}_iperf3.json" 2> "${PREFIX}_iperf3.err"
IPERF_RC=$?
echo "iperf3 exit=${IPERF_RC}"

wait $REC_PID
REC_RC=$?
echo "recorder exit=${REC_RC}"

if [ -f "/root/ccreplay/${PREFIX}_iperf3_server.pid" ]; then
  kill "$(cat "/root/ccreplay/${PREFIX}_iperf3_server.pid")" 2>/dev/null || true
fi

echo "=== qdisc show after transfer (ns_r, vr2) ==="
ip netns exec ns_r tc -s qdisc show dev vr2 | tee "${PREFIX}_qdisc_post.txt"

echo "=== recorder meta ==="
cat "${PREFIX}.meta.json"

echo "DONE rep=${REP}"
