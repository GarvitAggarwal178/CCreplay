"""Mode-A dry run of a userspace Reno model against the real
data/audit_src/fields_out.csv capture (24,656 real kernel callback events,
60s over the validated Gate-3-R2 topology). Goal: determine empirically
whether {snd_cwnd, snd_ssthresh, snd_cwnd_cnt, snd_cwnd_clamp,
max_packets_out, is_cwnd_limited} + callback inputs {ack, acked} are
SUFFICIENT to reproduce every real tcp_reno_cong_avoid mutation exactly,
before any recorder/trace-format code is written. If not, the missing
field is discovered here, at zero re-record cost.

Model implements tcp_is_cwnd_limited / tcp_slow_start / tcp_cong_avoid_ai
exactly as declared in bpf/bpf_tracing_net.h (tcp_is_cwnd_limited) and as
recalled from upstream net/ipv4/tcp_cong.c (tcp_slow_start,
tcp_cong_avoid_ai, tcp_reno_cong_avoid) -- this run is exactly the
empirical check for whether that recollection is correct on this kernel.
"""
import csv


def tcp_is_cwnd_limited(cwnd, ssthresh, max_packets_out, is_cwnd_limited_bit):
    if cwnd < ssthresh:  # tcp_in_slow_start
        return cwnd < 2 * max_packets_out
    return bool(is_cwnd_limited_bit)


def tcp_slow_start(cwnd, ssthresh, clamp, acked):
    new_cwnd = min(cwnd + acked, ssthresh)
    acked -= (new_cwnd - cwnd)
    new_cwnd = min(new_cwnd, clamp)
    return new_cwnd, acked


def tcp_cong_avoid_ai(cwnd, cwnd_cnt, clamp, w, acked):
    if cwnd_cnt >= w:
        cwnd_cnt = 0
        cwnd += 1
    cwnd_cnt += acked
    if cwnd_cnt >= w:
        delta = cwnd_cnt // w
        cwnd_cnt -= delta * w
        cwnd += delta
    cwnd = min(cwnd, clamp)
    return cwnd, cwnd_cnt


def model_cong_avoid(pre, ack, acked):
    cwnd = pre["snd_cwnd"]
    ssthresh = pre["snd_ssthresh"]
    cwnd_cnt = pre["snd_cwnd_cnt"]
    clamp = pre["snd_cwnd_clamp"]
    max_packets_out = pre["max_packets_out"]
    is_lim = pre["is_cwnd_limited"]

    if not tcp_is_cwnd_limited(cwnd, ssthresh, max_packets_out, is_lim):
        return cwnd, cwnd_cnt  # no mutation

    if cwnd < ssthresh:  # slow start
        cwnd, acked = tcp_slow_start(cwnd, ssthresh, clamp, acked)
        if acked == 0:
            return cwnd, cwnd_cnt

    cwnd, cwnd_cnt = tcp_cong_avoid_ai(cwnd, cwnd_cnt, clamp, cwnd, acked)
    return cwnd, cwnd_cnt


def main():
    rows = list(csv.DictReader(open("data/audit_src/fields_out.csv")))
    ca_rows = [r for r in rows if r["callback"] == "0"]

    n = len(ca_rows)
    mismatches = []
    for r in ca_rows:
        pre = {
            "snd_cwnd": int(r["pre_snd_cwnd"]),
            "snd_ssthresh": int(r["pre_snd_ssthresh"]),
            "snd_cwnd_cnt": int(r["pre_snd_cwnd_cnt"]),
            "snd_cwnd_clamp": int(r["pre_snd_cwnd_clamp"]),
            "max_packets_out": int(r["pre_max_packets_out"]),
            "is_cwnd_limited": int(r["pre_is_cwnd_limited"]),
        }
        ack = int(r["ack"])
        acked = int(r["acked"])
        exp_cwnd = int(r["post_snd_cwnd"])
        exp_cwnd_cnt = int(r["post_snd_cwnd_cnt"])

        got_cwnd, got_cwnd_cnt = model_cong_avoid(pre, ack, acked)

        if got_cwnd != exp_cwnd or got_cwnd_cnt != exp_cwnd_cnt:
            mismatches.append((r, got_cwnd, got_cwnd_cnt, exp_cwnd, exp_cwnd_cnt))

    print(f"cong_avoid events: {n}")
    print(f"mismatches: {len(mismatches)}")
    print(f"match rate: {100*(n-len(mismatches))/n:.4f}%")

    for r, got_cwnd, got_cwnd_cnt, exp_cwnd, exp_cwnd_cnt in mismatches[:10]:
        print("MISMATCH:", {
            "pre_cwnd": r["pre_snd_cwnd"], "pre_ssthresh": r["pre_snd_ssthresh"],
            "pre_cwnd_cnt": r["pre_snd_cwnd_cnt"], "pre_clamp": r["pre_snd_cwnd_clamp"],
            "pre_max_packets_out": r["pre_max_packets_out"], "pre_is_cwnd_limited": r["pre_is_cwnd_limited"],
            "ack": r["ack"], "acked": r["acked"],
            "got": (got_cwnd, got_cwnd_cnt), "expected": (exp_cwnd, exp_cwnd_cnt),
        })


if __name__ == "__main__":
    main()
