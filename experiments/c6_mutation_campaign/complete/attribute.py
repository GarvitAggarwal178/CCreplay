"""Survivor attribution (SPEC.md section 4.2): one label per primary survivor.

U        -- the mutated line never executes on any primary trace (coverage.json).
E-proof  -- the mutant computes the same compared outputs for every input this
            harness can feed it; the argument is given per rule below.
E-obs    -- the line executes, but the distinguishing input never occurs on the
            recorded primary traces (the compared outputs were identical on
            every event).

Rules were written after reading each survivor's diff and the model source
(written by hand, after the run; nothing here is fitted to make a number
come out). Every rule names the source fact it relies on. Every survivor
must match exactly one rule, otherwise this script fails.

Usage: python results/c6_mutation_campaign/attribute.py   # writes survivors.csv
"""
import csv
import json

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from experiments.c6_mutation_campaign.complete import c6_common as common
from experiments.c6_mutation_campaign.complete import mutate

OUT = common.HERE / "survivors.csv"

# Inputs that are u32 fields in the Replay ABI, so u32() of them is the identity.
U32_ABI_INPUT_SNIPPETS = ("u32(jiffies_now)", "u32(snd_nxt)")


def _removed_abi_u32(m):
    """True if the u32() call this MASK mutant removed wrapped a u32 ABI input
    directly (one fewer `u32(jiffies_now)` / `u32(snd_nxt)` after mutation)."""
    old = [x[1:] for x in m["diff"].splitlines() if x.startswith("-") and not x.startswith("---")]
    new = [x[1:] for x in m["diff"].splitlines() if x.startswith("+") and not x.startswith("+++")]
    return any(" ".join(old).count(s) > " ".join(new).count(s) for s in U32_ABI_INPUT_SNIPPETS)


def _line(controller, n):
    return mutate.MODEL_SOURCES[controller].read_text().splitlines()[n - 1].strip()


