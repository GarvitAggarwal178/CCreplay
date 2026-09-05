#!/bin/bash
# R3 primary driver: 3 x 90s SOLO CUBIC transfers over the validated
# Gate-3-R2 topology, recorded by ccr_cubic. Mirrors scripts/run_r0.sh.
set -u
cd ~/ccreplay
mkdir -p raw/cubic_replay/primary

sysctl -w kernel.bpf_stats_enabled=1

bash scripts/setup_topology.sh > raw/cubic_replay/primary/driver_setup_topology.txt 2>&1
echo "topology setup exit=$?"

for rep in 1 2 3; do
  bash scripts/r3_run_one.sh "${rep}"
  RC=$?
  if [ "$RC" -ne 0 ]; then
    echo "!!! R3 run FAILED rep=${rep} exit=${RC} !!!"
  fi
done

bash scripts/teardown_topology.sh > raw/cubic_replay/primary/driver_teardown.txt 2>&1

echo "ALL R3 PRIMARY RUNS COMPLETE"
