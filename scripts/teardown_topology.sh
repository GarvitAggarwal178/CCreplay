#!/bin/bash
set -u
cd ~/ccreplay
pkill -f "iperf3 -s" 2>/dev/null || true
ip netns del ns_h1 2>/dev/null || true
ip netns del ns_h2 2>/dev/null || true
ip netns del ns_r 2>/dev/null || true
ip link del vh1 2>/dev/null || true
ip link del vh2 2>/dev/null || true
echo "teardown done"
ip netns list
