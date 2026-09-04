#!/bin/bash
# R0 driver: 3 x 90s SOLO Reno transfers over the validated Gate-3-R2
# topology, recorded by ccr_reno. See CLAUDE.md section 11.
set -u
cd ~/ccreplay
mkdir -p raw/r0

sysctl -w kernel.bpf_stats_enabled=1

bash scripts/setup_topology.sh > raw/r0/driver_setup_topology.txt 2>&1
echo "topology setup exit=$?"

for rep in 1 2 3; do
  bash scripts/r0_run_one.sh "${rep}"
  RC=$?
  if [ "$RC" -ne 0 ]; then
    echo "!!! R0 run FAILED rep=${rep} exit=${RC} !!!"
  fi
done

bash scripts/teardown_topology.sh > raw/r0/driver_teardown.txt 2>&1

echo "ALL R0 RUNS COMPLETE"