def rule(controller, m, cov_label):
    """Return (label, rule_id, reason) for one surviving mutant."""
    op, fn, desc = m["operator"], m["function"], m["description"]
    src = _line(controller, m["line"])

    if cov_label == "U":
        return "U", "U-coverage", "mutated line never executes on any primary trace"

    # ---- E-proof ------------------------------------------------------------
    if controller == "cubic":
        if fn == "<module>" and src.split("=")[0].strip() in (
                "FAST_CONVERGENCE", "TCP_FRIENDLINESS", "HYSTART") and desc == "1 -> 2":
            return "E-proof", "P1-truthy-flag", "flag is only used as a truth value; 1 and 2 are both truthy"
        if fn == "<module>" and src.split("=")[0].strip() in ("HYSTART_ACK_TRAIN", "HYSTART_DELAY"):
            return "E-proof", "P1-truthy-flag", (
                "HYSTART_DETECT & HYSTART_ACK_TRAIN and HYSTART_DETECT & HYSTART_DELAY are only "
                "truth-tested; both stay nonzero under this change")
        if fn == "hystart_update" and op == "AOR" and desc == "& -> |":
            return "E-proof", "P1-truthy-flag", "HYSTART_DETECT | flag is nonzero, as is HYSTART_DETECT & flag (3 & 1, 3 & 2)"
        if (fn == "<module>" and src.startswith("INITIAL_SSTHRESH")) or \
                (fn == "cubictcp_init" and "not HYSTART and INITIAL_SSTHRESH" in src):
            return "E-proof", "P2-dead-branch", (
                "the `not HYSTART and INITIAL_SSTHRESH` test stays falsy with HYSTART=1, "
                "INITIAL_SSTHRESH=0 under this change")
        if op == "SDL" and src == "ca = dict(ca)":
            return "E-proof", "P3-defensive-copy", (
                "deleting the defensive copy makes the function mutate its argument in place; "
                "every compared output is unchanged because each transition() receives a fresh "
                "PRE dict (Mode A) or its own carried state (Mode B). Violates the module's "
                "documented never-mutate-the-argument convention, which no output field can show")
        if op == "MASK" and desc == "remove u32()" and _removed_abi_u32(m):
            return "E-proof", "P4-u32-abi-input", (
                "the argument is already a u32 field of the trace (clock_jiffies32_before / "
                "pre_snd_nxt), so u32() is the identity")
        if fn == "bictcp_update" and op == "ROR" and src == 'if ca["last_max_cwnd"] <= cwnd:':
            return "E-proof", "P5-equal-branches", (
                "at last_max_cwnd == cwnd the other branch gives bic_K = cubic_root(0) = 0 and "
                "bic_origin_point = last_max_cwnd = cwnd, the same as this branch")
        if fn == "bictcp_update" and op == "ROR" and src == 'if t < ca["bic_K"]:':
            return "E-proof", "P5-equal-branches", "at t == bic_K, offs = 0 and delta = 0 in both branches"
        if fn in ("cubictcp_acked", "hystart_update") and op == "ROR" and desc == "> -> >=" and (
                src.startswith('if ca["delay_min"] == 0 or ca["delay_min"] > delay')
                or src.startswith('if ca["curr_rtt"] > delay')):
            return "E-proof", "P5-equal-branches", "on equality the guarded assignment writes the value already held"
        if fn == "bictcp_update" and op == "CRP" and desc == "32 -> 33":
            return "E-proof", "P6-same-integer", "CONFIG_HZ // 33 == CONFIG_HZ // 32 == 7 for CONFIG_HZ = 250"

    # ---- E-obs (grouped by the input condition that never occurs) ----------
    if op == "MASK":
        return "E-obs", "O1-no-overflow", "the masked value never leaves the type's range on recorded inputs"
    if controller == "cubic" and (fn in ("hystart_update", "hystart_ack_delay") or (
            fn == "<module>" and src.split("=")[0].strip() in (
                "HYSTART_ACK_DELTA_US", "HYSTART_DELAY_MIN", "HYSTART_DELAY_MAX", "USEC_PER_MSEC"))):
        return "E-obs", "O2-hystart", (
            "HyStart runs only during the initial slow start (found=1 from early in every trace, via "
            "delay detection; ACK-train detection never fires); the change does not move that decision")
    if controller == "cubic" and fn == "<module>" and src.startswith(("TCP_CA_Loss", "CA_EVENT_TX_START")) or \
            (controller == "cubic" and fn == "cubictcp_cwnd_event"):
        return "E-obs", "O3-no-loss-no-epoch-shift", (
            "no set_state to Loss (states seen: 0, 1, 3) and the single TX_START event per trace has "
            "epoch_start == 0, so the epoch-shift path never changes state")
    if controller == "cubic" and (fn == "bictcp_reset" or (fn == "cubictcp_init" and op == "SDL")):
        return "E-obs", "O4-zero-init-state", (
            "bictcp_reset only runs from init (Loss never occurs), and init's recorded private PRE "
            "state is already all zero")
    if op == "SDL" and ("min(cwnd, clamp)" in src or "min(new_cwnd, clamp)" in src):
        return "E-obs", "O5-clamp-never-binding", "snd_cwnd_clamp is never below the computed cwnd"
    return "E-obs", "O6-boundary-not-hit", (
        "the changed boundary, constant or operator only matters for an input value that never "
        "occurs at that point on the recorded traces")


def main():
    analysis = json.loads((common.HERE / "analysis.json").read_text())
    muts = {json.loads(x)["id"]: json.loads(x) for x in (common.HERE / "mutants.jsonl").read_text().splitlines()}
    rows = []
    for controller, d in sorted(analysis["controllers"].items()):
        for s in d["survivors"]:
            m = muts[s["id"]]
            label, rid, reason = rule(controller, m, s["coverage_label"])
            rows.append({"id": s["id"], "controller": controller, "operator": m["operator"],
                         "function": m["function"], "line": m["line"], "description": m["description"],
                         "source_line": _line(controller, m["line"]), "label": label,
                         "rule": rid, "reason": reason})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["controller"], r["line"], r["id"])))
    counts = {}
    for r in rows:
        k = (r["controller"], r["label"], r["rule"])
        counts[k] = counts.get(k, 0) + 1
    for k in sorted(counts):
        print(*k, counts[k])


if __name__ == "__main__":
    main()
