import csv

rows = list(csv.DictReader(open("data/audit_src/fields_out.csv")))
print("total events:", len(rows))

by_cb = {"0": [], "1": [], "2": []}
for r in rows:
    by_cb[r["callback"]].append(r)

for cb, name in [("0", "cong_avoid"), ("1", "ssthresh"), ("2", "undo_cwnd")]:
    print(f"--- {name}: {len(by_cb[cb])} events ---")

fields = ["snd_cwnd", "snd_ssthresh", "snd_cwnd_cnt", "snd_cwnd_clamp", "snd_cwnd_used",
          "snd_cwnd_stamp", "prior_cwnd", "prior_ssthresh", "packets_out", "max_packets_out"]

for cb, name in [("0", "cong_avoid"), ("1", "ssthresh"), ("2", "undo_cwnd")]:
    changed = {f: 0 for f in fields}
    for r in by_cb[cb]:
        for f in fields:
            if r[f"pre_{f}"] != r[f"post_{f}"]:
                changed[f] += 1
    n = len(by_cb[cb])
    print(f"{name} (n={n}) fields changed (count, %):")
    for f in fields:
        if changed[f] > 0:
            print(f"   {f}: {changed[f]} ({100*changed[f]/n:.1f}%)" if n else f"   {f}: {changed[f]}")

mismatches = 0
n1 = len(by_cb["1"])
for r in by_cb["1"]:
    cwnd = int(r["pre_snd_cwnd"])
    expected = max(cwnd >> 1, 2)
    if int(r["ret"]) != expected:
        mismatches += 1
print(f"ssthresh ret == max(cwnd>>1,2) mismatches: {mismatches}/{n1}")

mismatches2 = 0
n2 = len(by_cb["2"])
for r in by_cb["2"]:
    cwnd = int(r["pre_snd_cwnd"])
    prior = int(r["pre_prior_cwnd"])
    expected = max(cwnd, prior)
    if int(r["ret"]) != expected:
        mismatches2 += 1
print(f"undo_cwnd ret == max(cwnd,prior_cwnd) mismatches: {mismatches2}/{n2}")

print("--- sample cong_avoid rows ---")
for r in by_cb["0"][:3]:
    print({k: r[k] for k in ["ack", "acked", "pre_snd_cwnd", "post_snd_cwnd",
                              "pre_snd_cwnd_cnt", "post_snd_cwnd_cnt", "pre_snd_ssthresh"]})

print("--- sample undo_cwnd rows ---")
for r in by_cb["2"][:5]:
    print({k: r[k] for k in ["ret", "pre_snd_cwnd", "pre_prior_cwnd", "post_snd_cwnd"]})
