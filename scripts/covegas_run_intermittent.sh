#!/bin/bash
# Usage: covegas_run_intermittent.sh <B_BYTES> <REP> <OUTDIR>
# Adapted from ~/cn-spike/covegas/scripts/partC_run_intermittent.sh
# (docs/PROVENANCE.md) -- same workload shape: covegas runs continuously on
# port 5201 for 120s; a real kernel cubic flow runs intermittently on port
# 5301 (20s on / 20s off, 3 on-periods at [0,20) [40,60) [80,100), off at
# [20,40) [60,80) [100,120)). Uses CCReplay's own recorder
# (build/ccr_recorder_covegas) instead of the source repo's
# covegas_consumer -- produces a .ccr binary trace, not a CSV.
set -u
B_BYTES=$1
REP=$2
OUTDIR=$3
cd ~/ccreplay

PREFIX="${OUTDIR}/rep${REP}"
mkdir -p "${OUTDIR}"

echo "=== E1 intermittent: B=${B_BYTES} rep=${REP} ==="

bash scripts/set_qdiscs.sh "${B_BYTES}" > "${PREFIX}_qdisc_setup.txt" 2>&1
QDISC_RC=$?
if [ "$QDISC_RC" -ne 0 ]; then
  echo "STOP: qdisc setup failed."
  exit 2
fi

ip netns exec ns_r tc -j qdisc show dev vr2 > "${PREFIX}_bfifo_verify.json"
python3 scripts/verify_bfifo_limit.py "${PREFIX}_bfifo_verify.json" "${B_BYTES}" > "${PREFIX}_bfifo_verify.txt" 2>&1
VERIFY_RC=$?
cat "${PREFIX}_bfifo_verify.txt"
if [ "$VERIFY_RC" -ne 0 ]; then
  echo "STOP: bfifo limit verification FAILED."
  exit 3
fi

bash scripts/set_offloads.sh "${PREFIX}_offloads.txt"

bpftool struct_ops unregister name ccr_covegas 2>/dev/null || true

rm -f "/root/ccreplay/${PREFIX}_server1.pid" "/root/ccreplay/${PREFIX}_server2.pid"
ip netns exec ns_h2 iperf3 -s -p 5201 -D --pidfile "/root/ccreplay/${PREFIX}_server1.pid" > "${PREFIX}_server1_start.txt" 2>&1
ip netns exec ns_h2 iperf3 -s -p 5301 -D --pidfile "/root/ccreplay/${PREFIX}_server2.pid" > "${PREFIX}_server2_start.txt" 2>&1
sleep 1

build/ccr_recorder_covegas "${PREFIX}.ccr" "${PREFIX}.meta.json" 125 \
  > "${PREFIX}_recorder_stdout.txt" 2> "${PREFIX}_recorder_stderr.txt" &
REC_PID=$!

ATTACHED=0
for i in $(seq 1 100); do
  if sysctl net.ipv4.tcp_available_congestion_control 2>/dev/null | grep -q ccr_covegas; then
    ATTACHED=1
    break
  fi
  sleep 0.1
done
if [ "$ATTACHED" -ne 1 ]; then
  echo "STOP: recorder failed to attach within 10s."
  kill "$REC_PID" 2>/dev/null || true
  exit 4
fi
echo "recorder attached"

ip netns exec ns_h1 iperf3 -c 10.0.1.1 -p 5201 -C ccr_covegas -t 120 -i 1 -J \
  > "${PREFIX}_covegas_iperf3.json" 2> "${PREFIX}_covegas_iperf3.err" &
COVEGAS_PID=$!

for i in 1 2 3; do
  date +%s.%N > "${PREFIX}_cubic_rep${i}_start_ts.txt"
  ip netns exec ns_h1 iperf3 -c 10.0.1.1 -p 5301 -C cubic -t 20 -i 1 -J \
    > "${PREFIX}_cubic_rep${i}_iperf3.json" 2> "${PREFIX}_cubic_rep${i}_iperf3.err"
  date +%s.%N > "${PREFIX}_cubic_rep${i}_stop_ts.txt"
  if [ "$i" -lt 3 ]; then
    sleep 20
  fi
done

wait $COVEGAS_PID
echo "covegas iperf3 exit=$?"
wait $REC_PID
echo "recorder exit=$?"

if [ -f "/root/ccreplay/${PREFIX}_server1.pid" ]; then
  kill "$(cat "/root/ccreplay/${PREFIX}_server1.pid")" 2>/dev/null || true
fi
if [ -f "/root/ccreplay/${PREFIX}_server2.pid" ]; then
  kill "$(cat "/root/ccreplay/${PREFIX}_server2.pid")" 2>/dev/null || true
fi

echo "=== recorder meta ==="
cat "${PREFIX}.meta.json"

echo "DONE E1 rep=${REP}"
