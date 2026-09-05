#!/bin/bash
# Auxiliary scenario (Part B, docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md): one focused
# targeted attempt to trigger CUBIC's undo_cwnd callback, which fired zero times across
# all three primary Gate-3-R2 traces (undo_cwnd requires the kernel to detect a SPURIOUS
# loss/reduction -- e.g. via DSACK-based reordering detection -- which a clean,
# non-reordering bottleneck-queue-drop path does not produce).
#
# DEVIATION FROM VALIDATED GATE-3-R2 (documented, not primary evidence): after the normal
# Gate-3-R2 topology/qdisc setup, this script ADDS `reorder` to the ns_h1 netem delay qdisc
# (h1->bottleneck direction), which is not part of the validated Gate-3-R2 configuration.
# Everything else (10 Mbit/s htb+bfifo bottleneck, 40ms base RTT via two 20ms netem delays,
# offloads disabled) is unchanged. This trace is stored under raw/cubic_replay/auxiliary/
# undo_cwnd/, labeled AUXILIARY, and must never be included in primary R3A/R3B totals.
set -u
cd ~/ccreplay

PREFIX="raw/cubic_replay/auxiliary/undo_cwnd/aux1"
B_BYTES=250000
DURATION=60

mkdir -p raw/cubic_replay/auxiliary/undo_cwnd

echo "=== auxiliary undo_cwnd trigger attempt ==="

bash scripts/set_qdiscs.sh "${B_BYTES}" > "${PREFIX}_qdisc_setup.txt" 2>&1
QDISC_RC=$?
if [ "$QDISC_RC" -ne 0 ]; then
  echo "STOP: qdisc setup failed."
  exit 2
fi

echo "=== DEVIATION: adding reorder to ns_h1 netem (h1->bottleneck direction) ==="
ip netns exec ns_h1 tc qdisc change dev vh1 root netem delay 20ms reorder 25% 50% limit 10000 \
  2>&1 | tee "${PREFIX}_reorder_change.txt"
RC=$?
echo "reorder change exit=${RC}" | tee -a "${PREFIX}_reorder_change.txt"
if [ "$RC" -ne 0 ]; then
  echo "STOP: reorder qdisc change failed."
  exit 3
fi
ip netns exec ns_h1 tc -s qdisc show dev vh1 | tee -a "${PREFIX}_reorder_change.txt"

bash scripts/set_offloads.sh "${PREFIX}_offloads.txt"

bpftool struct_ops unregister name ccr_cubic 2>/dev/null || true

build/ccr_recorder_cubic "${PREFIX}.ccr" "${PREFIX}.meta.json" $((DURATION + 5)) \
  > "${PREFIX}_recorder_stdout.txt" 2> "${PREFIX}_recorder_stderr.txt" &
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
  echo "STOP: recorder failed to attach."
  kill "$REC_PID" 2>/dev/null || true
  exit 4
fi
echo "recorder attached"

rm -f "/root/ccreplay/${PREFIX}_iperf3_server.pid"
ip netns exec ns_h2 iperf3 -s -D --pidfile "/root/ccreplay/${PREFIX}_iperf3_server.pid" > "${PREFIX}_server_start.txt" 2>&1
sleep 1

ip netns exec ns_h1 iperf3 -c 10.0.1.1 -C ccr_cubic -t "${DURATION}" -i 5 -J > "${PREFIX}_iperf3.json" 2> "${PREFIX}_iperf3.err"
IPERF_RC=$?
echo "iperf3 exit=${IPERF_RC}"

wait $REC_PID
echo "recorder exit=$?"

if [ -f "/root/ccreplay/${PREFIX}_iperf3_server.pid" ]; then
  kill "$(cat "/root/ccreplay/${PREFIX}_iperf3_server.pid")" 2>/dev/null || true
fi

echo "=== recorder meta ==="
cat "${PREFIX}.meta.json"

echo "DONE auxiliary undo_cwnd attempt"
