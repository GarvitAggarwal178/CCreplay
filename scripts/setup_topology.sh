#!/bin/bash
# Idempotent 3-namespace topology: ns_h1 -- ns_r -- ns_h2, no qdisc nesting.
set -eu

ip netns del ns_h1 2>/dev/null || true
ip netns del ns_h2 2>/dev/null || true
ip netns del ns_r 2>/dev/null || true
ip link del vh1 2>/dev/null || true
ip link del vh2 2>/dev/null || true

ip netns add ns_h1
ip netns add ns_r
ip netns add ns_h2

# veth pair A: vh1 (ns_h1) <-> vr1 (ns_r), subnet 10.0.0.0/24
ip link add vh1 type veth peer name vr1
ip link set vh1 netns ns_h1
ip link set vr1 netns ns_r

# veth pair B: vr2 (ns_r) <-> vh2 (ns_h2), subnet 10.0.1.0/24
ip link add vr2 type veth peer name vh2
ip link set vr2 netns ns_r
ip link set vh2 netns ns_h2

ip netns exec ns_h1 ip addr add 10.0.0.1/24 dev vh1
ip netns exec ns_r  ip addr add 10.0.0.2/24 dev vr1
ip netns exec ns_r  ip addr add 10.0.1.2/24 dev vr2
ip netns exec ns_h2 ip addr add 10.0.1.1/24 dev vh2

ip netns exec ns_h1 ip link set vh1 up
ip netns exec ns_r  ip link set vr1 up
ip netns exec ns_r  ip link set vr2 up
ip netns exec ns_h2 ip link set vh2 up
ip netns exec ns_h1 ip link set lo up
ip netns exec ns_r  ip link set lo up
ip netns exec ns_h2 ip link set lo up

# forwarding in ns_r
ip netns exec ns_r sysctl -w net.ipv4.ip_forward=1

# routes: h1 reaches h2's subnet via r; h2 reaches h1's subnet via r
ip netns exec ns_h1 ip route add 10.0.1.0/24 via 10.0.0.2 dev vh1
ip netns exec ns_h2 ip route add 10.0.0.0/24 via 10.0.1.2 dev vh2

echo "=== setup done ==="
echo "-- ns_h1 addr/route --"
ip netns exec ns_h1 ip addr show vh1
ip netns exec ns_h1 ip route show
echo "-- ns_r addr/route/forward --"
ip netns exec ns_r ip addr show vr1
ip netns exec ns_r ip addr show vr2
ip netns exec ns_r sysctl net.ipv4.ip_forward
echo "-- ns_h2 addr/route --"
ip netns exec ns_h2 ip addr show vh2
ip netns exec ns_h2 ip route show
