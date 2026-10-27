"""Shared, stdlib-only helpers for the Phase-3 Kali analyses: iperf3 JSON
and `ss -tin` log parsing, percentiles, and a Student-t quantile (no SciPy
on the VM). Imported by lab_summarize.py and nonint_analyze.py.
"""
import json
import math
import re

_RTT_RE = re.compile(r"(?<![a-z_])rtt:([0-9.]+)/")


def iperf3_metrics(path):
    """Throughput, retransmits and RTT from one iperf3 -J client log.
    Raises ValueError if the run did not complete."""
    with open(path) as f:
        d = json.load(f)
    if "error" in d:
        raise ValueError(f"iperf3 error: {d['error']}")
    end = d["end"]
    sender = end["streams"][0]["sender"]
    return {
        "throughput_bps": end["sum_received"]["bits_per_second"],
        "sent_bps": end["sum_sent"]["bits_per_second"],
        "retransmits": end["sum_sent"].get("retransmits"),
        "mean_rtt_ms": sender["mean_rtt"] / 1000.0 if "mean_rtt" in sender else None,
        "min_rtt_ms": sender["min_rtt"] / 1000.0 if "min_rtt" in sender else None,
        "max_rtt_ms": sender["max_rtt"] / 1000.0 if "max_rtt" in sender else None,
        "duration_s": end["sum_received"]["seconds"],
    }


_ACKED_RE = re.compile(r"bytes_acked:([0-9]+)")


def ss_srtt_samples(path):
    """srtt values (ms) of the DATA connection from a `ss -tin` sample log.

    Each sample (a line starting "@ <time>") can list more than one socket to
    the iperf3 port: iperf3's control connection goes to the same server port
    as the data connection, so `dport = <port>` matches both. Per sample, keep
    only the socket with the largest bytes_acked (the data flow; the control
    socket acks only a few hundred bytes). `minrtt:` is excluded.
    """
    out = []

    def flush(sockets):
        best = max((s for s in sockets if s[1] is not None), key=lambda s: s[0], default=None)
        if best is not None:
            out.append(best[1])

    sockets = []  # [(bytes_acked, rtt)] for the current sample
    with open(path) as f:
        for line in f:
            if line.startswith("@"):
                flush(sockets)
                sockets = []
                continue
            m = _RTT_RE.search(line)
            if m:
                a = _ACKED_RE.search(line)
                sockets.append((int(a.group(1)) if a else 0, float(m.group(1))))
    flush(sockets)
    return out


def percentile(xs, q):
    """Linear-interpolation percentile, q in [0, 100]."""
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


def mean(xs):
    return sum(xs) / len(xs)


def var(xs):
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


# --- Student t (regularized incomplete beta, Numerical Recipes betacf) -----

def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > 1e-300 else 1e-300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > 1e-300 else 1e-300
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def _betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1.0 - x) / b


def t_cdf(t, df):
    x = df / (df + t * t)
    tail = 0.5 * _betai(df / 2.0, 0.5, x)
    return 1.0 - tail if t >= 0 else tail


def t_quantile(p, df):
    """Inverse of t_cdf by bisection (p in (0.5, 1))."""
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def welch_ci(a, b, level=0.90):
    """CI of mean(a) - mean(b) (Welch). Returns (diff, lo, hi, df, se)."""
    va, vb, na, nb = var(a), var(b), len(a), len(b)
    se = math.sqrt(va / na + vb / nb)
    df = (va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)) if se > 0 else na + nb - 2
    t = t_quantile(1.0 - (1.0 - level) / 2.0, df)
    d = mean(a) - mean(b)
    return d, d - t * se, d + t * se, df, se


def tost_verdict(lo, hi, margin):
    """SPEC Part C: EQUIVALENT if the CI lies inside (-margin, +margin);
    NOT EQUIVALENT if it lies entirely outside; INCONCLUSIVE otherwise."""
    if -margin < lo and hi < margin:
        return "EQUIVALENT"
    if lo > margin or hi < -margin:
        return "NOT EQUIVALENT"
    return "INCONCLUSIVE"
